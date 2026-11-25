import json

import httpx
from pydantic import SecretStr
from sqlalchemy import text

from app import termii
from app.dependencies import db_session
from test_discovery import _create_viewer


def _session(client):
    generator = client.app.dependency_overrides[db_session]()
    return next(generator), generator


def _add_emergency_contact(client, phone: str = "08012345678") -> None:
    response = client.post(
        "/safety/emergency-contacts",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        json={"name": "Trusted contact", "phone": phone, "relationship": "Friend"},
    )
    assert response.status_code == 201


def test_safety_check_in_sends_termii_sms_and_records_delivery(api_client, monkeypatch) -> None:
    client, _ = api_client
    _create_viewer(client, monkeypatch)
    _add_emergency_contact(client)
    client.app.state.settings.termii_api_key = SecretStr("termii-test-key")
    client.app.state.settings.termii_sender_id = "Flingra"
    requests: list[httpx.Request] = []
    transport = httpx.MockTransport(
        lambda request: (
            requests.append(request) or httpx.Response(200, json={"code": "ok"})
        )
    )
    original_client = httpx.Client
    monkeypatch.setattr(
        termii.httpx,
        "Client",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    response = client.post(
        "/safety/check-ins",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        json={"message": "I need help", "locationLink": "https://maps.example.test/location"},
    )

    assert response.status_code == 201
    assert response.json()["notifiedContacts"] == ["Trusted contact"]
    assert response.json()["status"] == "sent"
    payload = json.loads(requests[0].content)
    assert payload["to"] == "2348012345678"
    assert payload["from"] == "Flingra"
    assert "I need help" in payload["sms"]
    assert "https://maps.example.test/location" in payload["sms"]
    assert requests[0].url == termii.TERMII_SEND_SMS_URL
    assert client.get("/safety/check-ins").json()[0]["notifiedContacts"] == ["Trusted contact"]


def test_unconfigured_termii_fails_closed_and_records_no_delivery(api_client, monkeypatch) -> None:
    client, _ = api_client
    _create_viewer(client, monkeypatch)
    _add_emergency_contact(client)

    response = client.post(
        "/safety/check-ins",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        json={"message": "Please call me"},
    )

    assert response.status_code == 503
    assert client.get("/safety/check-ins").json()[0]["status"] == "failed"
    db, generator = _session(client)
    try:
        assert db.execute(
            text("SELECT notified_contacts_json FROM safety_check_ins")
        ).scalar_one() == "[]"
    finally:
        generator.close()
