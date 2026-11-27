import io
import json
import uuid
from datetime import UTC, datetime, timedelta

from PIL import Image
from sqlalchemy import text

from app.config import Settings
from app.dependencies import db_session
from app.privacy_worker import process_privacy_requests
from test_discovery import _create_candidate, _create_viewer


def _session(client):
    generator = client.app.dependency_overrides[db_session]()
    return next(generator), generator


def test_settings_sessions_password_and_privacy_requests(api_client, monkeypatch) -> None:
    client, _ = api_client
    account_id = _create_viewer(client, monkeypatch)
    csrf = client.cookies["flingra_csrf"]

    sessions = client.get("/settings/sessions")
    assert sessions.status_code == 200
    assert len(sessions.json()) == 1
    assert sessions.json()[0]["current"] is True

    changed = client.post(
        "/settings/password",
        headers={"X-CSRF-Token": csrf},
        json={"currentPassword": "secure-password-123", "newPassword": "new-secure-password-456"},
    )
    assert changed.status_code == 204
    old_login = client.post(
        "/auth/login",
        json={"identifier": "viewer@example.test", "password": "secure-password-123"},
    )
    assert old_login.status_code == 401

    export = client.post("/settings/data-export", headers={"X-CSRF-Token": csrf})
    assert export.status_code == 202
    assert export.json()["status"] == "queued"

    deletion = client.post("/settings/account/delete", headers={"X-CSRF-Token": csrf})
    assert deletion.status_code == 202
    db, generator = _session(client)
    try:
        assert db.execute(
            text("SELECT account_state FROM accounts WHERE id = :account_id"),
            {"account_id": account_id},
        ).scalar_one() == "deletion_requested"
        assert db.execute(
            text("SELECT COUNT(*) FROM privacy_requests WHERE account_id = :account_id"),
            {"account_id": account_id},
        ).scalar_one() == 2
    finally:
        generator.close()


def test_privacy_export_worker_completes_and_exposes_only_owner_data(api_client, monkeypatch) -> None:
    client, _ = api_client
    account_id = _create_viewer(client, monkeypatch)
    thread_id = uuid.uuid4().hex
    message_id = uuid.uuid4().hex
    db, generator = _session(client)
    try:
        db.execute(
            text(
                """
                INSERT INTO chat_threads (id, participant_a_id, participant_b_id)
                VALUES (:id, :account_id, 'another-account')
                """
            ),
            {"id": thread_id, "account_id": account_id},
        )
        db.execute(
            text(
                """
                INSERT INTO chat_messages (id, thread_id, author_id, message_text)
                VALUES (:id, :thread_id, :account_id, 'export this message')
                """
            ),
            {"id": message_id, "thread_id": thread_id, "account_id": account_id},
        )
        db.commit()
    finally:
        generator.close()

    response = client.post(
        "/settings/data-export",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
    )
    request_id = response.json()["requestId"]
    db, generator = _session(client)
    try:
        assert process_privacy_requests(db, Settings(database_url="sqlite://")) == 1
        assert process_privacy_requests(db, Settings(database_url="sqlite://")) == 0
    finally:
        generator.close()

    export = client.get(f"/settings/data-export/{request_id}")
    assert export.status_code == 200
    payload = export.json()
    assert payload["status"] == "completed"
    assert payload["result"]["account"]["id"] == account_id
    assert "password_hash" not in payload["result"]["account"]
    assert payload["result"]["data"]["chat_messages"][0]["id"] == message_id


