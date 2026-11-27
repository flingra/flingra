import json
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.config import Settings
from app.dependencies import db_session
from app.errors import ApiException
from app.feature_schemas import (
    ChatAttachment,
    ChatInterestCreateRequest,
    ChatInterestResponse,
    ChatMessageCreateRequest,
    ChatThreadCreateRequest,
    ChatThreadResponse,
    DirectMessageResponse,
    MeetupPaymentCreateRequest,
    MeetupPaymentDisputeRequest,
    MeetupPaymentResponse,
)
from app.routes.auth import IdentityVerifiedAccount, get_app_settings, require_csrf
from app.routes.profiles import _effective_subscription_tier, _member_profile, _visible_profile_rows
from app.realtime import enqueue_realtime_event
from app.routes.media import _normalize_image, _persist_upload
from app.storage import ObjectStorage, get_object_storage
from app.wallet import credit_wallet, debit_wallet

router = APIRouter(prefix="/chat", tags=["chat"])
DbSession = Annotated[Session, Depends(db_session)]
SettingsDependency = Annotated[Settings, Depends(get_app_settings)]
StorageDependency = Annotated[ObjectStorage, Depends(get_object_storage)]
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _require_ready(account: dict[str, Any]) -> None:
    if not account["email_verified"]:
        raise ApiException("CONTACT_NOT_VERIFIED", "Verify your contact before messaging.", 403)
    if not account["onboarding_complete"]:
        raise ApiException("ONBOARDING_REQUIRED", "Complete onboarding before messaging.", 403)


def _get_thread(db: Session, thread_id: str, account_id: str) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT id, participant_a_id, participant_b_id
            FROM chat_threads
            WHERE id = :thread_id
              AND (participant_a_id = :account_id OR participant_b_id = :account_id)
            """
        ),
        {"thread_id": thread_id, "account_id": account_id},
    ).mappings().first()
    if row is None:
        raise ApiException("THREAD_NOT_FOUND", "This conversation is unavailable.", 404)
    other_id = row["participant_b_id"] if row["participant_a_id"] == account_id else row["participant_a_id"]
    return {"id": str(row["id"]), "other_id": str(other_id)}


def _ensure_not_blocked(db: Session, account_id: str, other_id: str) -> None:
    blocked = db.execute(
        text(
            """
            SELECT 1 FROM safety_blocks
            WHERE (blocker_id = :account_id AND blocked_id = :other_id)
               OR (blocker_id = :other_id AND blocked_id = :account_id)
            LIMIT 1
            """
        ),
        {"account_id": account_id, "other_id": other_id},
    ).first()
    if blocked is not None:
        raise ApiException("MEMBER_BLOCKED", "Messaging is unavailable for this member.", 403)


def _ensure_interest_accepted(db: Session, account_id: str, other_id: str) -> None:
    accepted = db.execute(
        text(
            """
            SELECT 1 FROM chat_interest_requests
            WHERE status = 'accepted'
              AND (
                  (sender_id = :account_id AND recipient_id = :other_id)
                  OR (sender_id = :other_id AND recipient_id = :account_id)
              )
            LIMIT 1
            """
        ),
        {"account_id": account_id, "other_id": other_id},
    ).first()
    if accepted is None:
        raise ApiException(
            "INTEREST_NOT_ACCEPTED",
            "The interest request must be accepted before messaging.",
            403,
        )


def _discoverable_target(
    db: Session,
    account_id: str,
    settings: Settings,
    target_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    viewer = db.execute(
        text(
            """
            SELECT p.identity, p.subscription_tier, p.vip_expires_at, p.display_name
            FROM profiles p
            WHERE p.account_id = :account_id
            """
        ),
        {"account_id": account_id},
    ).mappings().first()
    if viewer is None:
        raise ApiException("NO_PROFILE", "Finish onboarding before messaging.", 404)
    rows = _visible_profile_rows(
        db,
        account_id,
        viewer["identity"],
        settings.demo_profiles_enabled,
        profile_id=target_id,
    )
    if not rows:
        raise ApiException("PROFILE_NOT_FOUND", "This member is unavailable.", 404)
    target = rows[0]
    viewer_tier = _effective_subscription_tier(viewer["subscription_tier"], viewer["vip_expires_at"])
    target_profile = _member_profile(target, None)
    if target_profile.subscription_tier == "vip" and viewer_tier != "vip":
        raise ApiException("VIP_REQUIRED", "Upgrade to VIP to message this member.", 403)
    return dict(viewer), target_profile.model_dump(by_alias=False)


def _thread_response(row: dict[str, Any]) -> ChatThreadResponse:
    photos = row["photos"]
    photos = json.loads(photos) if isinstance(photos, str) else photos
    return ChatThreadResponse(
        id=str(row["id"]),
        other_id=str(row["other_id"]),
        other_name=row["display_name"],
        other_photo=photos[0] if photos else "",
        last_message=row["last_message"] or "",
        last_message_at=row["last_message_at"],
    )


def _interest_request_row(db: Session, interest_id: str) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT i.id, i.sender_id, i.recipient_id, i.status, i.created_at,
                   p.display_name AS sender_name, p.photos AS sender_photos
            FROM chat_interest_requests i
            JOIN profiles p ON p.account_id = i.sender_id
            WHERE i.id = :interest_id
            """
        ),
        {"interest_id": interest_id},
    ).mappings().first()
    return dict(row) if row is not None else None


