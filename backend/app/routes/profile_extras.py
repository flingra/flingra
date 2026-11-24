import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings
from app.dependencies import db_session
from app.errors import ApiException
from app.routes.auth import IdentityVerifiedAccount, get_app_settings
from app.routes.profiles import _member_profile, _require_discovery_ready, _visible_profile_rows

router = APIRouter(tags=["profile extras"])
DbSession = Annotated[Session, Depends(db_session)]
SettingsDependency = Annotated[Settings, Depends(get_app_settings)]


def _visible_rows(
    account: dict[str, Any],
    db: Session,
    settings: Settings,
) -> list[dict[str, Any]]:
    _require_discovery_ready(account)
    viewer = db.execute(
        text("SELECT identity FROM profiles WHERE account_id = :account_id"),
        {"account_id": account.account_id},
    ).mappings().first()
    if viewer is None:
        raise ApiException("NO_PROFILE", "Finish onboarding before browsing members.", 404)
    return _visible_profile_rows(
        db,
        account.account_id,
        viewer["identity"],
        settings.demo_profiles_enabled,
    )


@router.get("/profiles")
def list_vip_profiles(
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> list[dict[str, Any]]:
    rows = _visible_rows(account, db, settings)
    return [
        profile.model_dump(by_alias=True)
        for row in rows
        if (profile := _member_profile(row, None)).subscription_tier == "vip"
    ]


@router.get("/videos/nearby")
def list_nearby_videos(
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> list[dict[str, str]]:
    rows = _visible_rows(account, db, settings)
    videos: list[dict[str, str]] = []
    for row in rows:
        profile_videos = json.loads(row["videos"]) if isinstance(row["videos"], str) else row["videos"]
        photos = json.loads(row["photos"]) if isinstance(row["photos"], str) else row["photos"]
        for video in profile_videos or []:
            if video.get("locked"):
                continue
            videos.append(
                {
                    "authorId": str(row["id"]),
                    "authorName": row["display_name"],
                    "authorPhoto": photos[0] if photos else "",
                    "video": video["url"],
                }
            )
    return videos


@router.get("/presence/{author_id}")
def get_member_presence(
    author_id: str,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> dict[str, str | bool | None]:
    _require_discovery_ready(account)
    if author_id == account.account_id:
        visible = True
    else:
        visible = any(
            str(row["id"]) == author_id
            for row in _visible_rows(account, db, settings)
        )
    if not visible:
        raise ApiException("PROFILE_NOT_FOUND", "This member is unavailable.", 404)
    has_status = db.execute(
        text(
            """
            SELECT 1 FROM member_statuses
            WHERE author_id = :author_id AND expires_at > :now
            LIMIT 1
            """
        ),
        {
            "author_id": author_id,
            "now": datetime.now(UTC).replace(tzinfo=None),
        },
    ).first() is not None
    return {"hasStatus": has_status, "isLive": False, "streamId": None}