def test_privacy_deletion_worker_soft_deletes_account_and_retains_records(api_client, monkeypatch) -> None:
    client, _ = api_client
    account_id = _create_viewer(client, monkeypatch)
    csrf = client.cookies["flingra_csrf"]
    storage = client.app.state.media_storage
    media_id = uuid.uuid4().hex
    object_key = f"accounts/{account_id}/{media_id}"
    storage.put(object_key, b"private media", "image/jpeg")
    db, generator = _session(client)
    try:
        db.execute(
            text(
                """
                INSERT INTO media_objects
                    (id, account_id, purpose, object_key, content_type, size_bytes, sha256)
                VALUES (:id, :account_id, 'profile-photo', :object_key, 'image/jpeg', 13, 'hash')
                """
            ),
            {"id": media_id, "account_id": account_id, "object_key": object_key},
        )
        db.commit()
    finally:
        generator.close()

    response = client.post("/settings/account/delete", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 202
    db, generator = _session(client)
    try:
        assert process_privacy_requests(
            db,
            Settings(database_url="sqlite://"),
        ) == 1
        assert process_privacy_requests(
            db,
            Settings(database_url="sqlite://"),
        ) == 0
        assert db.execute(
            text("SELECT account_state FROM accounts WHERE id = :account_id"),
            {"account_id": account_id},
        ).scalar_one() == "deleted"
        assert db.execute(
            text("SELECT status FROM privacy_requests WHERE id = :request_id"),
            {"request_id": response.json()["requestId"]},
        ).scalar_one() == "completed"
        assert db.execute(
            text("SELECT COUNT(*) FROM profiles WHERE account_id = :account_id"),
            {"account_id": account_id},
        ).scalar_one() == 1
        assert db.execute(
            text("SELECT COUNT(*) FROM media_objects WHERE account_id = :account_id"),
            {"account_id": account_id},
        ).scalar_one() == 1
    finally:
        generator.close()
    assert object_key in storage.objects
    assert client.get("/settings/sessions").status_code == 401


def test_posts_require_owned_media_and_status_expires(api_client, monkeypatch) -> None:
    client, _ = api_client
    account_id = _create_viewer(client, monkeypatch)
    csrf = client.cookies["flingra_csrf"]
    db, generator = _session(client)
    photo_urls = []
    try:
        for _ in range(3):
            media_id = uuid.uuid4().hex
            photo_urls.append(f"/media/{media_id}")
            db.execute(
                text(
                    """
                    INSERT INTO media_objects (
                        id, account_id, purpose, object_key, content_type, size_bytes, sha256
                    )
                    VALUES (:id, :account_id, 'profile-photo', :object_key, 'image/jpeg', 1, 'test')
                    """
                ),
                {
                    "id": media_id,
                    "account_id": account_id,
                    "object_key": f"accounts/{account_id}/test/{media_id}",
                },
            )
        db.commit()
    finally:
        generator.close()

    post = client.post(
        "/posts",
        headers={"X-CSRF-Token": csrf},
        json={"photos": photo_urls, "caption": "A test post"},
    )
    assert post.status_code == 201
    assert post.json()["photos"] == photo_urls
    unowned_video = client.post(
        "/posts",
        headers={"X-CSRF-Token": csrf},
        json={"video": "https://cdn.example.test/video.mp4"},
    )
    assert unowned_video.status_code == 400
    assert unowned_video.json()["error"]["code"] == "MEDIA_NOT_FOUND"
    upload = client.post(
        "/media/videos?purpose=post",
        headers={"X-CSRF-Token": csrf},
        files={"file": ("post.mp4", b"\x00\x00\x00\x18ftypisom", "video/mp4")},
    )
    assert upload.status_code == 201, upload.json()
    video_post = client.post(
        "/posts",
        headers={"X-CSRF-Token": csrf},
        json={"video": upload.json()["url"], "caption": "A video post"},
    )
    assert video_post.status_code == 201, video_post.json()
    assert video_post.json()["video"] == upload.json()["url"]

    image = Image.new("RGB", (4, 4), "red")
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    status = client.post(
        "/statuses",
        headers={"X-CSRF-Token": csrf},
        files={"file": ("status.png", image_bytes.getvalue(), "image/png")},
    )
    assert status.status_code == 201
    assert status.json()["kind"] == "image"
    assert len(client.get("/statuses/nearby").json()) == 1


def test_subscription_catalog_and_status_are_backend_owned(api_client, monkeypatch) -> None:
    client, _ = api_client
    _create_viewer(client, monkeypatch)

    plans = client.get("/subscriptions/plans")
    assert plans.status_code == 200
    assert [plan["id"] for plan in plans.json()] == ["vip-weekly", "vip-monthly", "vip-yearly"]
    assert plans.json()[0]["priceNaira"] == 3500
    assert client.get("/subscriptions/me").json() == {"tier": "free", "expiresAt": None}

    purchase = client.post(
        "/subscriptions",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        json={"planId": "vip-weekly"},
    )
    assert purchase.status_code == 409
    assert purchase.json()["error"]["code"] == "INSUFFICIENT_BALANCE"


def test_wallet_gift_purchase_and_vip_subscription_use_atomic_ledger(api_client, monkeypatch) -> None:
    client, _ = api_client
    account_id = _create_viewer(client, monkeypatch)
    db, generator = _session(client)
    try:
        db.execute(
            text(
                "INSERT INTO wallet_accounts (account_id, balance_kobo) VALUES (:account_id, 1000000)"
            ),
            {"account_id": account_id},
        )
        db.commit()
    finally:
        generator.close()
    csrf = client.cookies["flingra_csrf"]

    bought = client.post(
        "/wallet/gifts/buy",
        headers={"X-CSRF-Token": csrf},
        json={"giftTypeId": "rose", "quantity": 2},
    )
    assert bought.status_code == 200
    assert bought.json() == {"balanceNaira": 9000}
    assert client.get("/wallet/gifts/owned").json() == [
        {
            "gift": {
                "id": "rose",
                "name": "Rose",
                "emoji": "🌹",
                "priceNaira": 500,
            },
            "quantity": 2,
        }
    ]

    vip = client.post(
        "/subscriptions",
        headers={"X-CSRF-Token": csrf},
        json={"planId": "vip-weekly"},
    )
    assert vip.status_code == 201
    assert vip.json()["tier"] == "vip"
    assert client.get("/wallet/balance").json() == {"balanceNaira": 5500}
    assert [row["type"] for row in client.get("/wallet/transactions").json()] == [
        "vip-subscription",
        "gift-purchase",
    ]


def test_sending_gift_enqueues_recipient_notification(api_client, monkeypatch) -> None:
    client, _ = api_client
    sender_id = _create_viewer(client, monkeypatch)
    recipient_id = _create_candidate(client)
    db, generator = _session(client)
    try:
        db.execute(
            text(
                """
                INSERT INTO gift_inventory (account_id, gift_type_id, quantity)
                VALUES (:account_id, 'rose', 1)
                """
            ),
            {"account_id": sender_id},
        )
        db.commit()
    finally:
        generator.close()

    sent = client.post(
        "/wallet/gifts/rose/spend",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        json={"recipientId": recipient_id},
    )

    assert sent.status_code == 200
    db, generator = _session(client)
    try:
        event = db.execute(
            text(
                """
                SELECT event_type, payload_json FROM realtime_events
                WHERE recipient_id = :recipient_id
                ORDER BY id DESC LIMIT 1
                """
            ),
            {"recipient_id": recipient_id},
        ).mappings().one()
    finally:
        generator.close()
    assert event["event_type"] == "wallet.gift_received"
    payload = json.loads(event["payload_json"])
    assert payload["giftId"] == sent.json()["giftId"]
    assert payload["giftName"] == "Rose"
    assert payload["giftEmoji"] == "🌹"


def test_expired_vip_is_treated_as_free_for_profile_and_chat_access(api_client, monkeypatch) -> None:
    client, _ = api_client
    _create_viewer(client, monkeypatch)
    target_id = _create_candidate(client)
    db, generator = _session(client)
    try:
        db.execute(
            text(
                """
                UPDATE profiles
                SET subscription_tier = 'vip', vip_expires_at = :expires_at
                WHERE account_id = :target_id
                """
            ),
            {
                "target_id": target_id,
                "expires_at": datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
            },
        )
        db.commit()
    finally:
        generator.close()

    profile = client.get(f"/profiles/{target_id}")
    assert profile.status_code == 200
    assert profile.json()["subscriptionTier"] == "free"

    interest = client.post(
        "/chat/interests",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        json={"targetId": target_id},
    )
    assert interest.status_code == 201


def test_expired_vip_viewer_cannot_access_active_vip_chat(api_client, monkeypatch) -> None:
    client, _ = api_client
    viewer_id = _create_viewer(client, monkeypatch)
    target_id = _create_candidate(client)
    db, generator = _session(client)
    try:
        db.execute(
            text(
                """
                UPDATE profiles
                SET subscription_tier = 'vip', vip_expires_at = :expires_at
                WHERE account_id = :account_id
                """
            ),
            {
                "account_id": viewer_id,
                "expires_at": datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
            },
        )
        db.execute(
            text(
                """
                UPDATE profiles
                SET subscription_tier = 'vip', vip_expires_at = :expires_at
                WHERE account_id = :account_id
                """
            ),
            {
                "account_id": target_id,
                "expires_at": datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
            },
        )
        db.commit()
    finally:
        generator.close()

    response = client.post(
        "/chat/interests",
        headers={"X-CSRF-Token": client.cookies["flingra_csrf"]},
        json={"targetId": target_id},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "VIP_REQUIRED"
    assert client.get("/subscriptions/me").json() == {"tier": "free", "expiresAt": None}


def test_gift_redemption_credits_wallet_only_once(api_client, monkeypatch) -> None:
    client, _ = api_client
    account_id = _create_viewer(client, monkeypatch)
    target_id = _create_candidate(client)
    gift_id = uuid.uuid4().hex
    db, generator = _session(client)
    try:
        db.execute(
            text(
                """
                INSERT INTO received_gifts (
                    id, recipient_id, sender_id, gift_type_id, value_kobo, redeemed
                )
                VALUES (:id, :recipient_id, :sender_id, 'rose', 50000, FALSE)
                """
            ),
            {"id": gift_id, "recipient_id": account_id, "sender_id": target_id},
        )
        db.commit()
    finally:
        generator.close()

    headers = {"X-CSRF-Token": client.cookies["flingra_csrf"]}
    first = client.post(f"/wallet/gifts/{gift_id}/redeem", headers=headers)
    second = client.post(f"/wallet/gifts/{gift_id}/redeem", headers=headers)

    assert first.status_code == 204
    assert second.status_code == 409
    assert client.get("/wallet/balance").json() == {"balanceNaira": 500}
    assert len(client.get("/wallet/transactions").json()) == 1


def test_unsupported_chat_attachment_and_malformed_video_are_rejected(api_client, monkeypatch) -> None:
    client, _ = api_client
    _create_viewer(client, monkeypatch)
    csrf = client.cookies["flingra_csrf"]

    chat_attachment = client.post(
        "/chat/attachments",
        headers={"X-CSRF-Token": csrf},
        files={"file": ("attachment.txt", b"x" * (1024 * 1024 + 1), "text/plain")},
    )
    video_upload = client.post(
        "/media/videos",
        headers={"X-CSRF-Token": csrf},
        files={"file": ("clip.mp4", b"video data", "video/mp4")},
    )

    assert chat_attachment.status_code == 415
    assert chat_attachment.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert video_upload.status_code == 400
    assert video_upload.json()["error"]["code"] == "INVALID_VIDEO"
