import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.config import Settings
from app.dependencies import db_session
from app.errors import ApiException, ServiceUnavailable
from app.feature_schemas import (
    LiveJoinRequestDecisionRequest,
    LiveJoinRequestResponse,
    LiveKitConnectionResponse,
    LiveStreamMemberResponse,
    LiveStreamMessageCreateRequest,
    LiveStreamMessageResponse,
    LiveStreamResponse,
    LiveStreamStartRequest,
)
from app.livekit import create_room_token, delete_room
from app.realtime import enqueue_realtime_event
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
PRESENCE_TTL = timedelta(seconds=45)
MESSAGE_ACCESS_TTL = timedelta(minutes=2)
MAX_PARTICIPANTS = 5


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _as_datetime(value: datetime | str) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


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


def _photos(value: Any) -> list[str]:
    parsed = json.loads(value) if isinstance(value, str) else value
    return parsed if isinstance(parsed, list) else []


def _first_photo(value: Any) -> str:
    photos = _photos(value)
    return str(photos[0]) if photos and isinstance(photos[0], str) else ""


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


def _stream_response(
    row: dict[str, Any],
    participant_ids: list[str] | None = None,
) -> LiveStreamResponse:
    photos = _photos(row["photos"])
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
        participant_ids=participant_ids or [host_id],
    )


def _stream_participant_ids(db: Session, stream_id: str) -> list[str]:
    rows = db.execute(
        text(
            """
            SELECT account_id
            FROM live_stream_participants
            WHERE stream_id = :stream_id AND role IN ('host', 'guest')
              AND (role = 'host' OR last_seen_at >= :cutoff)
            ORDER BY CASE role WHEN 'host' THEN 0 ELSE 1 END, joined_at, account_id
            """
        ),
        {"stream_id": stream_id, "cutoff": _now() - PRESENCE_TTL},
    ).scalars()
    return [str(account_id) for account_id in rows]


