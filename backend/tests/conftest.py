from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.dependencies import db_session
from app.main import create_app


class TestObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put(self, key: str, body: bytes, content_type: str) -> None:
        self.objects[key] = (body, content_type)

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def get_url(self, key: str) -> str:
        return f"https://storage.example.test/{key}"


@pytest.fixture
def api_client() -> Iterator[tuple[TestClient, list[str]]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE accounts (
                id TEXT PRIMARY KEY, email TEXT UNIQUE, identifier TEXT UNIQUE NOT NULL,
                identifier_type TEXT NOT NULL, password_hash TEXT NOT NULL,
                date_of_birth DATE NOT NULL, gender TEXT NOT NULL, referred_by_code TEXT,
                terms_version TEXT NOT NULL, privacy_version TEXT NOT NULL,
                email_verified BOOLEAN NOT NULL, account_state TEXT NOT NULL,
                google_sub TEXT UNIQUE,
                login_failed_attempts INTEGER NOT NULL DEFAULT 0, locked_until DATETIME
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE profiles (
                account_id TEXT PRIMARY KEY, display_name TEXT NOT NULL DEFAULT '',
                bio TEXT NOT NULL, photos TEXT NOT NULL, videos TEXT, age_range TEXT NOT NULL,
                area TEXT NOT NULL DEFAULT '', distance_km REAL NOT NULL DEFAULT 0,
                interests TEXT NOT NULL, discoverable_by TEXT NOT NULL DEFAULT 'everyone',
                wants_to_discover TEXT NOT NULL DEFAULT 'everyone', identity TEXT NOT NULL,
                show_identity BOOLEAN NOT NULL DEFAULT FALSE, subscription_tier TEXT NOT NULL DEFAULT 'free',
                moderation_status TEXT NOT NULL DEFAULT 'pending', two_factor_enabled BOOLEAN,
                two_factor_method TEXT, onboarding_complete BOOLEAN NOT NULL DEFAULT FALSE,
                document_verification TEXT, document_type TEXT, vip_expires_at DATETIME,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.connection.create_function(
            "CONCAT",
            -1,
            lambda *parts: "".join(str(part) for part in parts),
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY, account_id TEXT NOT NULL, session_token_hash BLOB UNIQUE NOT NULL,
                expires_at DATETIME NOT NULL, revoked_at DATETIME, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE email_verification_tokens (
                account_id TEXT PRIMARY KEY, token_hash BLOB UNIQUE NOT NULL,
                expires_at DATETIME NOT NULL, attempt_count INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE password_reset_tokens (
                account_id TEXT PRIMARY KEY, token_hash BLOB UNIQUE NOT NULL,
                expires_at DATETIME NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE media_objects (
                id TEXT PRIMARY KEY, account_id TEXT NOT NULL, purpose TEXT NOT NULL,
                object_key TEXT UNIQUE NOT NULL, content_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE admin_users (
                id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'reviewer',
                failed_login_attempts INTEGER NOT NULL DEFAULT 0, locked_until DATETIME,
                disabled_at DATETIME, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE admin_sessions (
                id TEXT PRIMARY KEY, admin_id TEXT NOT NULL,
                session_token_hash BLOB UNIQUE NOT NULL, expires_at DATETIME NOT NULL,
                revoked_at DATETIME, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE platform_audit_events (
                id TEXT PRIMARY KEY, event_type TEXT NOT NULL, actor_type TEXT NOT NULL,
                actor_id TEXT, subject_account_id TEXT, outcome TEXT NOT NULL,
                request_id TEXT NOT NULL, metadata TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    delivered_codes: list[str] = []
    settings = Settings(
        database_url="sqlite://",
        session_cookie_secure=False,
        rate_limiting_enabled=False,
        allowed_origins=[],
        brevo_api_key="test-key",
        brevo_sender_email="noreply@example.test",
        google_client_id="test-google-client-id",
    )
    application = create_app(settings)
    application.state.media_storage = TestObjectStorage()

    def override_db() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            yield session

    application.dependency_overrides[db_session] = override_db
    with TestClient(application) as client:
        yield client, delivered_codes
    engine.dispose()
