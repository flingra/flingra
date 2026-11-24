import json
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.dependencies import db_session
from app.errors import ApiException, ServiceUnavailable
from app.feature_schemas import PostCreateRequest, PostResponse, StatusResponse
from app.routes.auth import IdentityVerifiedAccount, require_csrf
from app.routes.profiles import _visible_profile_rows

router = APIRouter(tags=["content"])
DbSession = Annotated[Session, Depends(db_session)]
MEDIA_URL_PATTERN = re.compile(r"^/media/([0-9a-f]{32})$")
STATUS_LIFETIME_HOURS = 24


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _require_ready(account: dict[str, Any]) -> None:
    if not account["email_verified"]:
        raise ApiException("CONTACT_NOT_VERIFIED", "Verify your contact before posting.", 403)
    if not account["onboarding_complete"]:
        raise ApiException("ONBOARDING_REQUIRED", "Complete onboarding before posting.", 403)


def _owned_profile_photo_ids(db: Session, account_id: str, media_urls: list[str]) -> list[str]:
    media_ids: list[str] = []
    for url in media_urls:
        match = MEDIA_URL_PATTERN.fullmatch(url)
        if match is None:
            raise ApiException("MEDIA_NOT_FOUND", "Only your uploaded profile photos can be posted.", 400)
        media_ids.append(match.group(1))
    if len(set(media_ids)) != len(media_ids):
        raise ApiException("DUPLICATE_MEDIA", "A post cannot contain the same photo more than once.", 400)
    if not media_ids:
        return []
    rows = db.execute(
        text(
            """
            SELECT id FROM media_objects
            WHERE account_id = :account_id AND purpose = 'profile-photo'
              AND id IN :media_ids
            """
        ).bindparams(bindparam("media_ids", expanding=True)),
        {"account_id": account_id, "media_ids": media_ids},
    ).scalars().all()
    if len(rows) != len(media_ids):
        raise ApiException("MEDIA_NOT_FOUND", "One or more photos are unavailable.", 404)
    return media_ids


@router.get("/posts/me", response_model=list[PostResponse])
def list_my_posts(
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> list[PostResponse]:
    _require_ready(account)
    rows = db.execute(
        text(
            """
            SELECT id, author_id, photos, video_url, caption, created_at
            FROM member_posts
            WHERE author_id = :account_id
            ORDER BY created_at DESC, id
            """
        ),
        {"account_id": account.account_id},
    ).mappings()
    posts = [
        PostResponse(
            id=str(row["id"]),
            author_id=str(row["author_id"]),
            photos=json.loads(row["photos"]) if isinstance(row["photos"], str) else row["photos"],
            video=row["video_url"],
            caption=row["caption"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
    record_audit_event(
        db,
        request,
        event_type="content.own_posts_viewed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
    )
    db.commit()
    return posts


@router.post(
    "/posts",
    response_model=PostResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_post(
    body: PostCreateRequest,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> PostResponse:
    _require_ready(account)
    if len(body.photos) < 3 and not body.video:
        raise ApiException("POST_MEDIA_REQUIRED", "Add at least 3 photos or 1 video to post.")
    if body.video:
        raise ServiceUnavailable(
            "Video upload is unavailable until validated private video storage is configured."
        )
    _owned_profile_photo_ids(db, account.account_id, body.photos)
    post_id = uuid.uuid4().hex
    created_at = _now()
    db.execute(
        text(
            """
            INSERT INTO member_posts (id, author_id, photos, caption, created_at)
            VALUES (:id, :author_id, :photos, :caption, :created_at)
            """
        ),
        {
            "id": post_id,
            "author_id": account.account_id,
            "photos": json.dumps(body.photos, separators=(",", ":")),
            "caption": body.caption.strip() if body.caption else None,
            "created_at": created_at,
        },
    )
    record_audit_event(
        db,
        request,
        event_type="content.post_created",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
        metadata={"postId": post_id, "photoCount": len(body.photos)},
    )
    db.commit()
    return PostResponse(
        id=post_id,
        author_id=account.account_id,
        photos=body.photos,
        video=None,
        caption=body.caption.strip() if body.caption else None,
        created_at=created_at,
    )


@router.delete("/posts/{post_id}", status_code=204, dependencies=[Depends(require_csrf)])
def delete_post(
    post_id: str,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> None:
    result = db.execute(
        text("DELETE FROM member_posts WHERE id = :post_id AND author_id = :account_id"),
        {"post_id": post_id, "account_id": account.account_id},
    )
    if not result.rowcount:
        raise ApiException("POST_NOT_FOUND", "This post is unavailable.", 404)
    record_audit_event(
        db,
        request,
        event_type="content.post_deleted",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
        metadata={"postId": post_id},
    )
    db.commit()


@router.get("/statuses/nearby", response_model=list[StatusResponse])
def list_nearby_statuses(
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> list[StatusResponse]:
    _require_ready(account)
    viewer = db.execute(
        text("SELECT identity FROM profiles WHERE account_id = :account_id"),
        {"account_id": account.account_id},
    ).mappings().first()
    if viewer is None:
        raise ApiException("NO_PROFILE", "Finish onboarding before viewing statuses.", 404)
    visible_rows = _visible_profile_rows(
        db,
        account.account_id,
        viewer["identity"],
        False,
    )
    visible_ids = [str(row["id"]) for row in visible_rows]
    visible_ids.append(account.account_id)
    rows = db.execute(
        text(
            """
            SELECT s.id, s.author_id, s.media_url, s.media_kind, s.created_at,
                   p.display_name, p.photos
            FROM member_statuses s
            JOIN profiles p ON p.account_id = s.author_id
            WHERE s.author_id IN :visible_ids AND s.expires_at > :now
            ORDER BY s.created_at DESC, s.id
            """
        ).bindparams(bindparam("visible_ids", expanding=True)),
        {"visible_ids": visible_ids, "now": _now()},
    ).mappings()
    result: list[StatusResponse] = []
    for row in rows:
        photos = json.loads(row["photos"]) if isinstance(row["photos"], str) else row["photos"]
        result.append(
            StatusResponse(
                id=str(row["id"]),
                author_id=str(row["author_id"]),
                author_name=row["display_name"],
                author_photo=photos[0] if photos else "",
                media=row["media_url"],
                kind=row["media_kind"],
                created_at=row["created_at"],
            )
        )
    record_audit_event(
        db,
        request,
        event_type="content.nearby_statuses_viewed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
        metadata={"statusCount": len(result)},
    )
    db.commit()
    return result
