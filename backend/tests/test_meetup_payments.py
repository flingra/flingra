from sqlalchemy import text

from app.dependencies import db_session
from test_admin_audit import admin_login, seed_admin, set_admin_role
from test_discovery import _create_candidate, _create_viewer


def _session(client):
    generator = client.app.dependency_overrides[db_session]()
    return next(generator), generator


def test_meetup_payment_dispute_is_admin_resolved_and_ledger_safe(api_client, monkeypatch) -> None:
    client, _ = api_client
    payer_id = _create_viewer(client, monkeypatch)
    recipient_id = _create_candidate(client)
    csrf = client.cookies["flingra_csrf"]
    db, generator = _session(client)
    try:
        db.execute(
            text(
                "INSERT INTO wallet_accounts (account_id, balance_kobo) VALUES (:id, 250000)"
            ),
            {"id": payer_id},
        )
        db.commit()
        session_id = db.execute(
            text("SELECT id FROM sessions WHERE account_id = :account_id"),
            {"account_id": payer_id},
        ).scalar_one()
    finally:
        generator.close()

    thread = client.post(
        "/chat/threads",
        headers={"X-CSRF-Token": csrf},
        json={"otherId": recipient_id},
    )
    assert thread.status_code == 201
    proposal = client.post(
        f"/chat/threads/{thread.json()['id']}/payment-proposals",
        headers={"X-CSRF-Token": csrf},
        json={"amountNaira": 1200},
    )
    assert proposal.status_code == 201
    payment_id = proposal.json()["id"]
    assert proposal.json()["status"] == "proposed"

    db, generator = _session(client)
    try:
        assert db.execute(
            text("SELECT balance_kobo FROM wallet_accounts WHERE account_id = :id"),
            {"id": payer_id},
        ).scalar_one() == 250000
        db.execute(
            text("UPDATE sessions SET account_id = :recipient_id WHERE id = :session_id"),
            {"recipient_id": recipient_id, "session_id": session_id},
        )
        db.commit()
    finally:
        generator.close()

    accepted = client.post(
        f"/chat/meetup-payments/{payment_id}/accept",
        headers={"X-CSRF-Token": csrf},
    )
    assert accepted.status_code == 200, accepted.json()
    assert accepted.json()["status"] == "held"
    db, generator = _session(client)
    try:
        assert db.execute(
            text("SELECT balance_kobo FROM wallet_accounts WHERE account_id = :id"),
            {"id": payer_id},
        ).scalar_one() == 130000
    finally:
        generator.close()

    disputed = client.post(
        f"/chat/meetup-payments/{payment_id}/disputes",
        headers={"X-CSRF-Token": csrf},
        json={"reason": "The agreed meetup did not take place."},
    )
    assert disputed.status_code == 200
    assert disputed.json()["status"] == "disputed"
    assert client.post(
        f"/chat/meetup-payments/{payment_id}/release",
        headers={"X-CSRF-Token": csrf},
    ).status_code == 409

    admin_id = seed_admin(client)
    set_admin_role(client, admin_id, "super_admin")
    assert admin_login(client).status_code == 200
    admin_csrf = client.cookies["flingra_admin_csrf"]
    queue = client.get("/admin/meetup-payments/disputes")
    assert queue.status_code == 200
    assert queue.json()["items"][0]["id"] == payment_id
    resolution = client.post(
        f"/admin/meetup-payments/{payment_id}/resolve",
        headers={"X-CSRF-Token": admin_csrf},
        json={"resolution": "refund", "reason": "Payment claim reviewed."},
    )
    assert resolution.status_code == 200
    assert resolution.json()["status"] == "refunded"
    assert client.get(
        "/admin/meetup-payments/disputes"
    ).json()["items"] == []

    db, generator = _session(client)
    try:
        assert db.execute(
            text("SELECT balance_kobo FROM wallet_accounts WHERE account_id = :id"),
            {"id": payer_id},
        ).scalar_one() == 250000
        assert db.execute(
            text("SELECT status FROM meetup_payments WHERE id = :id"),
            {"id": payment_id},
        ).scalar_one() == "refunded"
        assert db.execute(
            text(
                "SELECT COUNT(*) FROM wallet_transactions WHERE transaction_type = 'meetup-payment-refunded'"
            )
        ).scalar_one() == 1
    finally:
        generator.close()