def _visible_stream_for_viewer(
    db: Session,
    account_id: str,
    settings: Settings,
    stream_id: str,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    viewer, streams = _visible_streams(db, account_id, settings.demo_profiles_enabled)
    row = next((stream for stream in streams if str(stream["id"]) == stream_id), None)
    if row is None:
        raise ApiException("STREAM_NOT_FOUND", "This stream has ended or is unavailable.", 404)
    host = str(row["host_account_id"]) == account_id
    host_tier = _effective_subscription_tier(row["subscription_tier"], row["vip_expires_at"])
    viewer_tier = _effective_subscription_tier(viewer["subscription_tier"], viewer["vip_expires_at"])
    if not host and host_tier == "vip" and viewer_tier != "vip":
        raise ApiException("VIP_REQUIRED", "Upgrade to VIP to join this member's stream.", 403)
    return viewer, row, host


def _upsert_presence(db: Session, stream_id: str, account_id: str, role: str, now: datetime) -> None:
    if db.get_bind().dialect.name == "sqlite":
        statement = """
            INSERT INTO live_stream_participants (stream_id, account_id, role, joined_at, last_seen_at)
            VALUES (:stream_id, :account_id, :role, :now, :now)
            ON CONFLICT(stream_id, account_id) DO UPDATE SET
                role = CASE
                    WHEN live_stream_participants.role IN ('host', 'guest')
                    THEN live_stream_participants.role ELSE excluded.role END,
                last_seen_at = excluded.last_seen_at
        """
    else:
        statement = """
            INSERT INTO live_stream_participants (stream_id, account_id, role, joined_at, last_seen_at)
            VALUES (:stream_id, :account_id, :role, :now, :now)
            ON DUPLICATE KEY UPDATE
                role = IF(role IN ('host', 'guest'), role, VALUES(role)),
                last_seen_at = VALUES(last_seen_at)
        """
    db.execute(
        text(statement),
        {"stream_id": stream_id, "account_id": account_id, "role": role, "now": now},
    )


def _require_stream_presence(
    db: Session,
    stream_id: str,
    account_id: str,
) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT role, last_seen_at
            FROM live_stream_participants
            WHERE stream_id = :stream_id AND account_id = :account_id
            """
        ),
        {"stream_id": stream_id, "account_id": account_id},
    ).mappings().first()
    if row is None or _as_datetime(row["last_seen_at"]) < _now() - MESSAGE_ACCESS_TTL:
        raise ApiException("STREAM_NOT_JOINED", "Join this stream before interacting.", 403)
    return dict(row)


def _broadcast_stream_event(
    db: Session,
    stream_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    recipients = db.execute(
        text(
            """
            SELECT account_id FROM live_stream_participants
            WHERE stream_id = :stream_id AND last_seen_at >= :cutoff
            """
        ),
        {"stream_id": stream_id, "cutoff": _now() - MESSAGE_ACCESS_TTL},
    ).scalars()
    for recipient_id in recipients:
        enqueue_realtime_event(db, str(recipient_id), event_type, payload)


def process_live_stream_lifecycle(
    db: Session,
    settings: Settings,
    *,
    limit: int = 100,
) -> int:
    now = _now()
    cutoff = now - timedelta(seconds=60)
    lock = " FOR UPDATE SKIP LOCKED" if db.get_bind().dialect.name != "sqlite" else ""
    rows = db.execute(
        text(
            """
            SELECT s.id, s.host_account_id, s.room_name, s.status
            FROM live_streams s
            WHERE (
                s.status = 'live'
                AND NOT EXISTS (
                    SELECT 1 FROM live_stream_participants p
                    WHERE p.stream_id = s.id AND p.role = 'host'
                      AND p.last_seen_at >= :cutoff
                )
            ) OR (s.status = 'ended' AND s.room_closed_at IS NULL)
            ORDER BY s.started_at, s.id
            LIMIT :limit
            """
            + lock
        ),
        {"cutoff": cutoff, "limit": limit},
    ).mappings().all()
    rooms: list[tuple[str, str]] = []
    for value in rows:
        row = dict(value)
        if row["status"] == "live":
            db.execute(
                text(
                    """
                    UPDATE live_streams
                    SET status = 'ended', ended_at = :now
                    WHERE id = :id AND status = 'live'
                    """
                ),
                {"now": now, "id": row["id"]},
            )
            db.execute(
                text(
                    """
                    UPDATE live_stream_join_requests
                    SET status = 'expired', responded_at = :now
                    WHERE stream_id = :id AND status = 'pending'
                    """
                ),
                {"now": now, "id": row["id"]},
            )
            _broadcast_stream_event(
                db,
                str(row["id"]),
                "livestream.ended",
                {"streamId": str(row["id"]), "hostId": str(row["host_account_id"])},
            )
            db.execute(
                text("DELETE FROM live_stream_participants WHERE stream_id = :id"),
                {"id": row["id"]},
            )
        rooms.append((str(row["id"]), str(row["room_name"])))
    db.commit()
    cleanup_failures: list[ServiceUnavailable] = []
    for stream_id, room_name in rooms:
        try:
            delete_room(settings, room_name)
        except ServiceUnavailable as exc:
            cleanup_failures.append(exc)
            continue
        db.execute(
            text("UPDATE live_streams SET room_closed_at = :now WHERE id = :id"),
            {"now": _now(), "id": stream_id},
        )
    db.commit()
    if cleanup_failures:
        raise ServiceUnavailable(
            f"LiveKit cleanup failed for {len(cleanup_failures)} livestream room(s); they will be retried."
        )
    return len(rows)


@router.get("", response_model=list[LiveStreamResponse])
def list_live_streams(
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> list[LiveStreamResponse]:
    _require_discovery_ready(account)
    _, streams = _visible_streams(db, account.account_id, settings.demo_profiles_enabled)
    return [
        _stream_response(row, _stream_participant_ids(db, str(row["id"])))
        for row in streams
    ]


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
        response = _stream_response(
            row,
            _stream_participant_ids(db, str(row["id"])),
        ).model_dump(by_alias=True)
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
    _upsert_presence(db, stream_id, account.account_id, "host", now)
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
    photos = _photos(profile["photos"])
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
    return _stream_response(
        row,
        _stream_participant_ids(db, str(row["id"])),
    )


@router.post("/{stream_id}/token", response_model=LiveKitConnectionResponse, dependencies=[Depends(require_csrf)])
def get_live_stream_token(
    stream_id: str,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> LiveKitConnectionResponse:
    _require_discovery_ready(account)
    _, row, host = _visible_stream_for_viewer(
        db, account.account_id, settings, stream_id
    )
    presence = db.execute(
        text(
            """
            SELECT role FROM live_stream_participants
            WHERE stream_id = :stream_id AND account_id = :account_id
            """
        ),
        {"stream_id": stream_id, "account_id": account.account_id},
    ).scalar_one_or_none()
    role = str(presence) if presence in {"host", "guest"} else "viewer"
    now = _now()
    if role == "guest":
        lock = " FOR UPDATE" if db.get_bind().dialect.name != "sqlite" else ""
        db.execute(
            text("SELECT id FROM live_streams WHERE id = :stream_id AND status = 'live'" + lock),
            {"stream_id": stream_id},
        ).first()
        active_speakers = int(
            db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM live_stream_participants
                    WHERE stream_id = :stream_id
                      AND account_id != :account_id
                      AND (role = 'host' OR (role = 'guest' AND last_seen_at >= :cutoff))
                    """
                ),
                {
                    "stream_id": stream_id,
                    "account_id": account.account_id,
                    "cutoff": now - PRESENCE_TTL,
                },
            ).scalar_one()
        )
        if active_speakers >= MAX_PARTICIPANTS:
            raise ApiException("STREAM_FULL", "This stream already has five active participants.", 409)
    _upsert_presence(db, stream_id, account.account_id, role, now)
    url, token = create_room_token(
        settings,
        room_name=str(row["room_name"]),
        identity=account.account_id,
        can_publish=role in {"host", "guest"},
    )
    db.commit()
    return LiveKitConnectionResponse(url=url, token=token)


