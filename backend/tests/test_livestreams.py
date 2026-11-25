import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text

from app import livekit
from app.dependencies import db_session
from app.errors import ServiceUnavailable
from app.routes import auth, livestreams
from app.security import hash_password
from test_discovery import _create_candidate


def _session(client):
    generator = client.app.dependency_overrides[db_session]()
    return next(generator), generator


def test_live_stream_lifecycle_issues_restricted_livekit_tokens(api_client, monkeypatch) -> None:
    client, delivered_codes = api_client
    monkeypatch.setattr(
        auth,
        "send_verification_code",
        lambda _settings, _recipient, code: delivered_codes.append(code),
    )
    signup = client.post(
        "/auth/signup",
        json={
            "sex": "woman",
            "identifier": "streamer@example.test",
            "password": "secure-password-123",
            "dateOfBirth": "1995-02-10",
            "acceptedTerms": True,
        },
    )
    assert signup.status_code == 201
    verified = client.post(
        "/auth/verify-contact",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        json={"code": delivered_codes[0]},
    )
    assert verified.status_code == 200
    account_id = client.get("/auth/session").json()["accountId"]
    db, generator = _session(client)
    try:
        db.execute(
            text(
                """
                UPDATE profiles
                SET display_name = 'Streamer', photos = '[]', bio = '', interests = '[]',
                    onboarding_complete = TRUE, moderation_status = 'approved',
                    document_verification = 'verified'
                WHERE account_id = :account_id
                """
            ),
            {"account_id": account_id},
        )
        db.commit()
    finally:
        generator.close()

    client.app.state.settings.livekit_url = "wss://livekit.example.test"
    client.app.state.settings.livekit_api_key = "api-key"
    client.app.state.settings.livekit_api_secret = SecretStr("api-secret")
    started = client.post(
        "/live-streams",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        json={"title": "Test stream"},
    )
    assert started.status_code == 201, started.json()
    stream = started.json()
    assert stream["hostId"] == account_id
    assert stream["title"] == "Test stream"
    assert stream["liveKitUrl"] == "wss://livekit.example.test"

    token_payload = stream["token"].split(".")[1]
    decoded = base64.urlsafe_b64decode(token_payload + "=" * (-len(token_payload) % 4))
    claims = json.loads(decoded)
    assert claims["iss"] == "api-key"
    assert claims["sub"] == account_id
    assert claims["video"]["roomJoin"] is True
    assert claims["video"]["canPublish"] is True
    assert client.get("/live-streams").json()[0]["id"] == stream["id"]
    assert client.get(f"/presence/{account_id}").json() == {
        "hasStatus": False,
        "isLive": True,
        "streamId": stream["id"],
    }

    requests: list[httpx.Request] = []
    responses = [httpx.Response(503), httpx.Response(200, json={})]
    transport = httpx.MockTransport(
        lambda request: requests.append(request) or responses.pop(0)
    )
    original_client = httpx.Client
    monkeypatch.setattr(
        livekit.httpx,
        "Client",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )
    failed_end = client.delete(
        f"/live-streams/{stream['id']}",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
    )
    assert failed_end.status_code == 503
    db, generator = _session(client)
    try:
        durable_state = db.execute(
            text("SELECT status, room_closed_at FROM live_streams WHERE id = :id"),
            {"id": stream["id"]},
        ).one()
        assert durable_state.status == "ended"
        assert durable_state.room_closed_at is None
    finally:
        generator.close()
    ended = client.delete(
        f"/live-streams/{stream['id']}",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
    )
    assert ended.status_code == 204
    assert requests[0].url.path.endswith("/twirp/livekit.RoomService/DeleteRoom")
    assert len(requests) == 2
    assert client.get("/live-streams").json() == []
    assert client.get(f"/presence/{account_id}").json()["isLive"] is False

    next_stream = client.post(
        "/live-streams",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        json={"title": "Worker cleanup"},
    )
    assert next_stream.status_code == 201, next_stream.json()
    db, generator = _session(client)
    try:
        db.execute(
            text(
                """
                UPDATE live_stream_participants
                SET last_seen_at = :last_seen
                WHERE stream_id = :stream_id AND account_id = :account_id
                """
            ),
            {
                "last_seen": datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=61),
                "stream_id": next_stream.json()["id"],
                "account_id": account_id,
            },
        )
        db.commit()
    finally:
        generator.close()
    monkeypatch.setattr(livestreams, "delete_room", lambda *_args: None)
    db, generator = _session(client)
    try:
        assert livestreams.process_live_stream_lifecycle(
            db, client.app.state.settings
        ) == 1
        stream_status = db.execute(
            text("SELECT status, room_closed_at FROM live_streams WHERE id = :id"),
            {"id": next_stream.json()["id"]},
        ).one()
        assert stream_status.status == "ended"
        assert stream_status.room_closed_at is not None
    finally:
        generator.close()


