import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.dependencies import db_session
from app.errors import ServiceUnavailable
from app.routes import calls
from app.security import hash_password
from test_discovery import _create_candidate, _create_viewer


def _session(client):
    generator = client.app.dependency_overrides[db_session]()
    return next(generator), generator


def _login_as_candidate(client, account_id: str) -> TestClient:
    password = "candidate-password-123"
    db, generator = _session(client)
    try:
        email = db.execute(
            text("SELECT email FROM accounts WHERE id = :id"),
            {"id": account_id},
        ).scalar_one()
        db.execute(
            text("UPDATE accounts SET password_hash = :password WHERE id = :id"),
            {"password": hash_password(password), "id": account_id},
        )
        db.commit()
    finally:
        generator.close()
    candidate = TestClient(client.app)
    response = candidate.post(
        "/auth/login",
        json={"identifier": email, "password": password},
    )
    assert response.status_code == 200, response.json()
    return candidate


def test_call_credit_purchase_and_server_billed_call_lifecycle(api_client, monkeypatch) -> None:
    client, _ = api_client
    caller_id = _create_viewer(client, monkeypatch)
    callee_id = _create_candidate(client)
    db, generator = _session(client)
    try:
        db.execute(
            text("UPDATE profiles SET photos = :photos WHERE account_id = :account_id"),
            {
                "photos": json.dumps(["/media/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]),
                "account_id": caller_id,
            },
        )
        db.execute(
            text("INSERT INTO wallet_accounts (account_id, balance_kobo) VALUES (:id, 500000)"),
            {"id": caller_id},
        )
        db.commit()
    finally:
        generator.close()

    client.app.state.settings.livekit_url = "wss://livekit.example.test"
    client.app.state.settings.livekit_api_key = "api-key"
    from pydantic import SecretStr

    client.app.state.settings.livekit_api_secret = SecretStr("api-secret")
    monkeypatch.setattr(calls, "delete_room", lambda *_args: None)
    csrf = client.cookies["flingra_csrf"]

    assert client.get("/calls/coin-price").json() == {"priceNaira": 50}
    assert client.get("/calls/coin-packages").json() == [
        {"coins": 10, "priceNaira": 500},
        {"coins": 15, "priceNaira": 750},
        {"coins": 30, "priceNaira": 1500},
    ]
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": "purchase-key-0001"}
    purchase = client.post("/calls/credits/purchase", headers=headers, json={"coins": 10})
    assert purchase.status_code == 201, purchase.json()
    assert purchase.json() == {"coins": 10, "balanceNaira": 4500}
    assert client.post("/calls/credits/purchase", headers=headers, json={"coins": 10}).json() == purchase.json()
    mismatch = client.post("/calls/credits/purchase", headers=headers, json={"coins": 15})
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    started = client.post(
        "/calls",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "call-key-0001"},
        json={"targetId": callee_id, "callType": "audio"},
    )
    assert started.status_code == 201, started.json()
    call_id = started.json()["callId"]
    assert started.json()["status"] == "ringing"

    callee = _login_as_candidate(client, callee_id)
    try:
        incoming = callee.get("/calls/incoming").json()[0]
        assert incoming["callId"] == call_id
        assert incoming["status"] == "ringing"
        assert incoming["callerId"] == caller_id
        assert incoming["callerName"] == "Viewer"
        assert incoming["callerIdentity"] == "man"
        assert incoming["callerPhoto"] == "/media/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        callee_csrf = callee.cookies["flingra_csrf"]
        accepted = callee.post(
            f"/calls/{call_id}/accept",
            headers={"X-CSRF-Token": callee_csrf},
        )
        assert accepted.status_code == 200, accepted.json()
        assert accepted.json()["status"] == "connecting"
        assert client.post(
            f"/calls/{call_id}/connected",
            headers={"X-CSRF-Token": csrf},
        ).json()["status"] == "connecting"
        connected = callee.post(
            f"/calls/{call_id}/connected",
            headers={"X-CSRF-Token": callee_csrf},
        )
        assert connected.status_code == 200, connected.json()
        assert connected.json()["status"] == "active"
        assert connected.json()["creditBalance"] == 9
        assert client.get("/calls/credits").json() == {"coins": 9}

        db, generator = _session(client)
        try:
            db.execute(
                text("UPDATE call_sessions SET last_billed_at = :time WHERE id = :id"),
                {"time": datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=60), "id": call_id},
            )
            db.commit()
        finally:
            generator.close()
        boundary = client.post(
            f"/calls/{call_id}/heartbeat",
            headers={"X-CSRF-Token": csrf},
        )
        assert boundary.status_code == 200, boundary.json()
        assert boundary.json()["creditBalance"] == 9

        db, generator = _session(client)
        try:
            db.execute(
                text("UPDATE call_sessions SET last_billed_at = :time WHERE id = :id"),
                {"time": datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=61), "id": call_id},
            )
            db.commit()
        finally:
            generator.close()
        heartbeat = client.post(
            f"/calls/{call_id}/heartbeat",
            headers={"X-CSRF-Token": csrf},
        )
        assert heartbeat.status_code == 200, heartbeat.json()
        assert heartbeat.json()["creditBalance"] == 8
        db, generator = _session(client)
        try:
            db.execute(
                text("UPDATE call_sessions SET last_billed_at = :time WHERE id = :id"),
                {"time": datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=61), "id": call_id},
            )
            db.commit()
        finally:
            generator.close()
        ended = client.delete(
            f"/calls/{call_id}",
            headers={"X-CSRF-Token": csrf},
        )
        assert ended.status_code == 204
        assert client.get(f"/calls/{call_id}").json()["status"] == "ended"
        assert client.get("/calls/credits").json() == {"coins": 7}
    finally:
        callee.close()

    db, generator = _session(client)
    try:
        assert db.execute(
            text(
                """
                SELECT COUNT(*) FROM call_credit_transactions
                WHERE account_id = :account_id AND transaction_type = 'call-credit-spend'
                """
            ),
            {"account_id": caller_id},
        ).scalar_one() == 3
    finally:
        generator.close()


