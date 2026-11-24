from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import DBAPIError

from app.migrate import is_database_permission_error


def test_mysql_create_denied_is_identified_as_permission_error() -> None:
    error = DBAPIError("statement", {}, Exception(1142, "CREATE command denied"), False)

    assert is_database_permission_error(error)


def test_unrelated_database_error_is_not_misreported_as_permission_error() -> None:
    error = DBAPIError("statement", {}, Exception(2003, "connection refused"), False)

    assert not is_database_permission_error(error)


def test_live_location_migration_adds_private_live_location_columns(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    migration_file = (
        Path(__file__).resolve().parents[1]
        / "internal"
        / "migrate"
        / "migrations"
        / "000013_live_location_sharing.sql"
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE profiles (account_id TEXT PRIMARY KEY)")
        for statement in migration_file.read_text().split(";"):
            if statement.strip():
                connection.exec_driver_sql(statement)
    assert {"live_latitude", "live_longitude", "location_shared_at"} <= {
        column["name"] for column in inspect(engine).get_columns("profiles")
    }
    engine.dispose()
