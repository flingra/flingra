import json
import uuid

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


def test_interest_requires_woman_approval_before_chat(api_client, monkeypatch) -> None:
    client, _ = api_client
    sender_id = _create_viewer(client, monkeypatch)
    target_id = _create_candidate(client)
    csrf = client.cookies["flingra_csrf"]
    db, generator = _session(client)
    try:
        session_id = db.execute(
            text("SELECT id FROM sessions WHERE account_id = :account_id"),
            {"account_id": sender_id},
        ).scalar_one()
    finally:
        generator.close()

    first = client.post(
        "/chat/interests",
        headers={"X-CSRF-Token": csrf},
        json={"targetId": target_id},
    )
    second = client.post(
        "/chat/interests",
        headers={"X-CSRF-Token": csrf},
        json={"targetId": target_id},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    interest_id = first.json()["id"]
    assert first.json()["status"] == "pending"
    assert client.get("/chat/threads").json() == []
    blocked_thread = client.post(
        "/chat/threads",
        headers={"X-CSRF-Token": csrf},
        json={"otherId": target_id},
    )
    assert blocked_thread.status_code == 403
    assert blocked_thread.json()["error"]["code"] == "INTEREST_NOT_ACCEPTED"

    thread_id = uuid.uuid4().hex
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
        assert [event["event_type"] for event in events] == ["chat.interest_received"]
        assert json.loads(events[0]["payload_json"]) == {
            "interestId": interest_id,
            "senderName": "Viewer",
        }
        left, right = sorted((sender_id, target_id))
        db.execute(
            text(
                """
                INSERT INTO chat_threads (id, participant_a_id, participant_b_id)
                VALUES (:id, :left, :right)
                """
            ),
            {"id": thread_id, "left": left, "right": right},
        )
        db.commit()
    finally:
        generator.close()

    assert client.get("/chat/threads").json() == []
    blocked_message = client.post(
        f"/chat/threads/{thread_id}/messages",
        headers={"X-CSRF-Token": csrf},
        json={"text": "Hello before acceptance"},
    )
    assert blocked_message.status_code == 403
    assert blocked_message.json()["error"]["code"] == "INTEREST_NOT_ACCEPTED"

    db, generator = _session(client)
    try:
        db.execute(
            text("UPDATE sessions SET account_id = :recipient_id WHERE id = :session_id"),
            {"recipient_id": target_id, "session_id": session_id},
        )
        db.commit()
    finally:
        generator.close()

    requests = client.get("/chat/interests")
    assert requests.status_code == 200
    assert [request["id"] for request in requests.json()] == [interest_id]
    woman_interest = client.post(
        "/chat/interests",
        headers={"X-CSRF-Token": csrf},
        json={"targetId": sender_id},
    )
    assert woman_interest.status_code == 403
    assert woman_interest.json()["error"]["code"] == "INTEREST_DIRECTION_RESTRICTED"

    accepted = client.post(
        f"/chat/interests/{interest_id}/accept",
        headers={"X-CSRF-Token": csrf},
    )
    assert accepted.status_code == 200
    thread_id = accepted.json()["id"]
    assert client.get("/chat/threads").json()[0]["id"] == thread_id
    accepted_again = client.post(
        f"/chat/interests/{interest_id}/accept",
        headers={"X-CSRF-Token": csrf},
    )
    assert accepted_again.status_code == 200
    assert accepted_again.json()["id"] == thread_id

    db, generator = _session(client)
    try:
        assert db.execute(
            text(
                "SELECT COUNT(*) FROM realtime_events "
                "WHERE recipient_id = :recipient_id AND event_type = 'chat.interest_accepted'"
            ),
            {"recipient_id": sender_id},
        ).scalar_one() == 1
        db.execute(
            text("UPDATE sessions SET account_id = :sender_id WHERE id = :session_id"),
            {"sender_id": sender_id, "session_id": session_id},
        )
        db.commit()
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


def test_declined_interest_can_be_resent(api_client, monkeypatch) -> None:
    client, _ = api_client
    sender_id = _create_viewer(client, monkeypatch)
    recipient_id = _create_candidate(client)
    csrf = client.cookies["flingra_csrf"]
    interest = client.post(
        "/chat/interests",
        headers={"X-CSRF-Token": csrf},
        json={"targetId": recipient_id},
    )
    assert interest.status_code == 201

    db, generator = _session(client)
    try:
        session_id = db.execute(
            text("SELECT id FROM sessions WHERE account_id = :account_id"),
            {"account_id": sender_id},
        ).scalar_one()
        db.execute(
            text("UPDATE sessions SET account_id = :recipient_id WHERE id = :session_id"),
            {"recipient_id": recipient_id, "session_id": session_id},
        )
        db.commit()
    finally:
        generator.close()

    declined = client.post(
        f"/chat/interests/{interest.json()['id']}/decline",
        headers={"X-CSRF-Token": csrf},
    )
    assert declined.status_code == 204

    db, generator = _session(client)
    try:
        db.execute(
            text("UPDATE sessions SET account_id = :sender_id WHERE id = :session_id"),
            {"sender_id": sender_id, "session_id": session_id},
        )
        db.commit()
    finally:
        generator.close()

    repeated = client.post(
        "/chat/interests",
        headers={"X-CSRF-Token": csrf},
        json={"targetId": recipient_id},
    )
    assert repeated.status_code == 201
    assert repeated.json()["id"] == interest.json()["id"]
    assert repeated.json()["status"] == "pending"
    assert client.get("/chat/threads").json() == []
    db, generator = _session(client)
    try:
        assert db.execute(
            text(
                "SELECT COUNT(*) FROM realtime_events "
                "WHERE recipient_id = :recipient_id AND event_type = 'chat.interest_received'"
            ),
            {"recipient_id": recipient_id},
        ).scalar_one() == 2
    finally:
        generator.close()


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
