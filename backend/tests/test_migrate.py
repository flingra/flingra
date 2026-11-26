from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import DBAPIError

from app.database import (
    MIGRATION_LOCK_WAIT_SECONDS,
    _apply_admin_mfa_migration,
    run_migrations,
)
from app.migrate import is_database_permission_error


@pytest.mark.parametrize(
    ("lock_result", "message"),
    [
        (0, "Timed out waiting for the database migration lock"),
        (None, "The database did not return a result for the migration lock"),
    ],
)
def test_mysql_migration_lock_failure_is_diagnostic(
    tmp_path, lock_result: int | None, message: str
) -> None:
    (tmp_path / "000001_test.sql").write_text("SELECT 1")
    connection = MagicMock()
    connection.execute.return_value.scalar_one_or_none.return_value = lock_result
    engine = MagicMock()
    engine.dialect.name = "mysql"
    engine.connect.return_value.__enter__.return_value = connection

    with pytest.raises(RuntimeError, match=message):
        run_migrations(engine, str(tmp_path))

    lock_call = connection.execute.call_args
    assert lock_call.args[1]["timeout_seconds"] == MIGRATION_LOCK_WAIT_SECONDS
    connection.commit.assert_called_once()


def test_admin_mfa_migration_adds_only_missing_columns(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'admin-mfa.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE admin_users (id TEXT PRIMARY KEY, totp_secret VARCHAR(64) NULL)"
        )
        _apply_admin_mfa_migration(connection)

    columns = {column["name"] for column in inspect(engine).get_columns("admin_users")}
    assert {"totp_secret", "totp_pending_secret", "totp_enabled"} <= columns
    engine.dispose()


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
