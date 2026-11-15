import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.dependencies import db_session
from app.security import hash_password


def seed_admin(client, email="reviewer@example.test", password="a-very-long-admin-password") -> str:
    db_generator = client.app.dependency_overrides[db_session]()
    db = next(db_generator)
    admin_id = uuid.uuid4().hex
    try:
        db.execute(
            text(
                """
                INSERT INTO admin_users (id, email, password_hash)
                VALUES (:id, :email, :password_hash)
                """
            ),
            {"id": admin_id, "email": email, "password_hash": hash_password(password)},
        )
        db.commit()
    finally:
        db_generator.close()
    return admin_id


def seed_pending_document(client) -> tuple[str, str]:
    db_generator = client.app.dependency_overrides[db_session]()
    db = next(db_generator)
    account_id = uuid.uuid4().hex
    media_id = uuid.uuid4().hex
    try:
        db.execute(
            text(
                """
                INSERT INTO accounts (
                    id, email, identifier, identifier_type, password_hash, date_of_birth,
                    gender, terms_version, privacy_version, email_verified, account_state
                )
                VALUES (
                    :id, :email, :identifier, 'email', :password_hash, '1995-02-10',
                    'woman', 'v1', 'v1', TRUE, 'active'
                )
                """
            ),
            {
                "id": account_id,
                "email": "member@example.test",
                "identifier": "member@example.test",
                "password_hash": hash_password("secure-password-123"),
            },
        )
        db.execute(
            text(
                """
                INSERT INTO profiles (
                    account_id, display_name, bio, photos, age_range, interests, identity,
                    moderation_status, onboarding_complete, document_verification, document_type
                )
                VALUES (
                    :account_id, 'Member', 'Profile bio', '[]', '25–30', '[]', 'woman',
                    'pending', TRUE, 'pending', 'NIN'
                )
                """
            ),
            {"account_id": account_id},
        )
        db.execute(
            text(
                """
                INSERT INTO media_objects (
                    id, account_id, purpose, object_key, content_type, size_bytes, sha256
                )
                VALUES (:id, :account_id, 'identity-document', :object_key, 'image/jpeg', 20, :sha256)
                """
            ),
            {
                "id": media_id,
                "account_id": account_id,
                "object_key": f"accounts/{account_id}/identity-documents/{media_id}",
                "sha256": "a" * 64,
            },
        )
        db.commit()
    finally:
        db_generator.close()
    return account_id, media_id


def set_admin_role(client, admin_id: str, role: str) -> None:
    db_generator = client.app.dependency_overrides[db_session]()
    db = next(db_generator)
    try:
        db.execute(
            text("UPDATE admin_users SET role = :role WHERE id = :admin_id"),
            {"role": role, "admin_id": admin_id},
        )
        db.commit()
    finally:
        db_generator.close()


def admin_login(client, email="reviewer@example.test", password="a-very-long-admin-password"):
    return client.post("/admin/auth/login", json={"email": email, "password": password})


