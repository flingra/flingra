import json
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
from app.errors import ApiException, ServiceUnavailable
from app.feature_schemas import (
    ChatAttachment,
    ChatMessageCreateRequest,
    ChatThreadCreateRequest,
    ChatThreadResponse,
    DirectMessageResponse,
)
from app.routes.auth import IdentityVerifiedAccount, get_app_settings, require_csrf
from app.routes.profiles import _effective_subscription_tier, _member_profile, _visible_profile_rows

router = APIRouter(prefix="/chat", tags=["chat"])
DbSession = Annotated[Session, Depends(db_session)]
SettingsDependency = Annotated[Settings, Depends(get_app_settings)]
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


def _discoverable_target(
    db: Session,
    account_id: str,
    settings: Settings,
    target_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    viewer = db.execute(
        text(
            """
            SELECT p.identity, p.subscription_tier, p.vip_expires_at
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
            WHERE t.participant_a_id = :account_id OR t.participant_b_id = :account_id
            ORDER BY last_message_at DESC, t.id
            """
        ),
        {"account_id": account_id},
    ).mappings()
    return [_thread_response(dict(row)) for row in rows]


@router.post(
    "/threads",
    response_model=ChatThreadResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def get_or_create_thread(
    body: ChatThreadCreateRequest,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> ChatThreadResponse:
    _require_ready(account)
    _ensure_not_blocked(db, account.account_id, body.other_id)
    _, target = _discoverable_target(db, account.account_id, settings, body.other_id)
    left, right = sorted((account.account_id, body.other_id))
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
        else:
            existing = thread_id
            record_audit_event(
                db,
                request,
                event_type="chat.thread_created",
                actor_type="user",
                actor_id=account.account_id,
                subject_account_id=body.other_id,
                outcome="success",
            )
            db.commit()
    thread_id = str(existing)
    thread_rows = _list_threads(db, account.account_id)
    response = next((thread for thread in thread_rows if thread.id == thread_id), None)
    if response is not None:
        return response
    return ChatThreadResponse(
        id=thread_id,
        other_id=body.other_id,
        other_name=target["display_name"],
        other_photo=target["photos"][0] if target["photos"] else "",
        last_message="",
        last_message_at=_now(),
    )


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
    rows = db.execute(
        text(
            """
            SELECT id, thread_id, author_id, message_text, attachment_json, created_at
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
    _discoverable_target(db, account.account_id, settings, thread["other_id"])
    message_text = body.text.strip()
    if not message_text and body.attachment is None:
        raise ApiException("MESSAGE_REQUIRED", "Enter a message or attach a file.")
    if body.attachment is not None:
        raise ServiceUnavailable(
            "Chat attachments are not enabled until private file storage and recipient access are configured."
        )
    message_id = uuid.uuid4().hex
    created_at = _now()
    db.execute(
        text(
            """
            INSERT INTO chat_messages (
                id, thread_id, author_id, message_text, created_at
            )
            VALUES (:id, :thread_id, :author_id, :message_text, :created_at)
            """
        ),
        {
            "id": message_id,
            "thread_id": thread_id,
            "author_id": account.account_id,
            "message_text": message_text,
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
    db.commit()
    return DirectMessageResponse(
        id=message_id,
        thread_id=thread_id,
        author_id=account.account_id,
        text=message_text,
        created_at=created_at,
    )


@router.post(
    "/attachments",
    status_code=503,
    dependencies=[Depends(require_csrf)],
)
def upload_chat_attachment(
    account: IdentityVerifiedAccount,
    file: Annotated[UploadFile, File()],
) -> None:
    content = file.file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise ApiException("ATTACHMENT_TOO_LARGE", "Attachments must be 25MB or smaller.", 413)
    raise ServiceUnavailable(
        "Chat attachments are disabled until private file storage and recipient access are configured."
    )


@router.post(
    "/threads/{thread_id}/payment-proposals",
    status_code=503,
    dependencies=[Depends(require_csrf)],
)
def payment_proposals_not_enabled(
    thread_id: str,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> None:
    _get_thread(db, thread_id, account.account_id)
    raise ServiceUnavailable(
        "Meetup payments are unavailable until a regulated payment and escrow provider is configured."
    )