def _interest_response(row: dict[str, Any]) -> ChatInterestResponse:
    photos = row["sender_photos"]
    photos = json.loads(photos) if isinstance(photos, str) else photos
    return ChatInterestResponse(
        id=str(row["id"]),
        sender_id=str(row["sender_id"]),
        sender_name=row["sender_name"],
        sender_photo=photos[0] if photos else "",
        status=row["status"],
        created_at=row["created_at"],
    )


def _get_or_create_thread_id(db: Session, first_id: str, second_id: str) -> str:
    left, right = sorted((first_id, second_id))
    existing = db.execute(
        text(
            """
            SELECT id FROM chat_threads
            WHERE participant_a_id = :left AND participant_b_id = :right
            """
        ),
        {"left": left, "right": right},
    ).scalar_one_or_none()
    if existing is not None:
        return str(existing)

    thread_id = uuid.uuid4().hex
    try:
        db.execute(
            text(
                """
                INSERT INTO chat_threads (
                    id, participant_a_id, participant_b_id, created_at, last_message_at
                )
                VALUES (:id, :left, :right, :created_at, :created_at)
                """
            ),
            {"id": thread_id, "left": left, "right": right, "created_at": _now()},
        )
    except IntegrityError:
        db.rollback()
        existing = db.execute(
            text(
                """
                SELECT id FROM chat_threads
                WHERE participant_a_id = :left AND participant_b_id = :right
                """
            ),
            {"left": left, "right": right},
        ).scalar_one_or_none()
        if existing is None:
            raise
        return str(existing)
    return thread_id


def _list_threads(db: Session, account_id: str) -> list[ChatThreadResponse]:
    rows = db.execute(
        text(
            """
            SELECT t.id,
                   CASE WHEN t.participant_a_id = :account_id
                        THEN t.participant_b_id ELSE t.participant_a_id END AS other_id,
                   p.display_name, p.photos,
                   COALESCE((
                       SELECT m.message_text
                       FROM chat_messages m
                       WHERE m.thread_id = t.id
                       ORDER BY m.created_at DESC, m.id DESC
                       LIMIT 1
                   ), '') AS last_message,
                   COALESCE((
                       SELECT m.created_at
                       FROM chat_messages m
                       WHERE m.thread_id = t.id
                       ORDER BY m.created_at DESC, m.id DESC
                       LIMIT 1
                   ), t.created_at) AS last_message_at
            FROM chat_threads t
            JOIN profiles p
              ON p.account_id = CASE WHEN t.participant_a_id = :account_id
                                     THEN t.participant_b_id ELSE t.participant_a_id END
            WHERE (t.participant_a_id = :account_id OR t.participant_b_id = :account_id)
              AND EXISTS (
                  SELECT 1 FROM chat_interest_requests i
                  WHERE i.status = 'accepted'
                    AND (
                        (i.sender_id = t.participant_a_id AND i.recipient_id = t.participant_b_id)
                        OR (i.sender_id = t.participant_b_id AND i.recipient_id = t.participant_a_id)
                    )
              )
            ORDER BY last_message_at DESC, t.id
            """
        ),
        {"account_id": account_id},
    ).mappings()
    return [_thread_response(dict(row)) for row in rows]


