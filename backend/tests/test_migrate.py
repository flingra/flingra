from sqlalchemy.exc import DBAPIError

from app.migrate import is_database_permission_error


def test_mysql_create_denied_is_identified_as_permission_error() -> None:
    error = DBAPIError("statement", {}, Exception(1142, "CREATE command denied"), False)

    assert is_database_permission_error(error)


def test_unrelated_database_error_is_not_misreported_as_permission_error() -> None:
    error = DBAPIError("statement", {}, Exception(2003, "connection refused"), False)

    assert not is_database_permission_error(error)