@router.post(
    "/{stream_id}/heartbeat",
    status_code=204,
    dependencies=[Depends(require_csrf)],
)
def live_stream_heartbeat(
    stream_id: str,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> None:
    _, _, _ = _visible_stream_for_viewer(db, account.account_id, settings, stream_id)
    presence = _require_stream_presence(db, stream_id, account.account_id)
    _upsert_presence(db, stream_id, account.account_id, str(presence["role"]), _now())
    db.commit()


@router.delete(
    "/{stream_id}/participants/me",
    status_code=204,
    dependencies=[Depends(require_csrf)],
)
def leave_live_stream(
    stream_id: str,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> None:
    _, _, host = _visible_stream_for_viewer(db, account.account_id, settings, stream_id)
    if host:
        raise ApiException("HOST_MUST_END_STREAM", "The host must end the stream instead of leaving.", 409)
    presence = db.execute(
        text(
            """
            SELECT role FROM live_stream_participants
            WHERE stream_id = :stream_id AND account_id = :account_id
            """
        ),
        {"stream_id": stream_id, "account_id": account.account_id},
    ).scalar_one_or_none()
    if presence is None:
        return
    db.execute(
        text(
            "DELETE FROM live_stream_participants WHERE stream_id = :stream_id AND account_id = :account_id"
        ),
        {"stream_id": stream_id, "account_id": account.account_id},
    )
    db.commit()


@router.post(
    "/{stream_id}/join-requests",
    response_model=LiveJoinRequestResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def request_to_join_stream(
    stream_id: str,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> LiveJoinRequestResponse:
    _require_discovery_ready(account)
    _, stream, host = _visible_stream_for_viewer(db, account.account_id, settings, stream_id)
    if host:
        raise ApiException("HOST_CANNOT_JOIN", "The stream host is already a participant.", 409)
    lock = " FOR UPDATE" if db.get_bind().dialect.name != "sqlite" else ""
    db.execute(
        text("SELECT id FROM live_streams WHERE id = :stream_id AND status = 'live'" + lock),
        {"stream_id": stream_id},
    ).first()
    blocked = db.execute(
        text(
            """
            SELECT 1 FROM safety_blocks
            WHERE (blocker_id = :viewer AND blocked_id = :host)
               OR (blocker_id = :host AND blocked_id = :viewer)
            LIMIT 1
            """
        ),
        {"viewer": account.account_id, "host": stream["host_account_id"]},
    ).first()
    if blocked is not None:
        raise ApiException("MEMBER_BLOCKED", "Joining this stream is unavailable.", 403)
    participant = db.execute(
        text(
            """
            SELECT role FROM live_stream_participants
            WHERE stream_id = :stream_id AND account_id = :account_id
              AND role IN ('host', 'guest')
              AND (role = 'host' OR last_seen_at >= :cutoff)
            """
        ),
        {
            "stream_id": stream_id,
            "account_id": account.account_id,
            "cutoff": _now() - PRESENCE_TTL,
        },
    ).scalar_one_or_none()
    if participant is not None:
        raise ApiException("ALREADY_STREAM_PARTICIPANT", "You are already a guest in this stream.", 409)
    pending = db.execute(
        text(
            """
            SELECT r.id, r.stream_id, r.requester_id, r.status, r.created_at,
                   p.display_name, p.photos
            FROM live_stream_join_requests r
            JOIN profiles p ON p.account_id = r.requester_id
            WHERE r.stream_id = :stream_id AND r.requester_id = :account_id
              AND r.status = 'pending'
            ORDER BY r.created_at DESC LIMIT 1
            """
        ),
        {"stream_id": stream_id, "account_id": account.account_id},
    ).mappings().first()
    if pending is None:
        profile = _viewer_profile(db, account.account_id)
        request_id = uuid.uuid4().hex
        now = _now()
        db.execute(
            text(
                """
                INSERT INTO live_stream_join_requests (id, stream_id, requester_id, status, created_at)
                VALUES (:id, :stream_id, :requester_id, 'pending', :created_at)
                """
            ),
            {
                "id": request_id,
                "stream_id": stream_id,
                "requester_id": account.account_id,
                "created_at": now,
            },
        )
        photos = _photos(profile["photos"])
        response = LiveJoinRequestResponse(
            id=request_id,
            stream_id=stream_id,
            requester_id=account.account_id,
            requester_name=profile["display_name"],
            requester_photo=photos[0] if photos else "",
            status="pending",
            created_at=now,
        )
    else:
        photos = _photos(pending["photos"])
        response = LiveJoinRequestResponse(
            id=str(pending["id"]),
            stream_id=str(pending["stream_id"]),
            requester_id=str(pending["requester_id"]),
            requester_name=pending["display_name"],
            requester_photo=photos[0] if photos else "",
            status="pending",
            created_at=pending["created_at"],
        )
    if pending is None:
        enqueue_realtime_event(
            db,
            str(stream["host_account_id"]),
            "livestream.join_request",
            response.model_dump(by_alias=True),
        )
        record_audit_event(
            db,
            request,
            event_type="livestream.join_requested",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=str(stream["host_account_id"]),
            outcome="success",
            metadata={"streamId": stream_id, "requestId": response.id},
        )
    db.commit()
    return response


@router.get(
    "/{stream_id}/join-requests",
    response_model=list[LiveJoinRequestResponse],
)
def list_stream_join_requests(
    stream_id: str,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> list[LiveJoinRequestResponse]:
    _, stream, host = _visible_stream_for_viewer(db, account.account_id, settings, stream_id)
    if not host:
        raise ApiException("STREAM_HOST_REQUIRED", "Only the host can view join requests.", 403)
    rows = db.execute(
        text(
            """
            SELECT r.id, r.stream_id, r.requester_id, r.status, r.created_at,
                   p.display_name, p.photos
            FROM live_stream_join_requests r
            JOIN profiles p ON p.account_id = r.requester_id
            WHERE r.stream_id = :stream_id AND r.status = 'pending'
            ORDER BY r.created_at, r.id
            LIMIT 50
            """
        ),
        {"stream_id": stream_id},
    ).mappings()
    return [
        LiveJoinRequestResponse(
            id=str(row["id"]),
            stream_id=str(row["stream_id"]),
            requester_id=str(row["requester_id"]),
            requester_name=row["display_name"],
            requester_photo=_first_photo(row["photos"]),
            status=row["status"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


@router.patch(
    "/{stream_id}/join-requests/{request_id}",
    response_model=LiveJoinRequestResponse,
    dependencies=[Depends(require_csrf)],
)
def respond_to_join_request(
    stream_id: str,
    request_id: str,
    body: LiveJoinRequestDecisionRequest,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> LiveJoinRequestResponse:
    _, stream, host = _visible_stream_for_viewer(db, account.account_id, settings, stream_id)
    if not host:
        raise ApiException("STREAM_HOST_REQUIRED", "Only the host can respond to join requests.", 403)
    lock = " FOR UPDATE" if db.get_bind().dialect.name != "sqlite" else ""
    db.execute(
        text("SELECT id FROM live_streams WHERE id = :stream_id AND status = 'live'" + lock),
        {"stream_id": stream_id},
    ).first()
    row = db.execute(
        text(
            """
            SELECT id, requester_id, status, created_at
            FROM live_stream_join_requests
            WHERE id = :request_id AND stream_id = :stream_id
            """
            + lock
        ),
        {"request_id": request_id, "stream_id": stream_id},
    ).mappings().first()
    if row is None:
        raise ApiException("JOIN_REQUEST_NOT_FOUND", "This join request is unavailable.", 404)
    if row["status"] != "pending":
        raise ApiException("JOIN_REQUEST_RESOLVED", "This join request has already been resolved.", 409)

    requester_id = str(row["requester_id"])
    now = _now()
    status = "accepted" if body.accept else "declined"
    if body.accept:
        active_speakers = int(
            db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM live_stream_participants
                    WHERE stream_id = :stream_id
                      AND (role = 'host' OR (role = 'guest' AND last_seen_at >= :cutoff))
                    """
                ),
                {"stream_id": stream_id, "cutoff": now - PRESENCE_TTL},
            ).scalar_one()
        )
        if active_speakers >= MAX_PARTICIPANTS:
            raise ApiException("STREAM_FULL", "This stream already has five active participants.", 409)
        host_profile = _viewer_profile(db, account.account_id)
        requester_visible = _visible_profile_rows(
            db,
            account.account_id,
            host_profile["identity"],
            settings.demo_profiles_enabled,
            profile_id=requester_id,
        )
        if not requester_visible:
            raise ApiException("MEMBER_UNAVAILABLE", "This requester is no longer available.", 409)
        db.execute(
            text(
                """
                INSERT INTO live_stream_participants (stream_id, account_id, role, joined_at, last_seen_at)
                VALUES (:stream_id, :account_id, 'guest', :now, :now)
                ON DUPLICATE KEY UPDATE role = 'guest', last_seen_at = VALUES(last_seen_at)
                """
                if db.get_bind().dialect.name != "sqlite"
                else """
                INSERT INTO live_stream_participants (stream_id, account_id, role, joined_at, last_seen_at)
                VALUES (:stream_id, :account_id, 'guest', :now, :now)
                ON CONFLICT(stream_id, account_id) DO UPDATE SET
                    role = 'guest', last_seen_at = excluded.last_seen_at
                """
            ),
            {"stream_id": stream_id, "account_id": requester_id, "now": now},
        )
    db.execute(
        text(
            """
            UPDATE live_stream_join_requests
            SET status = :status, responded_at = :now
            WHERE id = :request_id AND status = 'pending'
            """
        ),
        {"status": status, "now": now, "request_id": request_id},
    )
    requester_profile = db.execute(
        text("SELECT display_name, photos FROM profiles WHERE account_id = :id"),
        {"id": requester_id},
    ).mappings().one()
    photos = _photos(requester_profile["photos"])
    response = LiveJoinRequestResponse(
        id=request_id,
        stream_id=stream_id,
        requester_id=requester_id,
        requester_name=requester_profile["display_name"],
        requester_photo=photos[0] if photos else "",
        status=status,
        created_at=row["created_at"],
    )
    enqueue_realtime_event(
        db,
        requester_id,
        "livestream.join_request_updated",
        response.model_dump(by_alias=True),
    )
    if body.accept:
        join_message_id = uuid.uuid4().hex
        db.execute(
            text(
                """
                INSERT INTO live_stream_messages
                    (id, stream_id, author_id, kind, message_text, created_at)
                VALUES (:id, :stream_id, :author_id, 'join', 'joined the live', :now)
                """
            ),
            {
                "id": join_message_id,
                "stream_id": stream_id,
                "author_id": requester_id,
                "now": now,
            },
        )
        _broadcast_stream_event(
            db,
            stream_id,
            "livestream.participant_joined",
            {"streamId": stream_id, "accountId": requester_id},
        )
    record_audit_event(
        db,
        request,
        event_type=f"livestream.join_{status}",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=requester_id,
        outcome="success",
        metadata={"streamId": stream_id, "requestId": request_id},
    )
    db.commit()
    return response


@router.get(
    "/{stream_id}/participants",
    response_model=list[LiveStreamMemberResponse],
)
def list_stream_participants(
    stream_id: str,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> list[LiveStreamMemberResponse]:
    _visible_stream_for_viewer(db, account.account_id, settings, stream_id)
    rows = db.execute(
        text(
            """
            SELECT p.account_id, p.display_name, p.photos
            FROM live_stream_participants s
            JOIN profiles p ON p.account_id = s.account_id
            WHERE s.stream_id = :stream_id AND s.role IN ('host', 'guest')
              AND (s.role = 'host' OR s.last_seen_at >= :cutoff)
            ORDER BY CASE s.role WHEN 'host' THEN 0 ELSE 1 END, s.joined_at, s.account_id
            """
        ),
        {"stream_id": stream_id, "cutoff": _now() - PRESENCE_TTL},
    ).mappings()
    return [
        LiveStreamMemberResponse(
            id=str(row["account_id"]),
            name=row["display_name"],
            photo=_first_photo(row["photos"]),
        )
        for row in rows
    ]


@router.get(
    "/{stream_id}/viewers",
    response_model=list[LiveStreamMemberResponse],
)
def list_stream_viewers(
    stream_id: str,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> list[LiveStreamMemberResponse]:
    _visible_stream_for_viewer(db, account.account_id, settings, stream_id)
    rows = db.execute(
        text(
            """
            SELECT p.account_id, p.display_name, p.photos
            FROM live_stream_participants s
            JOIN profiles p ON p.account_id = s.account_id
            WHERE s.stream_id = :stream_id AND s.role = 'viewer'
              AND s.last_seen_at >= :cutoff
            ORDER BY s.last_seen_at DESC, s.account_id
            LIMIT 50
            """
        ),
        {"stream_id": stream_id, "cutoff": _now() - PRESENCE_TTL},
    ).mappings()
    return [
        LiveStreamMemberResponse(
            id=str(row["account_id"]),
            name=row["display_name"],
            photo=_first_photo(row["photos"]),
        )
        for row in rows
    ]


@router.get(
    "/{stream_id}/messages",
    response_model=list[LiveStreamMessageResponse],
)
def list_stream_messages(
    stream_id: str,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> list[LiveStreamMessageResponse]:
    _visible_stream_for_viewer(db, account.account_id, settings, stream_id)
    _require_stream_presence(db, stream_id, account.account_id)
    rows = db.execute(
        text(
            """
            SELECT m.id, m.stream_id, m.author_id, m.kind, m.message_text, m.gift_id,
                   m.created_at, p.display_name
            FROM live_stream_messages m
            JOIN profiles p ON p.account_id = m.author_id
            WHERE m.stream_id = :stream_id
            ORDER BY m.created_at DESC, m.id DESC
            LIMIT 100
            """
        ),
        {"stream_id": stream_id},
    ).mappings().all()
    return [
        LiveStreamMessageResponse(
            id=str(row["id"]),
            stream_id=str(row["stream_id"]),
            author_id=str(row["author_id"]),
            author_name=row["display_name"],
            kind=row["kind"],
            text=row["message_text"],
            gift_id=str(row["gift_id"]) if row["gift_id"] else None,
            created_at=row["created_at"],
        )
        for row in reversed(rows)
    ]


@router.post(
    "/{stream_id}/messages",
    response_model=LiveStreamMessageResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def send_stream_message(
    stream_id: str,
    body: LiveStreamMessageCreateRequest,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> LiveStreamMessageResponse:
    _, stream, _ = _visible_stream_for_viewer(db, account.account_id, settings, stream_id)
    presence = _require_stream_presence(db, stream_id, account.account_id)
    if presence["role"] == "viewer":
        blocked = db.execute(
            text(
                """
                SELECT 1 FROM safety_blocks
                WHERE (blocker_id = :sender AND blocked_id = :host)
                   OR (blocker_id = :host AND blocked_id = :sender)
                LIMIT 1
                """
            ),
            {"sender": account.account_id, "host": stream["host_account_id"]},
        ).first()
        if blocked is not None:
            raise ApiException("MEMBER_BLOCKED", "Messaging in this stream is unavailable.", 403)

    gift_id = None
    message_text = body.text.strip()
    if not message_text:
        raise ApiException("MESSAGE_REQUIRED", "Enter a message.")
    if body.kind == "gift":
        if presence["role"] == "host":
            raise ApiException("GIFT_RECIPIENT_INVALID", "The host cannot send a gift to themself.", 400)
        if body.gift_id is None:
            raise ApiException("GIFT_REQUIRED", "Choose a gift to send.", 400)
        gift = db.execute(
            text("SELECT name, price_kobo FROM gift_catalog WHERE id = :id AND active = TRUE"),
            {"id": body.gift_id},
        ).mappings().first()
        if gift is None:
            raise ApiException("GIFT_NOT_FOUND", "That gift is not available.", 404)
        inventory = db.execute(
            text(
                """
                UPDATE gift_inventory SET quantity = quantity - 1
                WHERE account_id = :account_id AND gift_type_id = :gift_id AND quantity > 0
                """
            ),
            {"account_id": account.account_id, "gift_id": body.gift_id},
        )
        if inventory.rowcount != 1:
            raise ApiException("GIFT_NOT_OWNED", "Buy or earn this gift before sending it.", 409)
        gift_id = body.gift_id
        message_text = f"sent {gift['name']}"
        db.execute(
            text(
                """
                INSERT INTO received_gifts
                    (id, recipient_id, sender_id, gift_type_id, value_kobo, redeemed, created_at)
                VALUES
                    (:id, :recipient_id, :sender_id, :gift_type_id, :value_kobo, FALSE, :created_at)
                """
            ),
            {
                "id": uuid.uuid4().hex,
                "recipient_id": str(stream["host_account_id"]),
                "sender_id": account.account_id,
                "gift_type_id": gift_id,
                "value_kobo": gift["price_kobo"],
                "created_at": _now(),
            },
        )
    elif body.gift_id is not None:
        raise ApiException("INVALID_GIFT", "A gift ID is valid only for a gift message.", 400)

    message_id = uuid.uuid4().hex
    now = _now()
    profile = _viewer_profile(db, account.account_id)
    db.execute(
        text(
            """
            INSERT INTO live_stream_messages
                (id, stream_id, author_id, kind, message_text, gift_id, created_at)
            VALUES
                (:id, :stream_id, :author_id, :kind, :message_text, :gift_id, :created_at)
            """
        ),
        {
            "id": message_id,
            "stream_id": stream_id,
            "author_id": account.account_id,
            "kind": body.kind,
            "message_text": message_text,
            "gift_id": gift_id,
            "created_at": now,
        },
    )
    response = LiveStreamMessageResponse(
        id=message_id,
        stream_id=stream_id,
        author_id=account.account_id,
        author_name=profile["display_name"],
        kind=body.kind,
        text=message_text,
        gift_id=gift_id,
        created_at=now,
    )
    _broadcast_stream_event(
        db,
        stream_id,
        "livestream.message",
        response.model_dump(by_alias=True),
    )
    record_audit_event(
        db,
        request,
        event_type="livestream.message_sent",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=str(stream["host_account_id"]),
        outcome="success",
        metadata={"streamId": stream_id, "messageId": message_id, "kind": body.kind},
    )
    db.commit()
    return response


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
            SELECT room_name, status, room_closed_at FROM live_streams
            WHERE id = :stream_id AND host_account_id = :account_id
              AND status IN ('live', 'ended')
            """
            + (" FOR UPDATE" if db.get_bind().dialect.name != "sqlite" else "")
        ),
        {"stream_id": stream_id, "account_id": account.account_id},
    ).mappings().first()
    if row is None:
        raise ApiException("STREAM_NOT_FOUND", "This stream is unavailable.", 404)
    if row["room_closed_at"] is not None:
        return
    if row["status"] == "live":
        now = _now()
        _broadcast_stream_event(
            db,
            stream_id,
            "livestream.ended",
            {"streamId": stream_id, "hostId": account.account_id},
        )
        db.execute(
            text(
                """
                UPDATE live_stream_join_requests
                SET status = 'expired', responded_at = :now
                WHERE stream_id = :stream_id AND status = 'pending'
                """
            ),
            {"stream_id": stream_id, "now": now},
        )
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
        db.execute(
            text("DELETE FROM live_stream_participants WHERE stream_id = :stream_id"),
            {"stream_id": stream_id},
        )
        db.commit()
    delete_room(settings, str(row["room_name"]))
    db.execute(
        text("UPDATE live_streams SET room_closed_at = :now WHERE id = :stream_id"),
        {"now": _now(), "stream_id": stream_id},
    )
    db.commit()