def test_call_lifecycle_ends_stale_connecting_calls(api_client, monkeypatch) -> None:
    client, _ = api_client
    caller_id = _create_viewer(client, monkeypatch)
    callee_id = _create_candidate(client)
    client.app.state.settings.livekit_url = "wss://livekit.example.test"
    client.app.state.settings.livekit_api_key = "api-key"
    from pydantic import SecretStr

    client.app.state.settings.livekit_api_secret = SecretStr("api-secret")
    monkeypatch.setattr(calls, "delete_room", lambda *_args: None)
    csrf = client.cookies["flingra_csrf"]
    db, generator = _session(client)
    try:
        db.execute(
            text("INSERT INTO wallet_accounts (account_id, balance_kobo) VALUES (:id, 500000)"),
            {"id": caller_id},
        )
        db.commit()
    finally:
        generator.close()
    purchase = client.post(
        "/calls/credits/purchase",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "stale-call-purchase"},
        json={"coins": 10},
    )
    assert purchase.status_code == 201
    started = client.post(
        "/calls",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "stale-call-key"},
        json={"targetId": callee_id, "callType": "audio"},
    )
    assert started.status_code == 201
    call_id = started.json()["callId"]
    db, generator = _session(client)
    try:
        db.execute(
            text(
                "UPDATE call_sessions SET status = 'connecting', created_at = :created_at WHERE id = :id"
            ),
            {
                "created_at": datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=31),
                "id": call_id,
            },
        )
        db.commit()
        calls.process_call_lifecycle(db, client.app.state.settings)
        assert db.execute(
            text("SELECT status FROM call_sessions WHERE id = :id"),
            {"id": call_id},
        ).scalar_one() == "ended"
    finally:
        generator.close()


