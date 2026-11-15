import logging

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from pydantic import SecretStr

from app.config import Settings
from app import main
from app.database import build_database_url, normalize_database_url
from app.main import create_app


def settings_without_database() -> Settings:
    return Settings(
        database_url="",
        db_host=None,
        db_name=None,
        db_user=None,
        db_password=None,
        rate_limiting_enabled=False,
    )


def test_liveness_does_not_require_database() -> None:
    client = TestClient(create_app(settings_without_database()))

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_status_does_not_require_database() -> None:
    client = TestClient(create_app(settings_without_database()))

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_missing_database_configuration() -> None:
    client = TestClient(
        create_app(settings_without_database())
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "SERVICE_UNAVAILABLE",
            "message": (
                "Database is not configured. Set FLINGRA_DATABASE_URL or all "
                "FLINGRA_DB_HOST, FLINGRA_DB_NAME, FLINGRA_DB_USER, and "
                "FLINGRA_DB_PASSWORD fields."
            ),
        }
    }


def test_startup_logs_database_connection_success(monkeypatch, caplog) -> None:
    monkeypatch.setattr(main, "check_database", lambda _: True)
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    with TestClient(create_app(Settings(database_url="mysql+pymysql://test"))) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert "Database connection check succeeded." in caplog.text


def test_startup_logs_database_connection_failure_and_still_starts(caplog) -> None:
    caplog.set_level(logging.ERROR, logger="uvicorn.error")

    with TestClient(create_app(settings_without_database())) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert "Database connection check failed: Database is not configured." in caplog.text


def test_mysql_url_uses_pymysql_driver() -> None:
    assert normalize_database_url("mysql://user:pass@localhost/flingra") == (
        "mysql+pymysql://user:pass@localhost/flingra"
    )


def test_mysql_required_ssl_mode_is_converted_to_verified_pymysql_options() -> None:
    normalized = normalize_database_url(
        "mysql://user:pass@localhost/flingra?ssl-mode=REQUIRED"
    )

    assert normalized.startswith("mysql+pymysql://")
    assert "ssl-mode" not in normalized
    assert "ssl_verify_cert=false" in normalized
    assert "ssl_verify_identity" not in normalized


def test_mysql_required_mode_with_ca_enables_certificate_and_identity_validation() -> None:
    normalized = normalize_database_url(
        "mysql://user:pass@localhost/flingra?ssl-mode=REQUIRED&ssl-ca=%2Ftmp%2Faiven-ca.pem"
    )

    assert "ssl_verify_cert=true" in normalized
    assert "ssl_verify_identity=true" in normalized


def test_mysql_ssl_ca_option_is_normalized() -> None:
    normalized = normalize_database_url(
        "mysql://user:pass@localhost/flingra?ssl-mode=VERIFY_CA&ssl-ca=%2Fetc%2Fssl%2Faiven-ca.pem"
    )

    assert "ssl-mode" not in normalized
    assert "ssl_ca=%2Fetc%2Fssl%2Faiven-ca.pem" in normalized
    assert "ssl_verify_cert=true" in normalized
    assert "ssl_verify_identity" not in normalized


def test_mysql_unsupported_ssl_mode_fails_with_clear_error() -> None:
    import pytest

    with pytest.raises(ValueError, match="Unsupported MySQL ssl-mode"):
        normalize_database_url("mysql://user:pass@localhost/flingra?ssl-mode=INVALID")


def test_explicit_non_mysql_driver_is_preserved() -> None:
    url = "postgresql+psycopg://user:pass@localhost/flingra"

    assert normalize_database_url(url) == url


def test_database_url_can_be_built_from_separate_connection_settings() -> None:
    settings = Settings(
        db_host="mysql.example.test",
        db_port=24960,
        db_name="flingra",
        db_user="flingra_app",
        db_password=SecretStr("p@ss:/word"),
        db_ssl_mode="REQUIRED",
    )

    url = build_database_url(settings)

    assert url.startswith("mysql+pymysql://")
    assert "p%40ss%3A%2Fword" in url
    assert "mysql.example.test:24960/flingra" in url
    assert "ssl-mode=REQUIRED" in url

    parsed = create_engine(normalize_database_url(url)).url
    _, kwargs = create_engine(parsed).dialect.create_connect_args(parsed)
    assert kwargs["ssl_verify_cert"] == "false"


def test_database_fields_with_ca_validate_certificate_identity(tmp_path) -> None:
    ca_file = tmp_path / "aiven-ca.pem"
    ca_file.write_text("test CA placeholder")
    settings = Settings(
        db_host="mysql.example.test",
        db_port=24960,
        db_name="flingra",
        db_user="flingra_app",
        db_password=SecretStr("password"),
        db_ssl_mode="REQUIRED",
        db_ssl_ca=ca_file,
    )

    url = normalize_database_url(build_database_url(settings))
    parsed = create_engine(url).url
    _, kwargs = create_engine(parsed).dialect.create_connect_args(parsed)

    assert kwargs["ssl"]["ca"] == str(ca_file)
    assert kwargs["ssl_verify_cert"] == "true"
    assert kwargs["ssl_verify_identity"] == "true"
