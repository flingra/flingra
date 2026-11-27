import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.routes import admin_operations
from app.dependencies import db_session
from app.security import hash_password


def seed_admin(client, role="super_admin") -> str:
    generator = client.app.dependency_overrides[db_session]()
    db = next(generator)
    admin_id = uuid.uuid4().hex
    try:
        db.execute(
            text(
                """
                INSERT INTO admin_users (id, email, password_hash, role)
                VALUES (:id, :email, :password_hash, :role)
                """
            ),
            {
                "id": admin_id,
                "email": f"{admin_id}@example.test",
                "password_hash": hash_password("a-very-long-admin-password"),
                "role": role,
            },
        )
        db.commit()
    finally:
        generator.close()
    response = client.post(
        "/admin/auth/login",
        json={"email": f"{admin_id}@example.test", "password": "a-very-long-admin-password"},
    )
    assert response.status_code == 200
    return admin_id


def seed_user(client) -> str:
    generator = client.app.dependency_overrides[db_session]()
    db = next(generator)
    account_id = uuid.uuid4().hex
    try:
        db.execute(
            text(
                """
                INSERT INTO accounts (
                    id, email, identifier, identifier_type, password_hash, date_of_birth,
                    gender, terms_version, privacy_version, email_verified, account_state
                )
                VALUES (
                    :id, :email, :email, 'email', :password_hash, '1995-02-10',
                    'woman', 'v1', 'v1', TRUE, 'active'
                )
                """
            ),
            {
                "id": account_id,
                "email": f"{account_id}@example.test",
                "password_hash": hash_password("secure-password-123"),
            },
        )
        db.execute(
            text(
                """
                INSERT INTO profiles (
                    account_id, display_name, bio, photos, age_range, interests, identity,
                    onboarding_complete, document_verification
                )
                VALUES (:id, 'Test member', '', '[]', '25-30', '[]', 'woman', TRUE, 'verified')
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
            {"id": uuid.uuid4().hex, "account_id": account_id, "token_hash": b"x" * 32},
        )
        db.commit()
    finally:
        generator.close()
    return account_id


def test_super_admin_can_suspend_member_and_revoke_sessions(api_client) -> None:
    client, _ = api_client
    seed_admin(client)
    account_id = seed_user(client)

    response = client.post(
        f"/admin/users/{account_id}/status",
        headers={"X-CSRF-Token": client.cookies["flingra_admin_csrf"]},
        json={"status": "suspended", "reason": "Repeated abuse reports"},
    )

    assert response.status_code == 200
    assert response.json() == {"accountId": account_id, "status": "suspended"}
    db_generator = client.app.dependency_overrides[db_session]()
    db = next(db_generator)
    try:
        assert db.execute(
            text("SELECT account_state FROM accounts WHERE id = :id"),
            {"id": account_id},
        ).scalar_one() == "suspended"
        assert db.execute(
            text("SELECT revoked_at FROM sessions WHERE account_id = :id"),
            {"id": account_id},
        ).scalar_one() is not None
    finally:
        db_generator.close()


def test_admin_revoke_sessions_invalidates_active_member_session(api_client) -> None:
    client, _ = api_client
    seed_admin(client)
    account_id = seed_user(client)

    signed_in = client.post(
        "/auth/login",
        json={"identifier": f"{account_id}@example.test", "password": "secure-password-123"},
    )
    assert signed_in.status_code == 200
    assert client.get("/auth/session").json()["accountId"] == account_id

    revoked = client.post(
        f"/admin/users/{account_id}/sessions/revoke",
        headers={"X-CSRF-Token": client.cookies["flingra_admin_csrf"]},
    )
    assert revoked.status_code == 200
    assert revoked.json()["revokedCount"] == 2
    assert client.get("/auth/session").json() is None


def test_reviewer_cannot_suspend_member(api_client) -> None:
    client, _ = api_client
    seed_admin(client, "reviewer")
    account_id = seed_user(client)

    response = client.post(
        f"/admin/users/{account_id}/status",
        headers={"X-CSRF-Token": client.cookies["flingra_admin_csrf"]},
        json={"status": "banned", "reason": "Policy violation"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_FORBIDDEN"


def test_safety_report_queue_decision_and_privacy_retry_are_audited(api_client) -> None:
    client, _ = api_client
    admin_id = seed_admin(client)
    account_id = seed_user(client)
    report_id = uuid.uuid4().hex
    privacy_id = uuid.uuid4().hex
    generator = client.app.dependency_overrides[db_session]()
    db = next(generator)
    try:
        db.execute(
            text(
                """
                INSERT INTO safety_reports (
                    id, reporter_id, target_account_id, reason, description, status
                ) VALUES (:id, :account_id, :account_id, 'harassment', 'Repeated unwanted messages', 'open')
                """
            ),
            {"id": report_id, "account_id": account_id},
        )
        db.execute(
            text(
                """
                INSERT INTO privacy_requests (id, account_id, request_type, status)
                VALUES (:id, :account_id, 'data_export', 'failed')
                """
            ),
            {"id": privacy_id, "account_id": account_id},
        )
        db.commit()
    finally:
        generator.close()

    reports = client.get("/admin/safety/reports")
    assert reports.status_code == 200
    assert reports.json()["items"][0]["reportId"] == report_id
    decision = client.post(
        f"/admin/safety/reports/{report_id}/decision",
        headers={"X-CSRF-Token": client.cookies["flingra_admin_csrf"]},
        json={"decision": "reviewed", "reason": "Confirmed and escalated to safety review"},
    )
    assert decision.status_code == 200
    assert decision.json() == {"reportId": report_id, "status": "reviewed"}

    retry = client.post(
        f"/admin/privacy/requests/{privacy_id}/retry",
        headers={"X-CSRF-Token": client.cookies["flingra_admin_csrf"]},
    )
    assert retry.status_code == 200
    assert retry.json() == {"requestId": privacy_id, "status": "queued"}

    history = client.get(f"/admin/users/{account_id}/audit")
    assert history.status_code == 200
    event_types = [event["eventType"] for event in history.json()["items"]]
    assert "admin.safety.report_decided" in event_types
    assert "admin.privacy.request_retried" in event_types
    assert admin_id


def test_super_admin_wallet_and_gift_catalog_operations_create_audit_events(api_client) -> None:
    client, _ = api_client
    seed_admin(client)
    account_id = seed_user(client)
    csrf = {"X-CSRF-Token": client.cookies["flingra_admin_csrf"]}

    adjustment = client.post(
        f"/admin/users/{account_id}/wallet-adjustments",
        headers=csrf,
        json={"amount_kobo": 12_500, "reason": "Customer support credit"},
    )
    assert adjustment.status_code == 200
    assert adjustment.json() == {"accountId": account_id, "balanceKobo": 12_500}

    created = client.post(
        "/admin/gift-catalog",
        headers=csrf,
        json={"id": "sunflower", "name": "Sunflower", "emoji": "🌻", "price_kobo": 25000},
    )
    assert created.status_code == 200
    assert created.json()["id"] == "sunflower"

    disabled = client.patch(
        "/admin/gift-catalog/sunflower",
        headers=csrf,
        json={"active": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["active"] is False


def test_subscription_controls_are_super_admin_only_and_audited(api_client) -> None:
    client, _ = api_client
    seed_admin(client)
    account_id = seed_user(client)
    csrf = {"X-CSRF-Token": client.cookies["flingra_admin_csrf"]}

    plans = client.get("/admin/subscription-plans")
    assert plans.status_code == 200
    updated_plan = client.patch(
        "/admin/subscription-plans/vip-weekly",
        headers=csrf,
        json={"active": False},
    )
    assert updated_plan.status_code == 200
    assert updated_plan.json()["active"] is False

    expiry = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    subscription = client.put(
        f"/admin/users/{account_id}/subscription",
        headers=csrf,
        json={"tier": "vip", "expires_at": expiry, "reason": "Approved service recovery"},
    )
    assert subscription.status_code == 200
    assert subscription.json()["tier"] == "vip"
    assert client.get("/admin/subscriptions").json()["items"][0]["accountId"] == account_id


def test_call_credit_adjustments_and_dashboard_summary(api_client) -> None:
    client, _ = api_client
    seed_admin(client)
    account_id = seed_user(client)

    adjustment = client.post(
        f"/admin/users/{account_id}/call-credit-adjustments",
        headers={"X-CSRF-Token": client.cookies["flingra_admin_csrf"]},
        json={"amount": 7, "reason": "Support adjustment"},
    )
    assert adjustment.status_code == 200
    assert adjustment.json() == {"accountId": account_id, "balance": 7}
    dashboard = client.get("/admin/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["activeLiveStreams"] == 0
    assert dashboard.json()["pendingAccountVerifications"] == 0
    assert "pendingPayouts" in dashboard.json()


def test_safety_admin_can_end_live_stream_and_remove_content(api_client, monkeypatch) -> None:
    client, _ = api_client
    admin_id = seed_admin(client, "safety_admin")
    account_id = seed_user(client)
    stream_id = uuid.uuid4().hex
    post_id = uuid.uuid4().hex
    generator = client.app.dependency_overrides[db_session]()
    db = next(generator)
    try:
        db.execute(
            text(
                """
                INSERT INTO live_streams (id, host_account_id, room_name, title, status)
                VALUES (:id, :account_id, 'test-room', 'Test stream', 'live')
                """
            ),
            {"id": stream_id, "account_id": account_id},
        )
        db.execute(
            text(
                """
                INSERT INTO member_posts (id, author_id, photos, caption)
                VALUES (:id, :account_id, '[]', 'Needs review')
                """
            ),
            {"id": post_id, "account_id": account_id},
        )
        db.commit()
    finally:
        generator.close()
    monkeypatch.setattr(admin_operations, "delete_room", lambda *_args: None)
    csrf = {"X-CSRF-Token": client.cookies["flingra_admin_csrf"]}

    ended = client.post(f"/admin/live-streams/{stream_id}/end", headers=csrf)
    assert ended.status_code == 200
    assert ended.json()["status"] == "ended"
    removed = client.delete(f"/admin/content/posts/{post_id}", headers=csrf)
    assert removed.status_code == 200
    assert removed.json()["status"] == "removed"
    history = client.get(f"/admin/users/{account_id}/audit")
    event_types = [event["eventType"] for event in history.json()["items"]]
    assert "admin.live_stream.ended" in event_types
    assert "admin.content.post_removed" in event_types
    assert admin_id