def test_video_unlock_uses_creator_price_and_credits_creator(api_client, monkeypatch) -> None:
    client, _ = api_client
    viewer_id = _create_viewer(client, monkeypatch)
    creator_id = _create_candidate(client)
    media_id = uuid.uuid4().hex
    object_key = f"accounts/{creator_id}/profile-videos/{media_id}"
    storage = client.app.state.media_storage
    storage.put(object_key, b"private video", "video/mp4")
    db, generator = _session(client)
    try:
        db.execute(
            text(
                """
                INSERT INTO media_objects (
                    id, account_id, purpose, object_key, content_type, size_bytes, sha256
                )
                VALUES (:id, :account_id, 'profile-video', :object_key, 'video/mp4', 13, 'hash')
                """
            ),
            {"id": media_id, "account_id": creator_id, "object_key": object_key},
        )
        db.execute(
            text("UPDATE profiles SET videos = :videos WHERE account_id = :id"),
            {
                "videos": json.dumps(
                    [{"url": f"/media/{media_id}", "locked": True, "priceNaira": 1250}]
                ),
                "id": creator_id,
            },
        )
        db.execute(
            text("INSERT INTO wallet_accounts (account_id, balance_kobo) VALUES (:id, 400000)"),
            {"id": viewer_id},
        )
        db.commit()
    finally:
        generator.close()

    media_url = f"/media/{media_id}"
    csrf = client.cookies["flingra_csrf"]
    headers = {"X-CSRF-Token": csrf}
    invalid_price = client.patch(
        "/profiles/me",
        headers=headers,
        json={"videos": [{"url": media_url, "locked": True, "priceNaira": 3001}]},
    )
    assert invalid_price.status_code == 422

    assert client.get(media_url, follow_redirects=False).status_code == 404
    unlocked = client.post(
        "/videos/unlock",
        headers=headers,
        json={"url": media_url, "priceNaira": 1, "authorName": "untrusted"},
    )
    assert unlocked.status_code == 200, unlocked.json()
    assert unlocked.json() == {"url": media_url, "unlocked": True, "priceNaira": 1250}
    assert client.post("/videos/unlock", headers=headers, json={"url": media_url}).json() == unlocked.json()
    assert client.get("/videos/unlocks").json() == [media_url]
    assert client.get("/wallet/balance").json() == {"balanceNaira": 2750}

    db, generator = _session(client)
    try:
        assert db.execute(
            text("SELECT balance_kobo FROM wallet_accounts WHERE account_id = :id"),
            {"id": creator_id},
        ).scalar_one() == 125000
    finally:
        generator.close()
    assert client.get(media_url, follow_redirects=False).status_code == 307
    db, generator = _session(client)
    try:
        db.execute(
            text(
                """
                UPDATE video_unlocks SET expires_at = :expired
                WHERE viewer_id = :viewer AND media_id = :media
                """
            ),
            {
                "expired": datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1),
                "viewer": viewer_id,
                "media": media_id,
            },
        )
        db.commit()
    finally:
        generator.close()
    assert client.get(media_url, follow_redirects=False).status_code == 404
    renewed = client.post("/videos/unlock", headers=headers, json={"url": media_url})
    assert renewed.status_code == 200, renewed.json()
    assert client.get("/wallet/balance").json() == {"balanceNaira": 1500}
    assert client.get(media_url, follow_redirects=False).status_code == 307
    invalid = client.post(
        "/videos/unlock",
        headers=headers,
        json={"url": "https://example.test/video.mp4"},
    )
    assert invalid.status_code == 404


def test_call_worker_continues_room_cleanup_after_provider_failure(api_client, monkeypatch) -> None:
    client, _ = api_client
    caller_id = _create_viewer(client, monkeypatch)
    callee_id = _create_candidate(client)
    now = datetime.now(UTC).replace(tzinfo=None)
    db, generator = _session(client)
    try:
        for call_id in ("failed-room", "healthy-room"):
            db.execute(
                text(
                    """
                    INSERT INTO call_sessions (
                        id, caller_id, callee_id, room_name, call_type, status,
                        ended_at, created_at
                    )
                    VALUES (:id, :caller_id, :callee_id, :room, 'audio', 'declined', :now, :now)
                    """
                ),
                {
                    "id": call_id,
                    "caller_id": caller_id,
                    "callee_id": callee_id,
                    "room": call_id,
                    "now": now,
                },
            )
        db.commit()
    finally:
        generator.close()

    def close_room(_settings, room_name: str) -> None:
        if room_name == "failed-room":
            raise ServiceUnavailable("simulated LiveKit outage")

    monkeypatch.setattr(calls, "delete_room", close_room)
    db, generator = _session(client)
    try:
        with pytest.raises(ServiceUnavailable):
            calls.process_call_lifecycle(db, client.app.state.settings)
        closed = db.execute(
            text("SELECT room_name FROM call_sessions WHERE room_closed_at IS NOT NULL")
        ).scalars().all()
        assert "healthy-room" in closed
        assert "failed-room" not in closed
    finally:
        generator.close()