def test_admin_login_is_separate_and_csrf_protected(api_client) -> None:
    client, _ = api_client
    admin_id = seed_admin(client)

    assert client.get("/admin/reviews").status_code == 401
    response = admin_login(client)

    assert response.status_code == 200
    assert response.json() == {
        "adminId": admin_id,
        "email": "reviewer@example.test",
        "role": "reviewer",
    }
    cookie_headers = response.headers.get_list("set-cookie")
    assert any("flingra_admin_session=" in header and "HttpOnly" in header for header in cookie_headers)
    assert any("flingra_admin_session=" in header and "SameSite=lax" in header for header in cookie_headers)
    assert client.get("/admin/auth/session").json() == response.json()
    assert client.post("/admin/auth/signup").status_code == 404

    missing_csrf = client.post("/admin/auth/logout")
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["error"]["code"] == "CSRF_FAILED"

    csrf_token = client.cookies["flingra_admin_csrf"]
    logged_out = client.post(
        "/admin/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert logged_out.status_code == 204
    assert client.get("/admin/auth/session").json() is None


def test_admin_reviews_are_user_scoped_audited_and_paginated(api_client) -> None:
    client, _ = api_client
    account_id, media_id = seed_pending_document(client)
    admin_id = seed_admin(client)
    set_admin_role(client, admin_id, "super_admin")
    assert admin_login(client).status_code == 200
    csrf_token = client.cookies["flingra_admin_csrf"]

    queue = client.get("/admin/reviews", params={"type": "identity-document", "limit": 1})
    assert queue.status_code == 200
    review_id = f"document-{media_id}"
    assert queue.json() == {
        "items": [
            {
                "reviewId": review_id,
                "type": "identity-document",
                "accountId": account_id,
                "displayName": "Member",
                "status": "pending",
                "documentType": "NIN",
                "createdAt": queue.json()["items"][0]["createdAt"],
            }
        ],
        "nextOffset": None,
    }

    details = client.get(f"/admin/reviews/{review_id}")
    assert details.status_code == 200
    assert details.json()["status"] == "pending"
    assert details.json()["accountId"] == account_id

    document = client.get(
        f"/admin/reviews/{review_id}/document",
        follow_redirects=False,
    )
    assert document.status_code == 307
    assert "private, no-store" in document.headers["cache-control"]
    assert document.headers["location"].endswith(
        f"accounts/{account_id}/identity-documents/{media_id}"
    )

    decision = client.post(
        f"/admin/reviews/{review_id}/decision",
        headers={"X-CSRF-Token": csrf_token},
        json={"decision": "approved", "reason": "Document matches the account details."},
    )
    assert decision.status_code == 200
    assert decision.json() == {"reviewId": review_id, "status": "approved"}

    history = client.get(f"/admin/users/{account_id}/audit", params={"limit": 100})
    assert history.status_code == 200
    events = history.json()["items"]
    event_types = [event["eventType"] for event in events]
    assert "admin.review.queue_item_viewed" in event_types
    assert "admin.review.details_viewed" in event_types
    assert "admin.review.document_viewed" in event_types
    assert "admin.review.decided" in event_types
    assert "admin.audit.user_history_viewed" in event_types
    assert all(event["actorLabel"] == "reviewer@example.test" for event in events)
    assert all(len(event["requestId"]) == 32 for event in events)
    decision_event = next(event for event in events if event["eventType"] == "admin.review.decided")
    assert decision_event["metadata"]["reason"] == "Document matches the account details."

    db_generator = client.app.dependency_overrides[db_session]()
    db = next(db_generator)
    try:
        status = db.execute(
            text("SELECT document_verification FROM profiles WHERE account_id = :account_id"),
            {"account_id": account_id},
        ).scalar_one()
        assert status == "verified"
        stored_events = db.execute(
            text("SELECT metadata FROM platform_audit_events WHERE subject_account_id = :account_id"),
            {"account_id": account_id},
        ).scalars().all()
        assert all("secure-password-123" not in json.dumps(event) for event in stored_events)
    finally:
        db_generator.close()


def test_admin_login_failures_are_audited_without_exposing_credentials(api_client) -> None:
    client, _ = api_client
    seed_admin(client)

    response = admin_login(client, password="wrong-password")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_ADMIN_CREDENTIALS"
    assert "wrong-password" not in response.text

    db_generator = client.app.dependency_overrides[db_session]()
    db = next(db_generator)
    try:
        event = db.execute(
            text(
                """
                SELECT event_type, outcome, metadata, request_id
                FROM platform_audit_events
                WHERE event_type = 'admin.login'
                """
            )
        ).mappings().one()
        assert event["outcome"] == "failure"
        assert json.loads(event["metadata"]) == {"reason": "invalid_credentials"}
        assert len(event["request_id"]) == 32
    finally:
        db_generator.close()


def test_reviewer_role_cannot_access_audit_or_admin_management(api_client) -> None:
    client, _ = api_client
    seed_admin(client)
    assert admin_login(client).status_code == 200

    assert client.get("/admin/reviews").status_code == 200
    assert client.get("/admin/users/missing/audit").status_code == 403
    assert client.get("/admin/admins").status_code == 403


def test_super_admin_can_change_roles_and_disable_accounts(api_client) -> None:
    client, _ = api_client
    owner_id = seed_admin(client, email="owner@example.test")
    set_admin_role(client, owner_id, "super_admin")
    target_id = seed_admin(client, email="staff@example.test")
    assert admin_login(client, email="owner@example.test").status_code == 200
    csrf_token = client.cookies["flingra_admin_csrf"]

    changed = client.patch(
        f"/admin/admins/{target_id}",
        headers={"X-CSRF-Token": csrf_token},
        json={"role": "auditor"},
    )
    assert changed.status_code == 200
    assert changed.json()["role"] == "auditor"
    assert changed.json()["disabled"] is False

    self_update = client.patch(
        f"/admin/admins/{owner_id}",
        headers={"X-CSRF-Token": csrf_token},
        json={"role": "reviewer"},
    )
    assert self_update.status_code == 400
    assert self_update.json()["error"]["code"] == "ADMIN_SELF_UPDATE_DENIED"

    with TestClient(client.app) as staff_client:
        assert admin_login(staff_client, email="staff@example.test").json()["role"] == "auditor"
        assert staff_client.get("/admin/reviews").status_code == 403
        assert staff_client.get("/admin/users/missing/audit").status_code == 404

        admins = client.get("/admin/admins")
        assert admins.status_code == 200
        assert any(item["adminId"] == target_id for item in admins.json()["items"])

        disabled = client.patch(
            f"/admin/admins/{target_id}",
            headers={"X-CSRF-Token": csrf_token},
            json={"disabled": True},
        )
        assert disabled.status_code == 200
        assert disabled.json()["disabled"] is True
        assert staff_client.get("/admin/auth/session").json() is None
        assert staff_client.get("/admin/reviews").status_code == 401

    db_generator = client.app.dependency_overrides[db_session]()
    db = next(db_generator)
    try:
        audit_events = db.execute(
            text(
                """
                SELECT event_type FROM platform_audit_events
                WHERE event_type IN ('admin.account.updated', 'admin.authorization.denied')
                """
            )
        ).scalars().all()
        assert "admin.account.updated" in audit_events
        assert "admin.authorization.denied" in audit_events
    finally:
        db_generator.close()
