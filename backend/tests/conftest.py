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

    def delete(self, key: str, content_type: str = "image/jpeg") -> None:
        self.objects.pop(key, None)

    def get_url(self, key: str, content_type: str = "image/jpeg") -> str:
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
                emergency_contact_name TEXT, emergency_contact_phone_e164 TEXT,
                terms_version TEXT NOT NULL, privacy_version TEXT NOT NULL,
                email_verified BOOLEAN NOT NULL, account_state TEXT NOT NULL,
                google_sub TEXT UNIQUE,
                login_failed_attempts INTEGER NOT NULL DEFAULT 0, locked_until DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE profiles (
                account_id TEXT PRIMARY KEY, username TEXT NOT NULL DEFAULT 'fixture',
                username_changed_at DATETIME, display_name_changed_at DATETIME,
                display_name TEXT NOT NULL DEFAULT '',
                bio TEXT NOT NULL, photos TEXT NOT NULL, videos TEXT, age_range TEXT NOT NULL,
                area TEXT NOT NULL DEFAULT '', distance_km REAL NOT NULL DEFAULT 0,
                interests TEXT NOT NULL, discoverable_by TEXT NOT NULL DEFAULT 'everyone',
                wants_to_discover TEXT NOT NULL DEFAULT 'everyone', identity TEXT NOT NULL,
                show_identity BOOLEAN NOT NULL DEFAULT FALSE, subscription_tier TEXT NOT NULL DEFAULT 'free',
                moderation_status TEXT NOT NULL DEFAULT 'pending', two_factor_enabled BOOLEAN,
                two_factor_method TEXT, onboarding_complete BOOLEAN NOT NULL DEFAULT FALSE,
                document_verification TEXT, document_type TEXT, vip_expires_at DATETIME,
                latitude REAL, longitude REAL, live_latitude REAL, live_longitude REAL,
                location_shared_at DATETIME, demo_cohort_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
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
                expires_at DATETIME NOT NULL, revoked_at DATETIME, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                device_label TEXT NOT NULL DEFAULT 'Unknown device', last_active_at DATETIME
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
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                totp_secret TEXT, totp_pending_secret TEXT,
                totp_enabled BOOLEAN NOT NULL DEFAULT FALSE
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
        connection.exec_driver_sql(
            """
            CREATE TABLE safety_blocks (
                blocker_id TEXT NOT NULL, blocked_id TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (blocker_id, blocked_id)
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE safety_reports (
                id TEXT PRIMARY KEY, reporter_id TEXT NOT NULL, target_account_id TEXT NOT NULL,
                reason TEXT NOT NULL, description TEXT, status TEXT NOT NULL DEFAULT 'open',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP, resolved_at DATETIME
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE moderation_review_requests (
                id TEXT PRIMARY KEY, requester_id TEXT NOT NULL, target_account_id TEXT NOT NULL,
                source_type TEXT NOT NULL, source_id TEXT NOT NULL, reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open', created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE emergency_contacts (
                id TEXT PRIMARY KEY, account_id TEXT NOT NULL, name TEXT NOT NULL,
                phone TEXT NOT NULL, relationship TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE safety_check_ins (
                id TEXT PRIMARY KEY, account_id TEXT NOT NULL, message TEXT NOT NULL,
                location_link TEXT, status TEXT NOT NULL, notified_contacts_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE chat_threads (
                id TEXT PRIMARY KEY, participant_a_id TEXT NOT NULL, participant_b_id TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP, last_message_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (participant_a_id, participant_b_id)
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE chat_interest_requests (
                id TEXT PRIMARY KEY, sender_id TEXT NOT NULL, recipient_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, decided_at DATETIME,
                UNIQUE (sender_id, recipient_id)
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE chat_messages (
                id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, author_id TEXT NOT NULL,
                message_text TEXT NOT NULL DEFAULT '', attachment_json TEXT, attachment_media_id TEXT,
                payment_id TEXT UNIQUE, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE meetup_payments (
                id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, payer_id TEXT NOT NULL,
                recipient_id TEXT NOT NULL, payer_name TEXT NOT NULL, recipient_name TEXT NOT NULL,
                amount_kobo INTEGER NOT NULL, status TEXT NOT NULL, dispute_reason TEXT,
                dispute_opened_by TEXT, resolution_reason TEXT, resolved_by_admin_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, resolved_at DATETIME
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE live_streams (
                id TEXT PRIMARY KEY, host_account_id TEXT NOT NULL, room_name TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL, status TEXT NOT NULL,
                started_at DATETIME DEFAULT CURRENT_TIMESTAMP, ended_at DATETIME,
                room_closed_at DATETIME
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE member_posts (
                id TEXT PRIMARY KEY, author_id TEXT NOT NULL, photos TEXT NOT NULL,
                video_url TEXT, caption TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE member_statuses (
                id TEXT PRIMARY KEY, author_id TEXT NOT NULL, media_url TEXT NOT NULL,
                media_kind TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE privacy_requests (
                id TEXT PRIMARY KEY, account_id TEXT NOT NULL, request_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued', result_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE subscription_plans (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, duration_days INTEGER NOT NULL,
                price_kobo INTEGER NOT NULL, active BOOLEAN NOT NULL DEFAULT TRUE
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO subscription_plans (id, name, duration_days, price_kobo, active)
            VALUES
                ('vip-weekly', 'Weekly VIP', 7, 350000, TRUE),
                ('vip-monthly', 'Monthly VIP', 30, 1000000, TRUE),
                ('vip-yearly', 'Yearly VIP', 365, 8000000, TRUE)
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE wallet_accounts (
                account_id TEXT PRIMARY KEY, balance_kobo INTEGER NOT NULL DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE wallet_transactions (
                id TEXT PRIMARY KEY, account_id TEXT NOT NULL, transaction_type TEXT NOT NULL,
                amount_kobo INTEGER NOT NULL, description TEXT NOT NULL, status TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE referral_codes (
                account_id TEXT PRIMARY KEY, code TEXT NOT NULL UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE referral_rewards (
                referred_account_id TEXT PRIMARY KEY, referrer_account_id TEXT,
                referral_code TEXT NOT NULL, bonus_kobo INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE wallet_payment_intents (
                id TEXT PRIMARY KEY, account_id TEXT NOT NULL, reference TEXT NOT NULL UNIQUE,
                amount_kobo INTEGER NOT NULL, currency TEXT NOT NULL, status TEXT NOT NULL,
                authorization_url TEXT, settled_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE payout_bank_accounts (
                account_id TEXT PRIMARY KEY, recipient_code TEXT NOT NULL UNIQUE,
                bank_code TEXT NOT NULL, bank_name TEXT NOT NULL, account_name TEXT NOT NULL,
                account_last4 TEXT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE payout_requests (
                id TEXT PRIMARY KEY, account_id TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                reference TEXT NOT NULL UNIQUE, recipient_code TEXT NOT NULL, amount_kobo INTEGER NOT NULL,
                wallet_transaction_id TEXT NOT NULL, transfer_code TEXT, status TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(account_id, idempotency_key)
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE gift_catalog (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, emoji TEXT NOT NULL,
                price_kobo INTEGER NOT NULL, active BOOLEAN NOT NULL DEFAULT TRUE
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO gift_catalog (id, name, emoji, price_kobo, active)
            VALUES
                ('rose', 'Rose', '🌹', 50000, TRUE),
                ('fire', 'Fire', '🔥', 100000, TRUE),
                ('diamond', 'Diamond', '💎', 500000, TRUE),
                ('crown', 'Crown', '👑', 1000000, TRUE)
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE gift_inventory (
                account_id TEXT NOT NULL, gift_type_id TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (account_id, gift_type_id)
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE received_gifts (
                id TEXT PRIMARY KEY, recipient_id TEXT NOT NULL, sender_id TEXT NOT NULL,
                gift_type_id TEXT NOT NULL, value_kobo INTEGER NOT NULL,
                redeemed BOOLEAN NOT NULL DEFAULT FALSE, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE call_credit_pricing (
                id INTEGER PRIMARY KEY, price_naira INTEGER NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            "INSERT INTO call_credit_pricing (id, price_naira) VALUES (1, 50)"
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE call_credit_accounts (
                account_id TEXT PRIMARY KEY, balance INTEGER NOT NULL DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE call_sessions (
                id TEXT PRIMARY KEY, caller_id TEXT NOT NULL, callee_id TEXT NOT NULL,
                payer_id TEXT, room_name TEXT NOT NULL UNIQUE, call_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ringing', started_at DATETIME,
                last_billed_at DATETIME, last_activity_at DATETIME, ended_at DATETIME,
                caller_connected_at DATETIME, callee_connected_at DATETIME,
                room_closed_at DATETIME, billed_ticks INTEGER NOT NULL DEFAULT 0,
                idempotency_key TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(caller_id, idempotency_key)
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE call_credit_transactions (
                id TEXT PRIMARY KEY, account_id TEXT NOT NULL, call_id TEXT,
                tick_number INTEGER, transaction_type TEXT NOT NULL,
                amount INTEGER NOT NULL, description TEXT NOT NULL,
                idempotency_key TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(call_id, tick_number), UNIQUE(account_id, idempotency_key)
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE video_unlocks (
                id TEXT PRIMARY KEY, viewer_id TEXT NOT NULL, creator_id TEXT NOT NULL,
                media_id TEXT NOT NULL, price_kobo INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP, expires_at DATETIME NOT NULL,
                UNIQUE(viewer_id, media_id)
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE live_stream_join_requests (
                id TEXT PRIMARY KEY, stream_id TEXT NOT NULL, requester_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP, responded_at DATETIME
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE live_stream_participants (
                stream_id TEXT NOT NULL, account_id TEXT NOT NULL, role TEXT NOT NULL,
                joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (stream_id, account_id)
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE live_stream_messages (
                id TEXT PRIMARY KEY, stream_id TEXT NOT NULL, author_id TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'message', message_text TEXT NOT NULL,
                gift_id TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE realtime_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, recipient_id TEXT NOT NULL,
                event_type TEXT NOT NULL, payload_json TEXT NOT NULL,
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
