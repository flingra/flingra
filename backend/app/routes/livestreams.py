import json
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.config import Settings
from app.dependencies import db_session
from app.errors import ApiException
from app.feature_schemas import LiveKitConnectionResponse, LiveStreamResponse, LiveStreamStartRequest
from app.livekit import create_room_token, delete_room
from app.routes.auth import IdentityVerifiedAccount, get_app_settings, require_csrf
from app.routes.profiles import (
    _distance_km,
    _effective_subscription_tier,
    _profile_coordinates,
    _require_discovery_ready,
    _visible_profile_rows,
)

router = APIRouter(prefix="/live-streams", tags=["livestream"])
DbSession = Annotated[Session, Depends(db_session)]
SettingsDependency = Annotated[Settings, Depends(get_app_settings)]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _viewer_profile(db: Session, account_id: str) -> dict[str, Any]:
    profile = db.execute(
        text(
            """
            SELECT identity, display_name, photos, subscription_tier, vip_expires_at,
                   latitude, longitude
            FROM profiles WHERE account_id = :account_id
            """
        ),
        {"account_id": account_id},
    ).mappings().first()
    if profile is None:
        raise ApiException("NO_PROFILE", "Finish your profile before using livestreams.", 404)
    return dict(profile)


def _visible_streams(
    db: Session,
    account_id: str,
    include_demo_profiles: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    viewer = _viewer_profile(db, account_id)
    visible_hosts = {
        str(row["id"]): row
        for row in _visible_profile_rows(
            db,
            account_id,
            viewer["identity"],
            include_demo_profiles,
        )
    }
    own = db.execute(
        text(
            """
            SELECT a.id, a.date_of_birth, p.display_name, p.bio, p.photos, p.videos,
                   p.age_range, p.area, p.latitude, p.longitude, p.live_latitude,
                   p.live_longitude, p.location_shared_at, p.interests, p.discoverable_by,
                   p.wants_to_discover, p.identity, p.show_identity, p.subscription_tier,
                   p.vip_expires_at, p.created_at, p.demo_cohort_id
            FROM accounts a JOIN profiles p ON p.account_id = a.id
            WHERE a.id = :account_id AND a.email_verified = TRUE
              AND p.onboarding_complete = TRUE AND p.document_verification = 'verified'
              AND p.moderation_status = 'approved'
            """
        ),
        {"account_id": account_id},
    ).mappings().first()
    if own is not None:
        visible_hosts[account_id] = dict(own)

    active_rows = db.execute(
        text(
            """
            SELECT id, host_account_id, room_name, title, started_at
            FROM live_streams
            WHERE status = 'live'
            ORDER BY started_at DESC, id
            """
        )
    ).mappings()
    return viewer, [
        {
            **visible_hosts[str(stream["host_account_id"])],
            **dict(stream),
            "host_account_id": str(stream["host_account_id"]),
        }
        for stream in active_rows
        if str(stream["host_account_id"]) in visible_hosts
    ]


def _stream_response(row: dict[str, Any]) -> LiveStreamResponse:
    photos = json.loads(row["photos"]) if isinstance(row["photos"], str) else row["photos"]
    videos = json.loads(row["videos"]) if isinstance(row["videos"], str) else row["videos"]
    public_video = next(
        (
            video.get("url")
            for video in videos or []
            if isinstance(video, dict) and not video.get("locked") and isinstance(video.get("url"), str)
        ),
        None,
    )
    host_id = str(row["host_account_id"])
    return LiveStreamResponse(
        id=str(row["id"]),
        host_id=host_id,
        host_name=row["display_name"],
        host_photo=photos[0] if photos else "",
        host_video=public_video,
        title=row["title"],
        started_at=row["started_at"],
        participant_ids=[host_id],
    )


@router.get("", response_model=list[LiveStreamResponse])
def list_live_streams(
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> list[LiveStreamResponse]:
    _require_discovery_ready(account)
    _, streams = _visible_streams(db, account.account_id, settings.demo_profiles_enabled)
    return [_stream_response(row) for row in streams]


@router.get("/nearby")
def list_live_streams_nearby(
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> list[dict[str, Any]]:
    _require_discovery_ready(account)
    viewer, streams = _visible_streams(db, account.account_id, settings.demo_profiles_enabled)
    viewer_is_vip = (
        _effective_subscription_tier(viewer["subscription_tier"], viewer["vip_expires_at"]) == "vip"
    )
    origin_latitude = float(viewer["latitude"]) if viewer["latitude"] is not None else None
    origin_longitude = float(viewer["longitude"]) if viewer["longitude"] is not None else None
    results = []
    for row in streams:
        response = _stream_response(row).model_dump(by_alias=True)
        host_is_vip = (
            _effective_subscription_tier(row["subscription_tier"], row["vip_expires_at"]) == "vip"
        )
        host_latitude, host_longitude = _profile_coordinates(row)
        distance = None
        if (
            origin_latitude is not None
            and origin_longitude is not None
            and host_latitude is not None
            and host_longitude is not None
        ):
            distance = round(
                _distance_km(
                    host_latitude,
                    host_longitude,
                    origin_latitude,
                    origin_longitude,
                ),
                1,
            )
        results.append(
            {
                **response,
                "hostArea": row["area"],
                "hostDistanceKm": distance,
                "hostSubscriptionTier": "vip" if host_is_vip else "free",
                "_vipBoost": 0 if viewer_is_vip and host_is_vip else 1,
            }
        )
    results.sort(
        key=lambda stream: (
            stream.pop("_vipBoost"),
            stream["hostDistanceKm"] is None,
            stream["hostDistanceKm"] if stream["hostDistanceKm"] is not None else float("inf"),
        )
    )
    return results


@router.post("", status_code=201, dependencies=[Depends(require_csrf)])
def start_live_stream(
    body: LiveStreamStartRequest,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> dict[str, Any]:
    _require_discovery_ready(account)
    profile = db.execute(
        text(
            """
            SELECT identity, display_name, photos
            FROM profiles WHERE account_id = :account_id
            """
            + (" FOR UPDATE" if db.get_bind().dialect.name != "sqlite" else "")
        ),
        {"account_id": account.account_id},
    ).mappings().first()
    if profile is None:
        raise ApiException("NO_PROFILE", "Finish your profile before going live.", 404)
    if profile["identity"] != "woman":
        raise ApiException("LIVESTREAM_RESTRICTED", "Livestreaming is available for female accounts only.", 403)
    existing = db.execute(
        text("SELECT id FROM live_streams WHERE host_account_id = :account_id AND status = 'live'"),
        {"account_id": account.account_id},
    ).scalar_one_or_none()
    if existing is not None:
        raise ApiException("STREAM_ALREADY_LIVE", "End your current stream before starting another.", 409)

    stream_id = uuid.uuid4().hex
    room_name = f"flingra_stream_{stream_id}"
    now = _now()
    url, token = create_room_token(
        settings,
        room_name=room_name,
        identity=account.account_id,
        can_publish=True,
    )
    title = body.title.strip() or f"{profile['display_name']} is live"
    db.execute(
        text(
            """
            INSERT INTO live_streams (
                id, host_account_id, room_name, title, status, started_at
            )
            VALUES (:id, :host_id, :room_name, :title, 'live', :started_at)
            """
        ),
        {
            "id": stream_id,
            "host_id": account.account_id,
            "room_name": room_name,
            "title": title,
            "started_at": now,
        },
    )
    record_audit_event(
        db,
        request,
        event_type="livestream.started",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
        metadata={"streamId": stream_id},
    )
    db.commit()
    photos = json.loads(profile["photos"]) if isinstance(profile["photos"], str) else profile["photos"]
    stream = LiveStreamResponse(
        id=stream_id,
        host_id=account.account_id,
        host_name=profile["display_name"],
        host_photo=photos[0] if photos else "",
        title=title,
        started_at=now,
        participant_ids=[account.account_id],
    )
    return {**stream.model_dump(by_alias=True), "liveKitUrl": url, "token": token}


@router.get("/{stream_id}", response_model=LiveStreamResponse)
def get_live_stream(
    stream_id: str,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> LiveStreamResponse:
    _require_discovery_ready(account)
    viewer, streams = _visible_streams(db, account.account_id, settings.demo_profiles_enabled)
    row = next((stream for stream in streams if str(stream["id"]) == stream_id), None)
    if row is None:
        raise ApiException("STREAM_NOT_FOUND", "This stream has ended or is unavailable.", 404)
    host_tier = _effective_subscription_tier(row["subscription_tier"], row["vip_expires_at"])
    viewer_tier = _effective_subscription_tier(viewer["subscription_tier"], viewer["vip_expires_at"])
    if host_tier == "vip" and viewer_tier != "vip" and str(row["host_account_id"]) != account.account_id:
        raise ApiException("VIP_REQUIRED", "Upgrade to VIP to join this member's stream.", 403)
    return _stream_response(row)


@router.post("/{stream_id}/token", response_model=LiveKitConnectionResponse, dependencies=[Depends(require_csrf)])
def get_live_stream_token(
    stream_id: str,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> LiveKitConnectionResponse:
    _require_discovery_ready(account)
    viewer, streams = _visible_streams(db, account.account_id, settings.demo_profiles_enabled)
    row = next((stream for stream in streams if str(stream["id"]) == stream_id), None)
    if row is None:
        raise ApiException("STREAM_NOT_FOUND", "This stream has ended or is unavailable.", 404)
    host = str(row["host_account_id"]) == account.account_id
    host_tier = _effective_subscription_tier(row["subscription_tier"], row["vip_expires_at"])
    viewer_tier = _effective_subscription_tier(viewer["subscription_tier"], viewer["vip_expires_at"])
    if not host and host_tier == "vip" and viewer_tier != "vip":
        raise ApiException("VIP_REQUIRED", "Upgrade to VIP to join this member's stream.", 403)
    url, token = create_room_token(
        settings,
        room_name=str(row["room_name"]),
        identity=account.account_id,
        can_publish=host,
    )
    return LiveKitConnectionResponse(url=url, token=token)


@router.delete("/{stream_id}", status_code=204, dependencies=[Depends(require_csrf)])
def end_live_stream(
    stream_id: str,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> None:
    row = db.execute(
        text(
            """
            SELECT room_name FROM live_streams
            WHERE id = :stream_id AND host_account_id = :account_id AND status = 'live'
            """
        ),
        {"stream_id": stream_id, "account_id": account.account_id},
    ).mappings().first()
    if row is None:
        raise ApiException("STREAM_NOT_FOUND", "This stream is unavailable.", 404)
    delete_room(settings, str(row["room_name"]))
    now = _now()
    db.execute(
        text(
            """
            UPDATE live_streams
            SET status = 'ended', ended_at = :now
            WHERE id = :stream_id AND host_account_id = :account_id AND status = 'live'
            """
        ),
        {"stream_id": stream_id, "account_id": account.account_id, "now": now},
    )
    record_audit_event(
        db,
        request,
        event_type="livestream.ended",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
        metadata={"streamId": stream_id},
    )
    db.commit()
