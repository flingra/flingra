import base64
import json

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import text

from app import livekit
from app.dependencies import db_session
from app.errors import ServiceUnavailable
from app.routes import auth


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
    transport = httpx.MockTransport(
        lambda request: requests.append(request) or httpx.Response(200, json={})
    )
    original_client = httpx.Client
    monkeypatch.setattr(
        livekit.httpx,
        "Client",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )
    ended = client.delete(
        f"/live-streams/{stream['id']}",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
    )
    assert ended.status_code == 204
    assert requests[0].url.path.endswith("/twirp/livekit.RoomService/DeleteRoom")
    assert client.get("/live-streams").json() == []
    assert client.get(f"/presence/{account_id}").json()["isLive"] is False


def test_livekit_token_requires_credentials(api_client) -> None:
    client, _ = api_client
    with pytest.raises(ServiceUnavailable):
        livekit.create_room_token(
            client.app.state.settings,
            room_name="room",
            identity="account",
            can_publish=False,
        )
