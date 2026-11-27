import hashlib
import hmac
import json
import logging

import httpx
from sqlalchemy import text
from pydantic import SecretStr

from app.dependencies import db_session
from app import paystack
from test_discovery import _create_viewer


SECRET = "sk_test_paystack"


def _session(client):
    generator = client.app.dependency_overrides[db_session]()
    return next(generator), generator


def _enable_paystack(client) -> None:
    client.app.state.settings.payment_provider = "paystack"
    client.app.state.settings.paystack_secret_key = SecretStr(SECRET)
    client.app.state.settings.frontend_url = "https://app.example.test"


def _mock_paystack(monkeypatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    original_client = httpx.Client
    monkeypatch.setattr(
        paystack.httpx,
        "Client",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )


def _signature(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha512).hexdigest()


def test_wallet_top_up_initializes_paystack_without_crediting_wallet(
    api_client, monkeypatch
) -> None:
    client, _ = api_client
    _create_viewer(client, monkeypatch)
    _enable_paystack(client)
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "status": True,
                "data": {
                    "reference": payload["reference"],
                    "authorization_url": "https://checkout.paystack.com/example",
                },
            },
        )

    _mock_paystack(monkeypatch, handle)
    csrf = client.cookies["flingra_csrf"]
    response = client.post(
        "/wallet/top-ups",
        headers={"X-CSRF-Token": csrf},
        json={"amountNaira": 1250},
    )

    assert response.status_code == 201, response.json()
    assert response.json()["authorizationUrl"] == "https://checkout.paystack.com/example"
    assert requests[0].url.path == "/transaction/initialize"
    assert requests[0].headers["authorization"] == f"Bearer {SECRET}"
    assert json.loads(requests[0].content)["amount"] == 125000
    assert json.loads(requests[0].content)["callback_url"] == "https://app.example.test/wallet"

    db, generator = _session(client)
    try:
        intent = db.execute(
            text("SELECT status, amount_kobo FROM wallet_payment_intents")
        ).one()
        assert intent.status == "pending"
        assert intent.amount_kobo == 125000
        assert db.execute(text("SELECT COUNT(*) FROM wallet_transactions")).scalar_one() == 0
    finally:
        generator.close()


def test_wallet_top_up_logs_paystack_http_status_without_response_body_or_secret(
    api_client, monkeypatch, caplog
) -> None:
    client, _ = api_client
    _create_viewer(client, monkeypatch)
    _enable_paystack(client)
    _mock_paystack(
        monkeypatch,
        lambda _request: httpx.Response(400, text="private provider response"),
    )
    caplog.set_level(logging.WARNING, logger="uvicorn.error")
    csrf = client.cookies["flingra_csrf"]

    response = client.post(
        "/wallet/top-ups",
        headers={"X-CSRF-Token": csrf},
        json={"amountNaira": 1250},
    )

    assert response.status_code == 503
    assert "Paystack transaction initialization returned HTTP 400." in caplog.text
    assert "private provider response" not in caplog.text
    assert SECRET not in caplog.text


def test_signed_paystack_webhook_settles_wallet_once(api_client, monkeypatch) -> None:
    client, _ = api_client
    account_id = _create_viewer(client, monkeypatch)
    _enable_paystack(client)
    initialized: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/transaction/initialize"):
            payload = json.loads(request.content)
            initialized.update(payload)
            data = {
                "reference": payload["reference"],
                "authorization_url": "https://checkout.paystack.com/example",
            }
        else:
            data = {
                "status": "success",
                "reference": initialized["reference"],
                "amount": initialized["amount"],
                "currency": "NGN",
            }
        return httpx.Response(200, json={"status": True, "data": data})

    _mock_paystack(monkeypatch, handle)
    csrf = client.cookies["flingra_csrf"]
    initialized_response = client.post(
        "/wallet/top-ups",
        headers={"X-CSRF-Token": csrf},
        json={"amountNaira": 750},
    )
    assert initialized_response.status_code == 201, initialized_response.json()
    reference = initialized_response.json()["reference"]

    body = json.dumps(
        {
            "event": "charge.success",
            "data": {
                "reference": reference,
                "status": "success",
                "amount": 75000,
                "currency": "NGN",
            },
        },
        separators=(",", ":"),
    ).encode()
    headers = {
        "content-type": "application/json",
        "x-paystack-signature": _signature(body),
    }

    first = client.post("/webhooks/paystack", content=body, headers=headers)
    duplicate = client.post("/webhooks/paystack", content=body, headers=headers)

    assert first.status_code == 200
    assert first.json() == {"status": "processed"}
    assert duplicate.status_code == 200
    assert duplicate.json() == {"status": "ignored"}
    assert client.get("/wallet/balance").json()["balanceNaira"] == 750

    db, generator = _session(client)
    try:
        assert db.execute(
            text("SELECT balance_kobo FROM wallet_accounts WHERE account_id = :account_id"),
            {"account_id": account_id},
        ).scalar_one() == 75000
        assert db.execute(text("SELECT COUNT(*) FROM wallet_transactions")).scalar_one() == 1
        assert db.execute(
            text("SELECT status FROM wallet_payment_intents WHERE reference = :reference"),
            {"reference": reference},
        ).scalar_one() == "settled"
    finally:
        generator.close()


def test_invalid_paystack_webhook_signature_cannot_settle_payment(api_client, monkeypatch) -> None:
    client, _ = api_client
    _create_viewer(client, monkeypatch)
    _enable_paystack(client)
    body = b'{"event":"charge.success","data":{"reference":"unknown"}}'

    response = client.post(
        "/webhooks/paystack",
        content=body,
        headers={"content-type": "application/json", "x-paystack-signature": "invalid"},
    )

    assert response.status_code == 401
