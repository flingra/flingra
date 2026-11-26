import uuid

import pytest
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

from app.dependencies import db_session
from app.realtime import is_origin_allowed
from app.security import hash_token
from app import realtime


def test_realtime_origin_uses_same_origin_when_no_allowlist_is_configured() -> None:
    assert is_origin_allowed(
        "https://flingra.onrender.com",
        [],
        request_scheme="wss",
        request_netloc="flingra.onrender.com",
    )
    assert not is_origin_allowed(
        "https://attacker.example.test",
        [],
        request_scheme="wss",
        request_netloc="flingra.onrender.com",
    )


def test_realtime_websocket_rejects_empty_origin_allowlist(api_client) -> None:
    client, _ = api_client
    client.app.state.settings.allowed_origins = []

    with pytest.raises(WebSocketDisconnect) as disconnect:
        with client.websocket_connect(
            "/realtime/ws",
            headers={"Origin": "https://attacker.example.test"},
        ):
            pass

    assert disconnect.value.code == 4403


def test_realtime_websocket_rejects_non_allowlisted_origin(api_client) -> None:
    client, _ = api_client
    client.app.state.settings.allowed_origins = ["https://app.example.test"]

    with pytest.raises(WebSocketDisconnect) as disconnect:
        with client.websocket_connect(
            "/realtime/ws",
            headers={"Origin": "https://attacker.example.test"},
        ):
            pass

    assert disconnect.value.code == 4403


def test_realtime_websocket_accepts_same_origin_when_allowlist_is_empty(api_client, monkeypatch) -> None:
    client, _ = api_client
    generator = client.app.dependency_overrides[db_session]()
    db = next(generator)
    account_id = uuid.uuid4().hex
    session_token = uuid.uuid4().hex
    try:
        db.execute(
            text(
                """
                INSERT INTO accounts (
                    id, email, identifier, identifier_type, password_hash, date_of_birth,
                    gender, terms_version, privacy_version, email_verified, account_state
                )
                VALUES (:id, :email, :email, 'email', 'hash', '1995-02-10',
                        'woman', 'v1', 'v1', TRUE, 'active')
                """
            ),
            {"id": account_id, "email": f"{account_id}@example.test"},
        )
        db.execute(
            text(
                """
                INSERT INTO profiles (
                    account_id, display_name, bio, photos, age_range, interests, identity,
                    onboarding_complete, document_verification
                )
                VALUES (:id, 'Member', '', '[]', '25-30', '[]', 'woman', TRUE, 'pending')
                """
            ),
            {"id": account_id},
        )
        db.execute(
            text(
                """
                INSERT INTO sessions (id, account_id, session_token_hash, expires_at)
                VALUES (:id, :account_id, :token_hash, '2099-01-01')
                """
            ),
            {"id": uuid.uuid4().hex, "account_id": account_id, "token_hash": hash_token(session_token)},
        )
        db.commit()
        engine = db.get_bind()
    finally:
        generator.close()
    monkeypatch.setattr(realtime, "get_engine", lambda _settings: engine)
    client.cookies.set("flingra_session", session_token)

    with client.websocket_connect("/realtime/ws", headers={"Origin": "http://testserver"}):
        pass
