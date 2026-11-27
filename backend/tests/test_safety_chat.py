import json

from sqlalchemy import text

from app.dependencies import db_session
from test_admin_audit import admin_login, seed_admin, set_admin_role
from test_discovery import _create_candidate, _create_viewer


def _session(client):
    generator = client.app.dependency_overrides[db_session]()
    return next(generator), generator


def test_report_and_block_are_persisted_and_block_hides_profile(api_client, monkeypatch) -> None:
    client, _ = api_client
    _create_viewer(client, monkeypatch)
    target_id = _create_candidate(client)
    csrf = client.cookies["flingra_csrf"]

    response = client.post(
        "/safety/reports",
        headers={"X-CSRF-Token": csrf},
        json={
            "targetId": target_id,
            "reason": "harassment",
            "description": "Repeated unwanted messages",
            "alsoBlock": True,
        },
    )

    assert response.status_code == 201
    assert client.get("/safety/blocks").json()[0]["id"] == target_id
    assert target_id not in {profile["id"] for profile in client.get("/discovery").json()["items"]}
    blocked_again = client.post(
        "/safety/blocks",
        headers={"X-CSRF-Token": csrf},
        json={"targetId": target_id},
    )
    assert blocked_again.status_code == 204

    db, generator = _session(client)
    try:
        assert db.execute(text("SELECT COUNT(*) FROM safety_reports")).scalar_one() == 1
        assert db.execute(text("SELECT COUNT(*) FROM moderation_review_requests")).scalar_one() == 2
    finally:
        generator.close()


def test_chat_threads_are_idempotent_and_messages_require_membership(api_client, monkeypatch) -> None:
    client, _ = api_client
    _create_viewer(client, monkeypatch)
    target_id = _create_candidate(client)
    csrf = client.cookies["flingra_csrf"]

    first = client.post(
        "/chat/threads",
        headers={"X-CSRF-Token": csrf},
        json={"otherId": target_id, "notifyInterest": True},
    )
    second = client.post(
        "/chat/threads",
        headers={"X-CSRF-Token": csrf},
        json={"otherId": target_id, "notifyInterest": True},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    thread_id = first.json()["id"]
    db, generator = _session(client)
    try:
        events = db.execute(
            text(
                """
                SELECT event_type, payload_json FROM realtime_events
                WHERE recipient_id = :recipient_id ORDER BY id
                """
            ),
            {"recipient_id": target_id},
        ).mappings().all()
        assert [event["event_type"] for event in events] == ["chat.interest"]
        assert json.loads(events[0]["payload_json"]) == {
            "threadId": thread_id,
            "senderName": "Viewer",
        }
    finally:
        generator.close()

    sent = client.post(
        f"/chat/threads/{thread_id}/messages",
        headers={"X-CSRF-Token": csrf},
        json={"text": "Hello there"},
    )
    assert sent.status_code == 201
    assert sent.json()["text"] == "Hello there"
    assert client.get(f"/chat/threads/{thread_id}/messages").json()[0]["authorId"] == client.get(
        "/auth/session"
    ).json()["accountId"]


def test_safety_admin_can_review_and_resolve_report(api_client, monkeypatch) -> None:
    client, _ = api_client
    _create_viewer(client, monkeypatch)
    target_id = _create_candidate(client)
    user_csrf = client.cookies["flingra_csrf"]
    report = client.post(
        "/safety/reports",
        headers={"X-CSRF-Token": user_csrf},
        json={"targetId": target_id, "reason": "fake-profile", "alsoBlock": False},
    )
    assert report.status_code == 201

    admin_id = seed_admin(client)
    set_admin_role(client, admin_id, "safety_admin")
    assert admin_login(client).status_code == 200
    admin_csrf = client.cookies["flingra_admin_csrf"]
    queue = client.get("/admin/safety/reviews")
    assert queue.status_code == 200
    review_id = queue.json()["items"][0]["id"]

    decision = client.post(
        f"/admin/safety/reviews/{review_id}/decision",
        headers={"X-CSRF-Token": admin_csrf},
        json={"decision": "reviewed", "reason": "Reviewed against the report policy."},
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "reviewed"
    duplicate_decision = client.post(
        f"/admin/safety/reviews/{review_id}/decision",
        headers={"X-CSRF-Token": admin_csrf},
        json={"decision": "reviewed", "reason": "Reviewed against the report policy."},
    )
    assert duplicate_decision.status_code == 409
