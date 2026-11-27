import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.config import Settings
from app.dependencies import db_session
from app.errors import ApiException
from app.feature_schemas import VideoUnlockRequest, VideoUnlockResponse
from app.routes.auth import IdentityVerifiedAccount, get_app_settings, require_csrf
from app.routes.profiles import _effective_subscription_tier, _visible_profile_rows
from app.wallet import credit_wallet, debit_wallet, ensure_wallet_account

router = APIRouter(prefix="/videos", tags=["videos"])
DbSession = Annotated[Session, Depends(db_session)]
SettingsDependency = Annotated[Settings, Depends(get_app_settings)]
MEDIA_URL_PATTERN = re.compile(r"^/media/([0-9a-f]{32})$")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _video_metadata(db: Session, media_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    row = db.execute(
        text(
            """
            SELECT m.id, m.account_id, m.purpose, m.content_type,
                   p.videos, p.identity, p.subscription_tier, p.vip_expires_at
            FROM media_objects m
            JOIN profiles p ON p.account_id = m.account_id
            JOIN accounts a ON a.id = m.account_id
            WHERE m.id = :media_id AND m.purpose = 'profile-video'
              AND a.account_state NOT IN ('deletion_requested', 'deleted')
            """
        ),
        {"media_id": media_id},
    ).mappings().first()
    if row is None:
        raise ApiException("VIDEO_NOT_FOUND", "This video is unavailable.", 404)
    profile_videos = json.loads(row["videos"]) if isinstance(row["videos"], str) else row["videos"]
    video = next(
        (
            item
            for item in profile_videos or []
            if isinstance(item, dict) and item.get("url") == f"/media/{media_id}"
        ),
        None,
    )
    if video is None:
        raise ApiException("VIDEO_NOT_FOUND", "This video is unavailable.", 404)
    return dict(row), video


@router.get("/unlocks", response_model=list[str])
def list_video_unlocks(
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> list[str]:
    rows = db.execute(
        text(
            """
            SELECT media_id FROM video_unlocks
            WHERE viewer_id = :viewer_id AND expires_at > :now
            """
        ),
        {"viewer_id": account.account_id, "now": _now()},
    ).mappings()
    return [f"/media/{row['media_id']}" for row in rows]


@router.post(
    "/unlock",
    response_model=VideoUnlockResponse,
    dependencies=[Depends(require_csrf)],
)
def unlock_video(
    body: VideoUnlockRequest,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> VideoUnlockResponse:
    match = MEDIA_URL_PATTERN.fullmatch(body.url)
    if match is None:
        raise ApiException("VIDEO_NOT_FOUND", "This video is unavailable.", 404)
    media_id = match.group(1)
    metadata, video = _video_metadata(db, media_id)
    creator_id = str(metadata["account_id"])
    if creator_id == account.account_id:
        raise ApiException("VIDEO_UNLOCK_FORBIDDEN", "You cannot purchase your own video.", 400)
    if not video.get("locked"):
        return VideoUnlockResponse(url=body.url, unlocked=True, price_naira=0)
    if metadata["identity"] != "woman":
        raise ApiException("VIDEO_NOT_FOUND", "This video is unavailable.", 404)

    viewer = db.execute(
        text("SELECT identity, subscription_tier, vip_expires_at FROM profiles WHERE account_id = :id"),
        {"id": account.account_id},
    ).mappings().first()
    if viewer is None:
        raise ApiException("NO_PROFILE", "Finish your profile before unlocking videos.", 404)
    visible = _visible_profile_rows(
        db,
        account.account_id,
        viewer["identity"],
        settings.demo_profiles_enabled,
        profile_id=creator_id,
    )
    if not visible:
        raise ApiException("VIDEO_NOT_FOUND", "This video is unavailable.", 404)
    target = visible[0]
    if (
        _effective_subscription_tier(target["subscription_tier"], target["vip_expires_at"]) == "vip"
        and _effective_subscription_tier(viewer["subscription_tier"], viewer["vip_expires_at"]) != "vip"
    ):
        raise ApiException("VIP_REQUIRED", "Upgrade to VIP to view this member's profile.", 403)
    blocked = db.execute(
        text(
            """
            SELECT 1 FROM safety_blocks
            WHERE (blocker_id = :viewer AND blocked_id = :creator)
               OR (blocker_id = :creator AND blocked_id = :viewer)
            LIMIT 1
            """
        ),
        {"viewer": account.account_id, "creator": creator_id},
    ).first()
    if blocked is not None:
        raise ApiException("VIDEO_NOT_FOUND", "This video is unavailable.", 404)
    price_naira = video.get("priceNaira")
    if isinstance(price_naira, bool) or not isinstance(price_naira, int) or price_naira <= 0:
        raise ApiException("VIDEO_PRICE_INVALID", "This video cannot be purchased right now.", 409)
    price_naira = min(price_naira, 3_000)

    ensure_wallet_account(db, account.account_id)
    if db.get_bind().dialect.name != "sqlite":
        db.execute(
            text("SELECT account_id FROM wallet_accounts WHERE account_id = :id FOR UPDATE"),
            {"id": account.account_id},
        ).first()
    now = _now()
    existing_unlock = db.execute(
        text(
            """
            SELECT id, expires_at FROM video_unlocks
            WHERE viewer_id = :viewer AND media_id = :media
            """
        ),
        {"viewer": account.account_id, "media": media_id},
    ).mappings().first()
    if existing_unlock is not None and datetime.fromisoformat(str(existing_unlock["expires_at"])) > now:
        return VideoUnlockResponse(url=body.url, unlocked=True, price_naira=price_naira)

    price_kobo = price_naira * 100
    debit_wallet(
        db,
        account.account_id,
        price_kobo,
        transaction_type="video-unlock",
        description=f"Unlocked a video from {str(target['display_name'])[:100]}",
    )
    expires_at = now + timedelta(days=30)
    if existing_unlock is None:
        db.execute(
            text(
                """
                INSERT INTO video_unlocks (
                    id, viewer_id, creator_id, media_id, price_kobo, created_at, expires_at
                )
                VALUES (:id, :viewer, :creator, :media, :price, :created_at, :expires_at)
                """
            ),
            {
                "id": uuid.uuid4().hex,
                "viewer": account.account_id,
                "creator": creator_id,
                "media": media_id,
                "price": price_kobo,
                "created_at": now,
                "expires_at": expires_at,
            },
        )
    else:
        db.execute(
            text(
                """
                UPDATE video_unlocks
                SET price_kobo = :price, created_at = :created_at, expires_at = :expires_at
                WHERE id = :id
                """
            ),
            {
                "id": existing_unlock["id"],
                "price": price_kobo,
                "created_at": now,
                "expires_at": expires_at,
            },
        )
    credit_wallet(
        db,
        creator_id,
        price_kobo,
        transaction_type="video-sale",
        description="Earnings from a video unlock",
    )
    record_audit_event(
        db,
        request,
        event_type="video.unlocked",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=creator_id,
        outcome="success",
        metadata={"mediaId": media_id, "priceKobo": price_kobo},
    )
    db.commit()
    return VideoUnlockResponse(url=body.url, unlocked=True, price_naira=price_naira)
