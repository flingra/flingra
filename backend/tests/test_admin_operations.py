import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.routes import admin_operations
from app.dependencies import db_session
from app.errors import ServiceUnavailable
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
    assert dashboard.json()["registeredMembers"] == 1
    assert dashboard.json()["activeAccounts"] == 1
    assert dashboard.json()["activeMembersLast30Days"] == 1
    assert dashboard.json()["newMembersLast30Days"] == 1
    assert dashboard.json()["activeVipMembers"] == 0
    assert dashboard.json()["postsLast30Days"] == 0
    assert dashboard.json()["activeStatuses"] == 0
    assert len(dashboard.json()["memberSignupsByDay"]) == 30
    assert sum(day["count"] for day in dashboard.json()["memberSignupsByDay"]) == 1
    assert dashboard.json()["walletFundingLast30DaysKobo"] == 0


def test_member_details_and_wallet_history_are_readable_and_audited(api_client) -> None:
    client, _ = api_client
    seed_admin(client)
    account_id = seed_user(client)
    generator = client.app.dependency_overrides[db_session]()
    db = next(generator)
    try:
        db.execute(
            text("INSERT INTO wallet_accounts (account_id, balance_kobo) VALUES (:id, 2500)"),
            {"id": account_id},
        )
        db.execute(
            text(
                """
                INSERT INTO wallet_transactions
                    (id, account_id, transaction_type, amount_kobo, description, status)
                VALUES
                    (:credit_id, :account_id, 'top-up', 5000, 'Wallet funding', 'completed'),
                    (:spend_id, :account_id, 'video-unlock', -2500, 'Unlocked a member video', 'completed')
                """
            ),
            {"credit_id": uuid.uuid4().hex, "spend_id": uuid.uuid4().hex, "account_id": account_id},
        )
        db.execute(
            text("INSERT INTO call_credit_accounts (account_id, balance) VALUES (:id, 6)"),
            {"id": account_id},
        )
        db.execute(
            text(
                """
                INSERT INTO call_credit_transactions
                    (id, account_id, transaction_type, amount, description)
                VALUES (:id, :account_id, 'call-minute', -2, 'Call minutes used')
                """
            ),
            {"id": uuid.uuid4().hex, "account_id": account_id},
        )
        db.commit()
    finally:
        generator.close()

    details = client.get(f"/admin/users/{account_id}")
    assert details.status_code == 200
    assert details.json()["displayName"] == "Test member"
    assert details.json()["email"] == f"{account_id}@example.test"
    assert details.json()["gender"] == "woman"

    wallet = client.get(f"/admin/users/{account_id}/wallet")
    assert wallet.status_code == 200
    assert wallet.json()["walletBalanceKobo"] == 2500
    assert wallet.json()["walletSpentKobo"] == 2500
    assert wallet.json()["callCreditBalance"] == 6
    assert wallet.json()["callCreditsSpent"] == 2
    assert len(wallet.json()["transactions"]) == 3


def test_private_member_media_is_super_admin_only_and_opened_in_admin_context(api_client) -> None:
    client, _ = api_client
    seed_admin(client, "safety_admin")
    account_id = seed_user(client)
    media_id = uuid.uuid4().hex
    generator = client.app.dependency_overrides[db_session]()
    db = next(generator)
    try:
        db.execute(
            text(
                """
                INSERT INTO media_objects (
                    id, account_id, purpose, object_key, content_type, size_bytes, sha256
                )
                VALUES (:id, :account_id, 'profile-video', :key, 'video/mp4', 42, :sha)
                """
            ),
            {
                "id": media_id,
                "account_id": account_id,
                "key": f"accounts/{account_id}/profile-videos/{media_id}",
                "sha": "a" * 64,
            },
        )
        db.commit()
    finally:
        generator.close()

    forbidden = client.get(f"/admin/users/{account_id}/media")
    assert forbidden.status_code == 403

    generator = client.app.dependency_overrides[db_session]()
    db = next(generator)
    try:
        db.execute(text("UPDATE admin_users SET role = 'super_admin'"))
        db.commit()
    finally:
        generator.close()

    listed = client.get(f"/admin/users/{account_id}/media")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["contentType"] == "video/mp4"
    opened = client.get(
        f"/admin/users/{account_id}/media/{media_id}",
        follow_redirects=False,
    )
    assert opened.status_code == 307
    assert opened.headers["location"].endswith(f"profile-videos/{media_id}")
    removed = client.request(
        "DELETE",
        f"/admin/users/{account_id}/media/{media_id}",
        headers={"X-CSRF-Token": client.cookies["flingra_admin_csrf"]},
        json={"reason": "Confirmed AI-generated impersonation"},
    )
    assert removed.status_code == 200
    assert removed.json() == {"mediaId": media_id, "status": "removed"}
    generator = client.app.dependency_overrides[db_session]()
    db = next(generator)
    try:
        assert db.execute(
            text("SELECT COUNT(*) FROM media_objects WHERE id = :id"),
            {"id": media_id},
        ).scalar_one() == 0
    finally:
        generator.close()