def test_livekit_token_requires_credentials(api_client) -> None:
    client, _ = api_client
    with pytest.raises(ServiceUnavailable):
        livekit.create_room_token(
            client.app.state.settings,
            room_name="room",
            identity="account",
            can_publish=False,
        )


def test_livestream_join_capacity_presence_chat_and_gifts(api_client, monkeypatch) -> None:
    client, delivered_codes = api_client
    monkeypatch.setattr(
        auth,
        "send_verification_code",
        lambda _settings, _recipient, code: delivered_codes.append(code),
    )
    signup = client.post(
        "/auth/signup",
        json={
            "sex": "woman",
            "identifier": "host@example.test",
            "password": "secure-password-123",
            "dateOfBirth": "1995-02-10",
            "acceptedTerms": True,
        },
    )
    assert signup.status_code == 201
    verified = client.post(
        "/auth/verify-contact",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        json={"code": delivered_codes[0]},
    )
    assert verified.status_code == 200
    host_id = client.get("/auth/session").json()["accountId"]
    db, generator = _session(client)
    try:
        db.execute(
            text(
                """
                UPDATE profiles
                SET display_name = 'Host', photos = '[]', bio = '', interests = '[]',
                    discoverable_by = 'everyone', wants_to_discover = 'everyone',
                    onboarding_complete = TRUE, moderation_status = 'approved',
                    document_verification = 'verified'
                WHERE account_id = :account_id
                """
            ),
            {"account_id": host_id},
        )
        db.commit()
    finally:
        generator.close()

    client.app.state.settings.livekit_url = "wss://livekit.example.test"
    client.app.state.settings.livekit_api_key = "api-key"
    client.app.state.settings.livekit_api_secret = SecretStr("api-secret")
    host_csrf = client.cookies["flingra_csrf"]
    started = client.post(
        "/live-streams",
        headers={"X-CSRF-Token": host_csrf},
        json={"title": "Community stream"},
    )
    assert started.status_code == 201, started.json()
    stream_id = started.json()["id"]

    def create_candidate() -> str:
        account_id = _create_candidate(
            client,
            identity="man",
            discoverable_by="women",
            wants_to_discover="women",
        )
        db, generator = _session(client)
        try:
            email = db.execute(
                text("SELECT email FROM accounts WHERE id = :id"),
                {"id": account_id},
            ).scalar_one()
            db.execute(
                text("UPDATE accounts SET password_hash = :password WHERE id = :id"),
                {"password": hash_password("candidate-password-123"), "id": account_id},
            )
            db.commit()
        finally:
            generator.close()
        return account_id

    first_guest_id = create_candidate()
    guest = TestClient(client.app)
    try:
        login = guest.post(
            "/auth/login",
            json={
                "identifier": f"{first_guest_id}@example.test",
                "password": "candidate-password-123",
            },
        )
        assert login.status_code == 200, login.json()
        guest_csrf = guest.cookies["flingra_csrf"]
        viewer_token = guest.post(
            f"/live-streams/{stream_id}/token",
            headers={"X-CSRF-Token": guest_csrf},
        )
        assert viewer_token.status_code == 200, viewer_token.json()
        viewer_claims = json.loads(
            base64.urlsafe_b64decode(
                viewer_token.json()["token"].split(".")[1]
                + "=" * (-len(viewer_token.json()["token"].split(".")[1]) % 4)
            )
        )
        assert viewer_claims["video"]["canPublish"] is False

        join_request = guest.post(
            f"/live-streams/{stream_id}/join-requests",
            headers={"X-CSRF-Token": guest_csrf},
        )
        assert join_request.status_code == 201, join_request.json()
        listed = client.get(f"/live-streams/{stream_id}/join-requests")
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == join_request.json()["id"]
        accepted = client.patch(
            f"/live-streams/{stream_id}/join-requests/{join_request.json()['id']}",
            headers={"X-CSRF-Token": host_csrf},
            json={"accept": True},
        )
        assert accepted.status_code == 200, accepted.json()
        assert accepted.json()["status"] == "accepted"
        guest_token = guest.post(
            f"/live-streams/{stream_id}/token",
            headers={"X-CSRF-Token": guest_csrf},
        )
        claims = json.loads(
            base64.urlsafe_b64decode(
                guest_token.json()["token"].split(".")[1]
                + "=" * (-len(guest_token.json()["token"].split(".")[1]) % 4)
            )
        )
        assert claims["video"]["canPublish"] is True
        assert {member["id"] for member in client.get(f"/live-streams/{stream_id}/participants").json()} == {
            host_id,
            first_guest_id,
        }

        db, generator = _session(client)
        try:
            db.execute(
                text(
                    """
                    INSERT INTO gift_inventory (account_id, gift_type_id, quantity)
                    VALUES (:account_id, 'rose', 1)
                    """
                ),
                {"account_id": first_guest_id},
            )
            db.commit()
        finally:
            generator.close()
        gift_message = guest.post(
            f"/live-streams/{stream_id}/messages",
            headers={"X-CSRF-Token": guest_csrf},
            json={"text": "sent rose", "kind": "gift", "giftId": "rose"},
        )
        assert gift_message.status_code == 201, gift_message.json()
        assert gift_message.json()["giftId"] == "rose"
        assert client.get(f"/live-streams/{stream_id}/messages").json()[-1]["kind"] == "gift"
    finally:
        guest.close()

    for _ in range(3):
        guest_id = create_candidate()
        request_id = uuid.uuid4().hex
        db, generator = _session(client)
        try:
            db.execute(
                text(
                    """
                    INSERT INTO live_stream_join_requests
                        (id, stream_id, requester_id, status)
                    VALUES (:id, :stream_id, :requester_id, 'pending')
                    """
                ),
                {"id": request_id, "stream_id": stream_id, "requester_id": guest_id},
            )
            db.commit()
        finally:
            generator.close()
        response = client.patch(
            f"/live-streams/{stream_id}/join-requests/{request_id}",
            headers={"X-CSRF-Token": host_csrf},
            json={"accept": True},
        )
        assert response.status_code == 200, response.json()

    full_candidate = create_candidate()
    full_request_id = uuid.uuid4().hex
    db, generator = _session(client)
    try:
        db.execute(
            text(
                """
                INSERT INTO live_stream_join_requests
                    (id, stream_id, requester_id, status)
                VALUES (:id, :stream_id, :requester_id, 'pending')
                """
            ),
            {
                "id": full_request_id,
                "stream_id": stream_id,
                "requester_id": full_candidate,
            },
        )
        db.commit()
    finally:
        generator.close()
    full = client.patch(
        f"/live-streams/{stream_id}/join-requests/{full_request_id}",
        headers={"X-CSRF-Token": host_csrf},
        json={"accept": True},
    )
    assert full.status_code == 409
    assert full.json()["error"]["code"] == "STREAM_FULL"
