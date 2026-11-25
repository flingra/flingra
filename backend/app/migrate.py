from pathlib import Path

from sqlalchemy.exc import DBAPIError

from app.config import Settings, get_settings
from app.database import get_engine, run_migrations


def run_configured_migrations(settings: Settings | None = None) -> list[str]:
    settings = settings or get_settings()
    migration_settings = settings.model_copy(
        update={"database_url": settings.migration_database_url or settings.database_url}
    )
    migrations_dir = Path(__file__).resolve().parents[1] / "internal" / "migrate" / "migrations"
    return run_migrations(get_engine(migration_settings), str(migrations_dir))


def is_database_permission_error(error: DBAPIError) -> bool:
    return getattr(error.orig, "args", (None,))[0] in {1044, 1045, 1142, 1143}


def main() -> None:
    try:
        applied = run_configured_migrations()
    except DBAPIError as exc:
        if not is_database_permission_error(exc):
            raise
        raise SystemExit(
            "Migration failed because the configured migration database user lacks "
            "required DDL permissions. Configure FLINGRA_MIGRATION_DATABASE_URL with "
            "a database-migration account that can create/alter tables and indexes, "
            "or ask your database administrator to apply the migrations. The runtime "
            "database account can remain least-privileged."
        ) from None

    if applied:
        for migration in applied:
            print(f"Applied migration: {migration}")
    else:
        print("Database schema is up to date.")


if __name__ == "__main__":
    main()