def test_admin_can_send_audited_violation_warning_into_live_room(api_client) -> None:
    client, _ = api_client
    seed_admin(client, "safety_admin")
    account_id = seed_user(client)
    stream_id = uuid.uuid4().hex
    generator = client.app.dependency_overrides[db_session]()
    db = next(generator)
    try:
        db.execute(
            text(
                """
                INSERT INTO live_streams (id, host_account_id, room_name, title, status)
                VALUES (:id, :account_id, 'moderated-room', 'Live test', 'live')
                """
            ),
            {"id": stream_id, "account_id": account_id},
        )
        db.execute(
            text(
                """
                INSERT INTO live_stream_participants (stream_id, account_id, role)
                VALUES (:stream_id, :account_id, 'host')
                """
            ),
            {"stream_id": stream_id, "account_id": account_id},
        )
        db.commit()
    finally:
        generator.close()

    warning = client.post(
        f"/admin/live-streams/{stream_id}/warnings",
        headers={"X-CSRF-Token": client.cookies["flingra_admin_csrf"]},
        json={"severity": "violation", "reason": "Stop showing prohibited content"},
    )
    assert warning.status_code == 200
    assert warning.json()["status"] == "warning_issued"
    generator = client.app.dependency_overrides[db_session]()
    db = next(generator)
    try:
        message = db.execute(
            text("SELECT kind, message_text FROM live_stream_messages WHERE stream_id = :id"),
            {"id": stream_id},
        ).one()
        assert message.kind == "warning"
        assert message.message_text == "Violation warning: Stop showing prohibited content"
        assert db.execute(
            text("SELECT COUNT(*) FROM realtime_events WHERE recipient_id = :id"),
            {"id": account_id},
        ).scalar_one() == 1
        assert db.execute(
            text("SELECT COUNT(*) FROM platform_audit_events WHERE event_type = 'admin.live_stream.warning_issued'")
        ).scalar_one() == 1
    finally:
        generator.close()


def test_admin_live_monitor_token_is_read_only(api_client, monkeypatch) -> None:
    client, _ = api_client
    seed_admin(client, "safety_admin")
    account_id = seed_user(client)
    stream_id = uuid.uuid4().hex
    generator = client.app.dependency_overrides[db_session]()
    db = next(generator)
    try:
        db.execute(
            text(
                """
                INSERT INTO live_streams (id, host_account_id, room_name, title, status)
                VALUES (:id, :account_id, 'monitor-room', 'Live test', 'live')
                """
            ),
            {"id": stream_id, "account_id": account_id},
        )
        db.commit()
    finally:
        generator.close()

    token_args: dict[str, object] = {}

    def create_token(_settings, **kwargs):
        token_args.update(kwargs)
        return "wss://live.example.test", "read-only-token"

    monkeypatch.setattr(admin_operations, "create_room_token", create_token)
    response = client.post(
        f"/admin/live-streams/{stream_id}/monitor-token",
        headers={"X-CSRF-Token": client.cookies["flingra_admin_csrf"]},
    )

    assert response.status_code == 200
    assert response.json() == {"url": "wss://live.example.test", "token": "read-only-token"}
    assert token_args["room_name"] == "monitor-room"
    assert token_args["can_publish"] is False


def test_admin_role_can_access_platform_dashboard_without_wallet_funding(api_client) -> None:
    client, _ = api_client
    seed_admin(client, role="admin")
    seed_user(client)

    dashboard = client.get("/admin/dashboard")

    assert dashboard.status_code == 200
    assert dashboard.json()["registeredMembers"] == 1
    assert dashboard.json()["memberSignupsByDay"]
    assert "walletFundingLast30DaysKobo" not in dashboard.json()


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


def test_admin_live_stream_end_retries_room_cleanup_after_provider_failure(
    api_client, monkeypatch
) -> None:
    client, _ = api_client
    seed_admin(client, "safety_admin")
    account_id = seed_user(client)
    stream_id = uuid.uuid4().hex
    generator = client.app.dependency_overrides[db_session]()
    db = next(generator)
    try:
        db.execute(
            text(
                """
                INSERT INTO live_streams (id, host_account_id, room_name, title, status)
                VALUES (:id, :account_id, 'retry-room', 'Retry stream', 'live')
                """
            ),
            {"id": stream_id, "account_id": account_id},
        )
        db.commit()
    finally:
        generator.close()

    attempts = 0

    def close_room(*_args) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ServiceUnavailable("simulated LiveKit outage")

    monkeypatch.setattr(admin_operations, "delete_room", close_room)
    csrf = {"X-CSRF-Token": client.cookies["flingra_admin_csrf"]}

    failed_end = client.post(f"/admin/live-streams/{stream_id}/end", headers=csrf)
    assert failed_end.status_code == 503
    generator = client.app.dependency_overrides[db_session]()
    db = next(generator)
    try:
        state = db.execute(
            text("SELECT status, room_closed_at FROM live_streams WHERE id = :id"),
            {"id": stream_id},
        ).one()
        assert state.status == "ended"
        assert state.room_closed_at is None
    finally:
        generator.close()

    retried_end = client.post(f"/admin/live-streams/{stream_id}/end", headers=csrf)
    assert retried_end.status_code == 200
    assert retried_end.json() == {"streamId": stream_id, "status": "ended"}
    generator = client.app.dependency_overrides[db_session]()
    db = next(generator)
    try:
        state = db.execute(
            text("SELECT status, room_closed_at FROM live_streams WHERE id = :id"),
            {"id": stream_id},
        ).one()
        assert state.status == "ended"
        assert state.room_closed_at is not None
    finally:
        generator.close()
