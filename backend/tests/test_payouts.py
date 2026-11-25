import hashlib
import hmac
import json

import httpx
from pydantic import SecretStr
from sqlalchemy import text

from app import paystack
from app.dependencies import db_session
from test_discovery import _create_viewer


SECRET = "sk_test_paystack"


def _session(client):
    generator = client.app.dependency_overrides[db_session]()
    return next(generator), generator


def test_paystack_payout_saves_only_masked_bank_details_and_refunds_failed_transfer(
    api_client, monkeypatch
) -> None:
    client, _ = api_client
    account_id = _create_viewer(client, monkeypatch)
    client.app.state.settings.payment_provider = "paystack"
    client.app.state.settings.paystack_secret_key = SecretStr(SECRET)
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/bank":
            data = [{"code": "058", "name": "Guaranty Trust Bank"}]
        elif request.url.path == "/bank/resolve":
            data = {"account_name": "Test Customer", "account_number": "0123456789"}
        elif request.url.path == "/transferrecipient":
            data = {"recipient_code": "RCP_test"}
        elif request.url.path == "/transfer":
            data = {
                "reference": json.loads(request.content)["reference"],
                "transfer_code": "TRF_test",
                "status": "pending",
            }
        else:
            raise AssertionError(f"Unexpected Paystack request: {request.url.path}")
        return httpx.Response(200, json={"status": True, "data": data})

    transport = httpx.MockTransport(handle)
    original_client = httpx.Client
    monkeypatch.setattr(
        paystack.httpx,
        "Client",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )
    csrf = client.cookies["flingra_csrf"]
    bank_response = client.put(
        "/payout/bank-account",
        headers={"X-CSRF-Token": csrf},
        json={"accountNumber": "0123456789", "bankCode": "058"},
    )
    assert bank_response.status_code == 200
    assert bank_response.json()["accountNumberMasked"] == "****6789"

    db, generator = _session(client)
    try:
        db.execute(
            text(
                "INSERT INTO wallet_accounts (account_id, balance_kobo) VALUES (:id, 300000)"
            ),
            {"id": account_id},
        )
        db.commit()
    finally:
        generator.close()

    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": "payout-test-001"}
    first = client.post("/payouts", headers=headers, json={"amountNaira": 1500})
    duplicate = client.post("/payouts", headers=headers, json={"amountNaira": 1500})
    assert first.status_code == 201
    assert duplicate.status_code == 201
    assert duplicate.json()["reference"] == first.json()["reference"]
    assert first.json()["status"] == "pending"
    assert len([item for item in requests if item.url.path == "/transfer"]) == 1
    assert client.get("/wallet/balance").json()["balanceNaira"] == 1500

    bank = client.get("/payout/bank-account").json()
    assert bank["accountNumberMasked"] == "****6789"
    db, generator = _session(client)
    try:
        saved = db.execute(
            text(
                "SELECT recipient_code, account_last4 FROM payout_bank_accounts "
                "WHERE account_id = :account_id"
            ),
            {"account_id": account_id},
        ).one()
        assert saved.recipient_code == "RCP_test"
        assert saved.account_last4 == "6789"
    finally:
        generator.close()

    webhook = json.dumps(
        {
            "event": "transfer.failed",
            "data": {"reference": first.json()["reference"], "status": "failed"},
        },
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(SECRET.encode(), webhook, hashlib.sha512).hexdigest()
    webhook_headers = {"content-type": "application/json", "x-paystack-signature": signature}
    failed = client.post("/webhooks/paystack", content=webhook, headers=webhook_headers)
    duplicate_failure = client.post("/webhooks/paystack", content=webhook, headers=webhook_headers)

    assert failed.status_code == 200
    assert failed.json() == {"status": "processed"}
    assert duplicate_failure.json() == {"status": "ignored"}
    assert client.get("/wallet/balance").json()["balanceNaira"] == 3000
    assert [item["type"] for item in client.get("/wallet/transactions").json()] == [
        "payout-refund",
        "payout",
    ]
