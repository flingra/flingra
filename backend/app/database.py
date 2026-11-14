from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, URL, create_engine, make_url, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.errors import ServiceUnavailable


@lru_cache(maxsize=4)
def _engine_for_url(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


@lru_cache(maxsize=4)
def _sessionmaker_for_url(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=_engine_for_url(database_url), expire_on_commit=False)


def normalize_database_url(database_url: str) -> str:
    url = make_url(database_url)
    if url.drivername in {"mysql", "mysql+mysqldb"}:
        url = url.set(drivername="mysql+pymysql")

    query = dict(url.query)
    ssl_mode = query.pop("ssl-mode", query.pop("ssl_mode", None))
    if isinstance(ssl_mode, tuple):
        if len(ssl_mode) != 1:
            raise ValueError("MySQL ssl-mode must be specified exactly once")
        ssl_mode = ssl_mode[0]
    for key in tuple(query):
        if key.startswith("ssl-"):
            query[key.replace("-", "_")] = query.pop(key)

    if ssl_mode is not None:
        if not isinstance(ssl_mode, str):
            raise ValueError("MySQL ssl-mode must be a string")
        normalized_mode = ssl_mode.upper()
        if normalized_mode == "DISABLED":
            query["ssl_disabled"] = "true"
        elif normalized_mode == "PREFERRED":
            pass
        elif normalized_mode == "REQUIRED":
            if query.get("ssl_ca"):
                query["ssl_verify_cert"] = "true"
                query["ssl_verify_identity"] = "true"
            else:
                query["ssl_verify_cert"] = "false"
        elif normalized_mode == "VERIFY_CA":
            query["ssl_verify_cert"] = "true"
        elif normalized_mode == "VERIFY_IDENTITY":
            query["ssl_verify_cert"] = "true"
            query["ssl_verify_identity"] = "true"
        else:
            raise ValueError(f"Unsupported MySQL ssl-mode: {ssl_mode}")

    url = url.set(query=query)
    return url.render_as_string(hide_password=False)


def build_database_url(settings: Settings) -> str:
    if settings.database_url:
        return settings.database_url

    db_host = settings.db_host
    db_name = settings.db_name
    db_user = settings.db_user
    db_password = settings.db_password
    required = {
        "host": db_host,
        "database": db_name,
        "username": db_user,
        "password": db_password,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ServiceUnavailable(
            "Database is not configured. Set FLINGRA_DATABASE_URL or all "
            "FLINGRA_DB_HOST, FLINGRA_DB_NAME, FLINGRA_DB_USER, and FLINGRA_DB_PASSWORD fields."
        )
    if not db_host or not db_name or not db_user or db_password is None:
        raise ServiceUnavailable("Database connection settings are incomplete.")

    query = {"ssl-mode": settings.db_ssl_mode}
    if settings.db_ssl_ca:
        query["ssl-ca"] = str(settings.db_ssl_ca)
    return URL.create(
        "mysql+pymysql",
        username=db_user,
        password=db_password.get_secret_value(),
        host=db_host,
        port=settings.db_port,
        database=db_name,
        query=query,
    ).render_as_string(hide_password=False)


def get_engine(settings: Settings) -> Engine:
    return _engine_for_url(normalize_database_url(build_database_url(settings)))


def check_database(settings: Settings) -> bool:
    try:
        with get_engine(settings).connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except ServiceUnavailable:
        raise
    except SQLAlchemyError as exc:
        raise ServiceUnavailable("Database is unavailable.") from exc


def get_db(settings: Settings) -> Iterator[Session]:
    database_url = normalize_database_url(build_database_url(settings))
    session_factory = _sessionmaker_for_url(database_url)
    with session_factory() as session:
        yield session


def run_migrations(engine: Engine, migrations_dir: str) -> list[str]:
    from pathlib import Path

    from sqlalchemy import inspect

    migration_path = Path(migrations_dir)
    files = sorted(migration_path.glob("[0-9][0-9][0-9][0-9][0-9][0-9]_*.sql"))
    if not files:
        raise RuntimeError(f"No migrations found in {migration_path}")

    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(255) NOT NULL PRIMARY KEY,
                applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    with engine.connect() as connection:
        applied = set(
            connection.execute(text("SELECT version FROM schema_migrations")).scalars().all()
        )
    existing_tables = set(inspect(engine).get_table_names())

    if not applied and "accounts" in existing_tables:
        legacy_tables = {
            "accounts",
            "email_verification_tokens",
            "sessions",
            "password_reset_tokens",
        }
        missing = legacy_tables - existing_tables
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise RuntimeError(
                "Found a partial legacy schema without migration history; "
                f"inspect the database before migrating (missing: {missing_list})."
            )
        baseline = [
            path
            for path in files
            if path.name[:6] in {"000001", "000002", "000003", "000004"}
        ]
        with engine.begin() as connection:
            for path in baseline:
                connection.execute(
                    text("INSERT INTO schema_migrations (version) VALUES (:version)"),
                    {"version": path.name},
                )
        applied.update(path.name for path in baseline)

    newly_applied: list[str] = []
    for path in files:
        if path.name in applied:
            continue
        statements = [
            statement.strip()
            for statement in path.read_text().split(";")
            if statement.strip()
        ]
        with engine.begin() as connection:
            for statement in statements:
                connection.exec_driver_sql(statement)
            connection.execute(
                text("INSERT INTO schema_migrations (version) VALUES (:version)"),
                {"version": path.name},
            )
        newly_applied.append(path.name)
    return newly_applied