@router.post(
    "/threads",
    response_model=ChatThreadResponse,
    dependencies=[Depends(require_csrf)],
)
def get_or_create_thread(
    body: ChatThreadCreateRequest,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> ChatThreadResponse:
    _require_ready(account)
    _ensure_not_blocked(db, account.account_id, body.other_id)
    viewer, target = _discoverable_target(db, account.account_id, settings, body.other_id)
    left, right = sorted((account.account_id, body.other_id))
    thread_id = db.execute(
        text(
            """
            SELECT id FROM chat_threads
            WHERE participant_a_id = :left AND participant_b_id = :right
            """
        ),
        {"left": left, "right": right},
    ).scalar_one_or_none()
    if thread_id is None:
        if viewer["identity"] == "woman" and target["identity"] == "man":
            raise ApiException(
                "INTEREST_DIRECTION_RESTRICTED",
                "Women cannot start a conversation. Wait for the man to send an interest request.",
                403,
            )
        raise ApiException(
            "INTEREST_NOT_ACCEPTED",
            "The interest request must be accepted before messaging.",
            403,
        )
    _ensure_interest_accepted(db, account.account_id, body.other_id)
    thread_id = str(thread_id)
    thread_rows = _list_threads(db, account.account_id)
    response = next((thread for thread in thread_rows if thread.id == thread_id), None)
    if response is None:
        raise ApiException("THREAD_NOT_FOUND", "This conversation is unavailable.", 404)
    return response


@router.post(
    "/interests",
    response_model=ChatInterestResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_interest_request(
    body: ChatInterestCreateRequest,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> ChatInterestResponse:
    _require_ready(account)
    _ensure_not_blocked(db, account.account_id, body.target_id)
    viewer, target = _discoverable_target(db, account.account_id, settings, body.target_id)
    if viewer["identity"] != "man" or target["identity"] != "woman":
        raise ApiException(
            "INTEREST_DIRECTION_RESTRICTED",
            "Only men can send interest requests to women.",
            403,
        )

    existing = db.execute(
        text(
            """
            SELECT id, status FROM chat_interest_requests
            WHERE sender_id = :sender_id AND recipient_id = :recipient_id
            """
        ),
        {"sender_id": account.account_id, "recipient_id": body.target_id},
    ).mappings().first()
    now = _now()
    if existing is not None and existing["status"] != "declined":
        row = _interest_request_row(db, str(existing["id"]))
        if row is None:
            raise ApiException("INTEREST_NOT_FOUND", "This interest request is unavailable.", 404)
        return _interest_response(row)

    if existing is not None:
        interest_id = str(existing["id"])
        updated = db.execute(
            text(
                """
                UPDATE chat_interest_requests
                SET status = 'pending', created_at = :now, updated_at = :now, decided_at = NULL
                WHERE id = :id AND status = 'declined'
                """
            ),
            {"id": interest_id, "now": now},
        )
        if updated.rowcount != 1:
            row = _interest_request_row(db, interest_id)
            if row is None:
                raise ApiException("INTEREST_NOT_FOUND", "This interest request is unavailable.", 404)
            return _interest_response(row)
    else:
        interest_id = uuid.uuid4().hex
        try:
            db.execute(
                text(
                    """
                    INSERT INTO chat_interest_requests (
                        id, sender_id, recipient_id, status, created_at, updated_at
                    )
                    VALUES (:id, :sender_id, :recipient_id, 'pending', :created_at, :updated_at)
                    """
                ),
                {
                    "id": interest_id,
                    "sender_id": account.account_id,
                    "recipient_id": body.target_id,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        except IntegrityError:
            db.rollback()
            existing_id = db.execute(
                text(
                    """
                    SELECT id FROM chat_interest_requests
                    WHERE sender_id = :sender_id AND recipient_id = :recipient_id
                    """
                ),
                {"sender_id": account.account_id, "recipient_id": body.target_id},
            ).scalar_one_or_none()
            if existing_id is None:
                raise
            row = _interest_request_row(db, str(existing_id))
            if row is None:
                raise ApiException("INTEREST_NOT_FOUND", "This interest request is unavailable.", 404)
            return _interest_response(row)

    record_audit_event(
        db,
        request,
        event_type="chat.interest_requested",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=body.target_id,
        outcome="success",
    )
    enqueue_realtime_event(
        db,
        body.target_id,
        "chat.interest_received",
        {
            "interestId": interest_id,
            "senderName": viewer["display_name"],
        },
    )
    db.commit()
    row = _interest_request_row(db, interest_id)
    if row is None:
        raise ApiException("INTEREST_NOT_FOUND", "This interest request is unavailable.", 404)
    return _interest_response(row)


@router.get("/interests", response_model=list[ChatInterestResponse])
def list_incoming_interest_requests(
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> list[ChatInterestResponse]:
    _require_ready(account)
    rows = db.execute(
        text(
            """
            SELECT i.id, i.sender_id, i.recipient_id, i.status, i.created_at,
                   p.display_name AS sender_name, p.photos AS sender_photos
            FROM chat_interest_requests i
            JOIN profiles p ON p.account_id = i.sender_id
            WHERE i.recipient_id = :recipient_id AND i.status = 'pending'
            ORDER BY i.created_at DESC, i.id
            """
        ),
        {"recipient_id": account.account_id},
    ).mappings()
    return [_interest_response(dict(row)) for row in rows]


@router.post(
    "/interests/{interest_id}/accept",
    response_model=ChatThreadResponse,
    dependencies=[Depends(require_csrf)],
)
def accept_interest_request(
    interest_id: str,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> ChatThreadResponse:
    _require_ready(account)
    interest = db.execute(
        text(
            """
            SELECT id, sender_id, recipient_id, status
            FROM chat_interest_requests
            WHERE id = :interest_id AND recipient_id = :recipient_id
            """
        ),
        {"interest_id": interest_id, "recipient_id": account.account_id},
    ).mappings().first()
    if interest is None:
        raise ApiException("INTEREST_NOT_FOUND", "This interest request is unavailable.", 404)
    if interest["status"] == "declined":
        raise ApiException("INTEREST_ALREADY_DECLINED", "This interest request was declined.", 409)

    sender_id = str(interest["sender_id"])
    _ensure_not_blocked(db, account.account_id, sender_id)
    if interest["status"] == "pending":
        thread_id = _get_or_create_thread_id(db, sender_id, account.account_id)
        now = _now()
        updated = db.execute(
            text(
                """
                UPDATE chat_interest_requests
                SET status = 'accepted', updated_at = :now, decided_at = :now
                WHERE id = :interest_id AND status = 'pending'
                """
            ),
            {"interest_id": interest_id, "now": now},
        )
        if updated.rowcount != 1:
            db.rollback()
            latest_status = db.execute(
                text("SELECT status FROM chat_interest_requests WHERE id = :interest_id"),
                {"interest_id": interest_id},
            ).scalar_one_or_none()
            if latest_status == "declined":
                raise ApiException("INTEREST_ALREADY_DECLINED", "This interest request was declined.", 409)
            if latest_status != "accepted":
                raise ApiException("INTEREST_NOT_FOUND", "This interest request is unavailable.", 404)
            thread_id = db.execute(
                text(
                    """
                    SELECT id FROM chat_threads
                    WHERE participant_a_id = :left AND participant_b_id = :right
                    """
                ),
                {"left": min(sender_id, account.account_id), "right": max(sender_id, account.account_id)},
            ).scalar_one_or_none()
            if thread_id is None:
                raise ApiException("THREAD_NOT_FOUND", "The accepted conversation is unavailable.", 404)
            thread_id = str(thread_id)
        else:
            recipient_name = db.execute(
                text("SELECT display_name FROM profiles WHERE account_id = :account_id"),
                {"account_id": account.account_id},
            ).scalar_one()
            record_audit_event(
                db,
                request,
                event_type="chat.interest_accepted",
                actor_type="user",
                actor_id=account.account_id,
                subject_account_id=sender_id,
                outcome="success",
            )
            enqueue_realtime_event(
                db,
                sender_id,
                "chat.interest_accepted",
                {"threadId": thread_id, "recipientName": recipient_name},
            )
            db.commit()
    else:
        thread_id = db.execute(
            text(
                """
                SELECT id FROM chat_threads
                WHERE participant_a_id = :left AND participant_b_id = :right
                """
            ),
            {"left": min(sender_id, account.account_id), "right": max(sender_id, account.account_id)},
        ).scalar_one_or_none()
        if thread_id is None:
            raise ApiException("THREAD_NOT_FOUND", "The accepted conversation is unavailable.", 404)
        thread_id = str(thread_id)

    thread = next((item for item in _list_threads(db, account.account_id) if item.id == thread_id), None)
    if thread is None:
        raise ApiException("THREAD_NOT_FOUND", "The accepted conversation is unavailable.", 404)
    return thread


@router.post(
    "/interests/{interest_id}/decline",
    status_code=204,
    dependencies=[Depends(require_csrf)],
)
def decline_interest_request(
    interest_id: str,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> None:
    _require_ready(account)
    interest = db.execute(
        text(
            """
            SELECT status, sender_id FROM chat_interest_requests
            WHERE id = :interest_id AND recipient_id = :recipient_id
            """
        ),
        {"interest_id": interest_id, "recipient_id": account.account_id},
    ).mappings().first()
    if interest is None:
        raise ApiException("INTEREST_NOT_FOUND", "This interest request is unavailable.", 404)
    if interest["status"] == "accepted":
        raise ApiException("INTEREST_ALREADY_ACCEPTED", "This interest request was already accepted.", 409)
    if interest["status"] == "pending":
        now = _now()
        updated = db.execute(
            text(
                """
                UPDATE chat_interest_requests
                SET status = 'declined', updated_at = :now, decided_at = :now
                WHERE id = :interest_id AND status = 'pending'
                """
            ),
            {"interest_id": interest_id, "now": now},
        )
        if updated.rowcount != 1:
            db.rollback()
            latest_status = db.execute(
                text("SELECT status FROM chat_interest_requests WHERE id = :interest_id"),
                {"interest_id": interest_id},
            ).scalar_one_or_none()
            if latest_status == "accepted":
                raise ApiException("INTEREST_ALREADY_ACCEPTED", "This interest request was already accepted.", 409)
            if latest_status is None:
                raise ApiException("INTEREST_NOT_FOUND", "This interest request is unavailable.", 404)
        else:
            record_audit_event(
                db,
                request,
                event_type="chat.interest_declined",
                actor_type="user",
                actor_id=account.account_id,
                subject_account_id=interest["sender_id"],
                outcome="success",
            )
            db.commit()


@router.get("/threads", response_model=list[ChatThreadResponse])
def list_threads(
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> list[ChatThreadResponse]:
    _require_ready(account)
    threads = _list_threads(db, account.account_id)
    record_audit_event(
        db,
        request,
        event_type="chat.threads_viewed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
        metadata={"threadCount": len(threads)},
    )
    db.commit()
    return threads


@router.get("/threads/{thread_id}/messages", response_model=list[DirectMessageResponse])
def list_messages(
    thread_id: str,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> list[DirectMessageResponse]:
    _require_ready(account)
    thread = _get_thread(db, thread_id, account.account_id)
    _ensure_not_blocked(db, account.account_id, thread["other_id"])
    _ensure_interest_accepted(db, account.account_id, thread["other_id"])
    rows = db.execute(
        text(
            """
            SELECT id, thread_id, author_id, message_text, attachment_json, payment_id, created_at
            FROM chat_messages
            WHERE thread_id = :thread_id
            ORDER BY created_at, id
            """
        ),
        {"thread_id": thread_id},
    ).mappings()
    record_audit_event(
        db,
        request,
        event_type="chat.messages_viewed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=thread["other_id"],
        outcome="success",
    )
    db.commit()
    return [
        DirectMessageResponse(
            id=str(row["id"]),
            thread_id=str(row["thread_id"]),
            author_id=str(row["author_id"]),
            text=row["message_text"],
            attachment=ChatAttachment.model_validate(
                json.loads(row["attachment_json"])
                if isinstance(row["attachment_json"], str)
                else row["attachment_json"]
            )
            if row["attachment_json"]
            else None,
            payment_id=str(row["payment_id"]) if row["payment_id"] else None,
            created_at=row["created_at"],
        )
        for row in rows
    ]


@router.post(
    "/threads/{thread_id}/messages",
    response_model=DirectMessageResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def send_message(
    thread_id: str,
    body: ChatMessageCreateRequest,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> DirectMessageResponse:
    _require_ready(account)
    thread = _get_thread(db, thread_id, account.account_id)
    _ensure_not_blocked(db, account.account_id, thread["other_id"])
    _ensure_interest_accepted(db, account.account_id, thread["other_id"])
    _discoverable_target(db, account.account_id, settings, thread["other_id"])
    message_text = body.text.strip()
    if not message_text and body.attachment is None:
        raise ApiException("MESSAGE_REQUIRED", "Enter a message or attach a file.")
    attachment_json = None
    attachment_media_id = None
    if body.attachment is not None:
        match = re.fullmatch(r"/media/([0-9a-f]{32})", body.attachment.url)
        if match is None:
            raise ApiException("INVALID_ATTACHMENT", "Upload this attachment through the chat endpoint.", 400)
        attachment_media_id = match.group(1)
        media = db.execute(
            text(
                """
                SELECT content_type FROM media_objects
                WHERE id = :media_id AND account_id = :account_id AND purpose = 'chat-attachment'
                """
            ),
            {"media_id": attachment_media_id, "account_id": account.account_id},
        ).scalar_one_or_none()
        expected_type = (
            "image" if media and str(media).startswith("image/")
            else "video" if media and str(media).startswith("video/")
            else "file" if media == "application/pdf"
            else None
        )
        if expected_type is None or expected_type != body.attachment.type:
            raise ApiException("INVALID_ATTACHMENT", "This attachment is unavailable.", 400)
        attachment_json = body.attachment.model_dump_json()
    message_text = message_text or f"📎 {body.attachment.name}" if body.attachment else message_text
    message_id = uuid.uuid4().hex
    created_at = _now()
    db.execute(
        text(
            """
            INSERT INTO chat_messages (
                id, thread_id, author_id, message_text, attachment_json,
                attachment_media_id, payment_id, created_at
            )
            VALUES (
                :id, :thread_id, :author_id, :message_text, :attachment_json,
                :attachment_media_id, NULL, :created_at
            )
            """
        ),
        {
            "id": message_id,
            "thread_id": thread_id,
            "author_id": account.account_id,
            "message_text": message_text,
            "attachment_json": attachment_json,
            "attachment_media_id": attachment_media_id,
            "created_at": created_at,
        },
    )
    db.execute(
        text("UPDATE chat_threads SET last_message_at = :created_at WHERE id = :thread_id"),
        {"created_at": created_at, "thread_id": thread_id},
    )
    record_audit_event(
        db,
        request,
        event_type="chat.message_sent",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=thread["other_id"],
        outcome="success",
        metadata={"messageId": message_id},
    )
    response = DirectMessageResponse(
        id=message_id,
        thread_id=thread_id,
        author_id=account.account_id,
        text=message_text,
        attachment=body.attachment,
        created_at=created_at,
    )
    enqueue_realtime_event(
        db,
        thread["other_id"],
        "chat.message",
        response.model_dump(by_alias=True),
    )
    db.commit()
    return response


@router.post(
    "/attachments",
    response_model=ChatAttachment,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def upload_chat_attachment(
    account: IdentityVerifiedAccount,
    request: Request,
    db: DbSession,
    storage: StorageDependency,
    file: Annotated[UploadFile, File()],
) -> ChatAttachment:
    _require_ready(account)
    content = file.file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise ApiException("ATTACHMENT_TOO_LARGE", "Attachments must be 25MB or smaller.", 413)
    if not content:
        raise ApiException("EMPTY_UPLOAD", "Choose a file to attach.", 400)
    declared_type = (file.content_type or "").lower()
    if declared_type in {"image/jpeg", "image/png", "image/webp"}:
        content = _normalize_image(content, MAX_ATTACHMENT_BYTES)
        content_type = "image/jpeg"
        attachment_type = "image"
        extension = "jpg"
    elif declared_type in {"video/mp4", "video/webm"}:
        if declared_type == "video/mp4" and b"ftyp" not in content[:32]:
            raise ApiException("INVALID_VIDEO", "The uploaded file is not a valid MP4 video.", 400)
        if declared_type == "video/webm" and not content.startswith(b"\x1a\x45\xdf\xa3"):
            raise ApiException("INVALID_VIDEO", "The uploaded file is not a valid WebM video.", 400)
        content_type = declared_type
        attachment_type = "video"
        extension = "mp4" if content_type == "video/mp4" else "webm"
    elif declared_type == "application/pdf" and content.startswith(b"%PDF-"):
        content_type = declared_type
        attachment_type = "file"
        extension = "pdf"
    else:
        raise ApiException(
            "UNSUPPORTED_MEDIA_TYPE",
            "Attach a JPEG, PNG, WebP, MP4, WebM, or PDF file.",
            415,
        )

    media_id = uuid.uuid4().hex
    object_key = f"accounts/{account.account_id}/chat-attachments/{media_id}.{extension}"
    _persist_upload(
        request=request,
        db=db,
        storage=storage,
        account_id=account.account_id,
        media_id=media_id,
        object_key=object_key,
        purpose="chat-attachment",
        content=content,
        content_type=content_type,
    )
    filename = (file.filename or f"attachment.{extension}").replace("\\", "/").split("/")[-1]
    filename = "".join(character for character in filename if character.isprintable())[:255]
    if not filename:
        filename = f"attachment.{extension}"
    return ChatAttachment(url=f"/media/{media_id}", type=attachment_type, name=filename)


@router.post(
    "/threads/{thread_id}/payment-proposals",
    response_model=MeetupPaymentResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def propose_meetup_payment(
    thread_id: str,
    body: MeetupPaymentCreateRequest,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> MeetupPaymentResponse:
    _require_ready(account)
    thread = _get_thread(db, thread_id, account.account_id)
    _ensure_not_blocked(db, account.account_id, thread["other_id"])
    _ensure_interest_accepted(db, account.account_id, thread["other_id"])
    viewer, target = _discoverable_target(db, account.account_id, settings, thread["other_id"])
    if viewer["identity"] != "man":
        raise ApiException("PAYER_RESTRICTED", "Only male accounts can propose a meetup payment.", 403)
    if target["identity"] != "woman":
        raise ApiException("RECIPIENT_RESTRICTED", "Meetup payments can only be sent to female accounts.", 403)

    payment_id = uuid.uuid4().hex
    message_id = uuid.uuid4().hex
    now = _now()
    amount_kobo = body.amount_naira * 100
    db.execute(
        text(
            """
            INSERT INTO meetup_payments (
                id, thread_id, payer_id, recipient_id, payer_name, recipient_name,
                amount_kobo, status, created_at, updated_at
            )
            VALUES (
                :id, :thread_id, :payer_id, :recipient_id, :payer_name, :recipient_name,
                :amount_kobo, 'proposed', :created_at, :created_at
            )
            """
        ),
        {
            "id": payment_id,
            "thread_id": thread_id,
            "payer_id": account.account_id,
            "recipient_id": thread["other_id"],
            "payer_name": str(viewer.get("display_name") or "Member")[:100],
            "recipient_name": str(target.get("display_name") or "Member")[:100],
            "amount_kobo": amount_kobo,
            "created_at": now,
        },
    )
    db.execute(
        text(
            """
            INSERT INTO chat_messages (
                id, thread_id, author_id, message_text, payment_id, created_at
            )
            VALUES (
                :id, :thread_id, :author_id, :message_text, :payment_id, :created_at
            )
            """
        ),
        {
            "id": message_id,
            "thread_id": thread_id,
            "author_id": account.account_id,
            "message_text": f"Proposed ₦{body.amount_naira:,} for a meetup.",
            "payment_id": payment_id,
            "created_at": now,
        },
    )
    db.execute(
        text("UPDATE chat_threads SET last_message_at = :created_at WHERE id = :thread_id"),
        {"created_at": now, "thread_id": thread_id},
    )
    record_audit_event(
        db,
        request,
        event_type="meetup_payment.proposed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=thread["other_id"],
        outcome="success",
        metadata={"paymentId": payment_id, "amountKobo": amount_kobo},
    )
    response = MeetupPaymentResponse(
        id=payment_id,
        from_id=account.account_id,
        from_name=str(viewer.get("display_name") or "Member"),
        to_id=thread["other_id"],
        to_name=str(target.get("display_name") or "Member"),
        amount_naira=body.amount_naira,
        status="proposed",
        created_at=now,
    )
    enqueue_realtime_event(
        db,
        thread["other_id"],
        "chat.message",
        DirectMessageResponse(
            id=message_id,
            thread_id=thread_id,
            author_id=account.account_id,
            text=f"Proposed ₦{body.amount_naira:,} for a meetup.",
            payment_id=payment_id,
            created_at=now,
        ).model_dump(by_alias=True),
    )
    _enqueue_meetup_event(db, response)
    db.commit()
    return response


def _meetup_payment(
    db: Session,
    payment_id: str,
    account_id: str | None = None,
    *,
    lock: bool = False,
) -> dict[str, Any]:
    suffix = " FOR UPDATE" if lock and db.get_bind().dialect.name != "sqlite" else ""
    row = db.execute(
        text(
            """
            SELECT id, thread_id, payer_id, recipient_id, payer_name, recipient_name,
                   amount_kobo, status, created_at, resolved_at
            FROM meetup_payments
            WHERE id = :payment_id
              AND (:account_id IS NULL OR payer_id = :account_id OR recipient_id = :account_id)
            """
            + suffix
        ),
        {"payment_id": payment_id, "account_id": account_id},
    ).mappings().first()
    if row is None:
        raise ApiException("PAYMENT_NOT_FOUND", "This meetup payment is unavailable.", 404)
    return dict(row)


def _meetup_response(row: dict[str, Any]) -> MeetupPaymentResponse:
    return MeetupPaymentResponse(
        id=str(row["id"]),
        from_id=str(row["payer_id"]),
        from_name=str(row["payer_name"]),
        to_id=str(row["recipient_id"]),
        to_name=str(row["recipient_name"]),
        amount_naira=int(row["amount_kobo"]) // 100,
        status=row["status"],
        created_at=row["created_at"],
        resolved_at=row["resolved_at"],
    )


def _enqueue_meetup_event(db: Session, payment: MeetupPaymentResponse) -> None:
    payload = payment.model_dump(by_alias=True)
    for recipient_id in {payment.from_id, payment.to_id}:
        enqueue_realtime_event(db, recipient_id, "meetup_payment.updated", payload)


@router.get(
    "/meetup-payments",
    response_model=list[MeetupPaymentResponse],
)
def list_meetup_payments(
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> list[MeetupPaymentResponse]:
    rows = db.execute(
        text(
            """
            SELECT id, payer_id, recipient_id, payer_name, recipient_name,
                   amount_kobo, status, created_at, resolved_at
            FROM meetup_payments
            WHERE payer_id = :account_id OR recipient_id = :account_id
            ORDER BY created_at DESC, id
            LIMIT 100
            """
        ),
        {"account_id": account.account_id},
    ).mappings()
    return [_meetup_response(dict(row)) for row in rows]


@router.get(
    "/meetup-payments/{payment_id}",
    response_model=MeetupPaymentResponse,
)
def get_meetup_payment(
    payment_id: str,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> MeetupPaymentResponse:
    return _meetup_response(_meetup_payment(db, payment_id, account.account_id))


@router.post(
    "/meetup-payments/{payment_id}/accept",
    response_model=MeetupPaymentResponse,
    dependencies=[Depends(require_csrf)],
)
def accept_meetup_payment(
    payment_id: str,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> MeetupPaymentResponse:
    _require_ready(account)
    payment = _meetup_payment(db, payment_id, account.account_id, lock=True)
    if payment["recipient_id"] != account.account_id:
        raise ApiException("PAYMENT_ACTION_FORBIDDEN", "Only the recipient can accept this proposal.", 403)
    if payment["status"] != "proposed":
        raise ApiException("PAYMENT_NOT_PROPOSED", "This proposal is no longer awaiting acceptance.", 409)
    debit_wallet(
        db,
        str(payment["payer_id"]),
        int(payment["amount_kobo"]),
        transaction_type="meetup-payment-held",
        description=f"Meetup payment held for {payment['recipient_name']}",
    )
    now = _now()
    db.execute(
        text(
            """
            UPDATE meetup_payments
            SET status = 'held', updated_at = :now
            WHERE id = :id AND status = 'proposed'
            """
        ),
        {"id": payment_id, "now": now},
    )
    record_audit_event(
        db,
        request,
        event_type="meetup_payment.accepted",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=str(payment["payer_id"]),
        outcome="success",
        metadata={"paymentId": payment_id, "amountKobo": int(payment["amount_kobo"])},
    )
    payment["status"] = "held"
    _enqueue_meetup_event(db, _meetup_response(payment))
    db.commit()
    return _meetup_response(payment)


@router.post(
    "/meetup-payments/{payment_id}/decline",
    response_model=MeetupPaymentResponse,
    dependencies=[Depends(require_csrf)],
)
def decline_meetup_payment(
    payment_id: str,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> MeetupPaymentResponse:
    payment = _meetup_payment(db, payment_id, account.account_id, lock=True)
    if payment["recipient_id"] != account.account_id:
        raise ApiException("PAYMENT_ACTION_FORBIDDEN", "Only the recipient can decline this proposal.", 403)
    if payment["status"] != "proposed":
        raise ApiException("PAYMENT_NOT_PROPOSED", "This proposal is no longer awaiting acceptance.", 409)
    now = _now()
    db.execute(
        text(
            """
            UPDATE meetup_payments
            SET status = 'declined', resolved_at = :now, updated_at = :now
            WHERE id = :id AND status = 'proposed'
            """
        ),
        {"id": payment_id, "now": now},
    )
    record_audit_event(
        db,
        request,
        event_type="meetup_payment.declined",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=str(payment["payer_id"]),
        outcome="success",
        metadata={"paymentId": payment_id},
    )
    payment.update(status="declined", resolved_at=now)
    _enqueue_meetup_event(db, _meetup_response(payment))
    db.commit()
    return _meetup_response(payment)


@router.post(
    "/meetup-payments/{payment_id}/release",
    response_model=MeetupPaymentResponse,
    dependencies=[Depends(require_csrf)],
)
def release_meetup_payment(
    payment_id: str,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> MeetupPaymentResponse:
    payment = _meetup_payment(db, payment_id, account.account_id, lock=True)
    if payment["payer_id"] != account.account_id:
        raise ApiException("PAYMENT_ACTION_FORBIDDEN", "Only the payer can release held funds.", 403)
    if payment["status"] != "held":
        raise ApiException("PAYMENT_NOT_HELD", "Only held funds can be released.", 409)
    credit_wallet(
        db,
        str(payment["recipient_id"]),
        int(payment["amount_kobo"]),
        transaction_type="meetup-payment-released",
        description=f"Meetup payment released by {payment['payer_name']}",
    )
    now = _now()
    db.execute(
        text(
            """
            UPDATE meetup_payments
            SET status = 'released', resolved_at = :now, updated_at = :now
            WHERE id = :id AND status = 'held'
            """
        ),
        {"id": payment_id, "now": now},
    )
    record_audit_event(
        db,
        request,
        event_type="meetup_payment.released",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=str(payment["recipient_id"]),
        outcome="success",
        metadata={"paymentId": payment_id, "amountKobo": int(payment["amount_kobo"])},
    )
    payment.update(status="released", resolved_at=now)
    _enqueue_meetup_event(db, _meetup_response(payment))
    db.commit()
    return _meetup_response(payment)


@router.post(
    "/meetup-payments/{payment_id}/refund",
    response_model=MeetupPaymentResponse,
    dependencies=[Depends(require_csrf)],
)
def refund_meetup_payment(
    payment_id: str,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> MeetupPaymentResponse:
    payment = _meetup_payment(db, payment_id, account.account_id, lock=True)
    if payment["payer_id"] != account.account_id:
        raise ApiException("PAYMENT_ACTION_FORBIDDEN", "Only the payer can request a refund.", 403)
    if payment["status"] != "held":
        raise ApiException("PAYMENT_NOT_HELD", "Only held funds can be refunded.", 409)
    credit_wallet(
        db,
        str(payment["payer_id"]),
        int(payment["amount_kobo"]),
        transaction_type="meetup-payment-refunded",
        description="Meetup payment refunded to payer",
    )
    now = _now()
    db.execute(
        text(
            """
            UPDATE meetup_payments
            SET status = 'refunded', resolved_at = :now, updated_at = :now
            WHERE id = :id AND status = 'held'
            """
        ),
        {"id": payment_id, "now": now},
    )
    record_audit_event(
        db,
        request,
        event_type="meetup_payment.refunded",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=str(payment["payer_id"]),
        outcome="success",
        metadata={"paymentId": payment_id, "amountKobo": int(payment["amount_kobo"])},
    )
    payment.update(status="refunded", resolved_at=now)
    _enqueue_meetup_event(db, _meetup_response(payment))
    db.commit()
    return _meetup_response(payment)


@router.post(
    "/meetup-payments/{payment_id}/disputes",
    response_model=MeetupPaymentResponse,
    dependencies=[Depends(require_csrf)],
)
def dispute_meetup_payment(
    payment_id: str,
    body: MeetupPaymentDisputeRequest,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> MeetupPaymentResponse:
    payment = _meetup_payment(db, payment_id, account.account_id, lock=True)
    if payment["status"] != "held":
        raise ApiException("PAYMENT_NOT_HELD", "Only held funds can be disputed.", 409)
    now = _now()
    reason = body.reason.strip()
    if not reason:
        raise ApiException("INVALID_DISPUTE_REASON", "Explain why you are disputing this payment.", 400)
    db.execute(
        text(
            """
            UPDATE meetup_payments
            SET status = 'disputed', dispute_reason = :reason, dispute_opened_by = :account_id,
                updated_at = :now
            WHERE id = :id AND status = 'held'
            """
        ),
        {"id": payment_id, "account_id": account.account_id, "reason": reason, "now": now},
    )
    record_audit_event(
        db,
        request,
        event_type="meetup_payment.disputed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=str(payment["recipient_id"]),
        outcome="success",
        metadata={"paymentId": payment_id},
    )
    payment["status"] = "disputed"
    _enqueue_meetup_event(db, _meetup_response(payment))
    db.commit()
    return _meetup_response(payment)
