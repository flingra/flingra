from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import DBAPIError

from app.database import (
    MIGRATION_LOCK_WAIT_SECONDS,
    _apply_admin_mfa_migration,
    _apply_chat_interest_approval_migration,
    _apply_two_factor_challenge_repair_migration,
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


@pytest.mark.parametrize(
    ("character_set", "collation"),
    [
        ("utf8mb4", "utf8mb4_0900_ai_ci"),
        ("utf8mb4", "utf8mb4_unicode_ci"),
    ],
)
def test_chat_interest_migration_matches_accounts_id_collation(
    character_set: str, collation: str
) -> None:
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = {
        "column_type": "varchar(64)",
        "character_set": character_set,
        "collation": collation,
    }
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "internal"
        / "migrate"
        / "migrations"
        / "000029_chat_interest_approval.sql"
    )

    _apply_chat_interest_approval_migration(connection, migration_path)

    create_table_sql = connection.exec_driver_sql.call_args_list[0].args[0]
    assert create_table_sql.count(
        f"CHARACTER SET {character_set} COLLATE {collation}"
    ) == 2
    assert len(connection.exec_driver_sql.call_args_list) == 2


def test_chat_interest_migration_rejects_unsafe_collation() -> None:
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = {
        "column_type": "varchar(64)",
        "character_set": "utf8mb4",
        "collation": "utf8mb4_unicode_ci; DROP TABLE accounts",
    }
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "internal"
        / "migrate"
        / "migrations"
        / "000029_chat_interest_approval.sql"
    )

    with pytest.raises(RuntimeError, match="invalid character set or collation"):
        _apply_chat_interest_approval_migration(connection, migration_path)

    connection.exec_driver_sql.assert_not_called()


def test_two_factor_challenge_repair_migration_creates_missing_table() -> None:
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = {
        "column_type": "varchar(64)",
        "character_set": "utf8mb4",
        "collation": "utf8mb4_unicode_ci",
    }
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "internal"
        / "migrate"
        / "migrations"
        / "000030_repair_two_factor_challenges.sql"
    )

    _apply_two_factor_challenge_repair_migration(connection, migration_path)

    create_table_sql = connection.exec_driver_sql.call_args_list[0].args[0]
    assert "CREATE TABLE IF NOT EXISTS two_factor_challenges" in create_table_sql
    assert "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci" in create_table_sql
    assert len(connection.exec_driver_sql.call_args_list) == 3


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
