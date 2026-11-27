import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.config import Settings
from app.dependencies import db_session
from app.errors import ApiException
from app.routes.auth import CurrentAccount, IdentityVerifiedAccount, get_app_settings, require_csrf
from app.schemas import (
    AudiencePreference,
    DiscoveryFeedResponse,
    DiscoveryProfileResponse,
    LiveLocationUpdate,
    LocationSharingResponse,
    OwnProfilePatch,
    OwnProfileResponse,
    ProfileSearchResult,
)

router = APIRouter(prefix="/profiles", tags=["profiles"])
discovery_router = APIRouter(prefix="/discovery", tags=["discovery"])
DISCOVERY_PAGE_SIZE = 6
PROFILE_SEARCH_LIMIT = 10
EARTH_RADIUS_KM = 6371.0
LIVE_LOCATION_TTL = timedelta(minutes=5)
USERNAME_CHANGE_COOLDOWN = timedelta(days=60)
DISPLAY_NAME_CHANGE_COOLDOWN = timedelta(days=21)


def _visible_profile_rows(
    db: Session,
    viewer_id: str,
    viewer_identity: str,
    include_demo_profiles: bool,
    profile_id: str | None = None,
    search_term: str | None = None,
    limit: int | None = None,
    min_age: int | None = None,
    max_age: int | None = None,
    target_identity: str | None = None,
) -> list[dict[str, Any]]:
    viewer_audience = {"man": "men", "woman": "women"}.get(viewer_identity)
    profile_condition = "AND a.id = :profile_id" if profile_id is not None else ""
    search_condition = ""
    age_condition = ""
    identity_condition = ""
    order_clause = "ORDER BY p.created_at DESC, a.id ASC"
    limit_clause = ""
    parameters: dict[str, Any] = {
        "viewer_id": viewer_id,
        "viewer_audience": viewer_audience,
        "include_demo_profiles": include_demo_profiles,
    }
    if profile_id is not None:
        parameters["profile_id"] = profile_id
    if search_term is not None:
        escaped = search_term.lower().replace("!", "!!").replace("%", "!%").replace("_", "!_")
        parameters.update(
            search_exact=search_term.lower(),
            search_prefix=f"{escaped}%",
            search_pattern=f"%{escaped}%",
        )
        search_condition = """
                  AND (
                      LOWER(p.username) LIKE :search_pattern ESCAPE '!'
                      OR LOWER(p.display_name) LIKE :search_pattern ESCAPE '!'
                  )
        """
        order_clause = """
                ORDER BY CASE
                    WHEN LOWER(p.username) = :search_exact THEN 0
                    WHEN LOWER(p.display_name) = :search_exact THEN 1
                    WHEN LOWER(p.username) LIKE :search_prefix ESCAPE '!' THEN 2
                    WHEN LOWER(p.display_name) LIKE :search_prefix ESCAPE '!' THEN 3
                    ELSE 4
                END, p.created_at DESC, a.id ASC
        """
    if limit is not None:
        parameters["result_limit"] = limit
        limit_clause = "LIMIT :result_limit"
    if min_age is not None and max_age is not None:
        today = date.today()
        parameters["youngest_birth_date"] = _date_years_ago(today, min_age)
        parameters["oldest_birth_date"] = _date_years_ago(today, max_age + 1)
        age_condition = """
                  AND a.date_of_birth > :oldest_birth_date
                  AND a.date_of_birth <= :youngest_birth_date
        """
    if target_identity is not None:
        parameters["target_identity"] = target_identity
        identity_condition = "AND p.identity = :target_identity"
    return list(
        db.execute(
            text(
                f"""
                SELECT a.id, a.date_of_birth,
                       p.username, p.display_name, p.bio, p.photos, p.videos, p.age_range, p.area,
                       p.latitude, p.longitude, p.live_latitude, p.live_longitude,
                       p.location_shared_at, p.interests, p.discoverable_by,
                       p.wants_to_discover, p.identity, p.show_identity,
                       p.subscription_tier, p.vip_expires_at, p.created_at, p.demo_cohort_id
                FROM profiles p
                JOIN accounts a ON a.id = p.account_id
                WHERE a.id != :viewer_id
                  AND a.account_state NOT IN ('deletion_requested', 'deleted')
                  AND a.email_verified = TRUE
                  AND p.onboarding_complete = TRUE
                  AND p.moderation_status = 'approved'
                  AND p.document_verification = 'verified'
                  AND (:include_demo_profiles = TRUE OR p.demo_cohort_id IS NULL)
                  AND NOT EXISTS (
                      SELECT 1 FROM safety_blocks b
                      WHERE (b.blocker_id = :viewer_id AND b.blocked_id = a.id)
                         OR (b.blocker_id = a.id AND b.blocked_id = :viewer_id)
                  )
                  AND (
                      p.discoverable_by = 'everyone'
                      OR (:viewer_audience IS NOT NULL AND p.discoverable_by = :viewer_audience)
                  )
                  AND (
                      p.wants_to_discover = 'everyone'
                      OR (:viewer_audience IS NOT NULL AND p.wants_to_discover = :viewer_audience)
                  )
                  {age_condition}
                  {identity_condition}
                  {search_condition}
                  {profile_condition}
                {order_clause}
                {limit_clause}
                """
            ),
            parameters,
        ).mappings()
    )


def _parse_json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return json.loads(value) if isinstance(value, str) else list(value)


def _profile_videos(value: Any) -> list[Any]:
    videos = _parse_json_list(value)
    normalized: list[Any] = []
    for video in videos:
        if not isinstance(video, dict):
            normalized.append(video)
            continue
        item = dict(video)
        for price_key in ("priceNaira", "price_naira"):
            price = item.get(price_key)
            if isinstance(price, int) and not isinstance(price, bool) and price > 3_000:
                item[price_key] = 3_000
        normalized.append(item)
    return normalized


def _parse_date(value: date | str) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def _date_years_ago(value: date, years: int) -> date:
    target_year = value.year - years
    try:
        return value.replace(year=target_year)
    except ValueError:
        return value.replace(year=target_year, day=28)


def _effective_subscription_tier(tier: str, expires_at: datetime | str | None) -> str:
    if tier != "vip" or expires_at is None:
        return tier
    expiry = expires_at if isinstance(expires_at, datetime) else datetime.fromisoformat(expires_at)
    if expiry.tzinfo is not None:
        expiry = expiry.astimezone(timezone.utc).replace(tzinfo=None)
    return "free" if expiry <= datetime.now(timezone.utc).replace(tzinfo=None) else "vip"


def _current_age(birth_date: date | str) -> int:
    born = _parse_date(birth_date)
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def _age_range(age: int) -> str:
    lower = (age // 5) * 5
    return f"{lower}–{lower + 5}"


def _distance_km(
    latitude: float,
    longitude: float,
    origin_latitude: float,
    origin_longitude: float,
) -> float:
    radians = math.radians
    latitude_delta = radians(latitude - origin_latitude)
    longitude_delta = radians(longitude - origin_longitude)
    origin_latitude_radians = radians(origin_latitude)
    latitude_radians = radians(latitude)
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(origin_latitude_radians)
        * math.cos(latitude_radians)
        * math.sin(longitude_delta / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(min(1.0, haversine)))


def _location_sharing_active(shared_at: datetime | str | None) -> bool:
    if shared_at is None:
        return False
    timestamp = shared_at if isinstance(shared_at, datetime) else datetime.fromisoformat(shared_at)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
    return timestamp >= datetime.now(timezone.utc).replace(tzinfo=None) - LIVE_LOCATION_TTL


def _profile_coordinates(row: dict[str, Any]) -> tuple[float | None, float | None]:
    if (
        _location_sharing_active(row["location_shared_at"])
        and row["live_latitude"] is not None
        and row["live_longitude"] is not None
    ):
        return float(row["live_latitude"]), float(row["live_longitude"])
    latitude = float(row["latitude"]) if row["latitude"] is not None else None
    longitude = float(row["longitude"]) if row["longitude"] is not None else None
    return latitude, longitude


def _member_profile(
    row: dict[str, Any],
    distance_km: float | None,
    *,
    include_video_previews: bool = False,
) -> DiscoveryProfileResponse:
    latitude, longitude = _profile_coordinates(row)
    videos = _profile_videos(row["videos"])
    if not include_video_previews:
        videos = [
            {
                key: value
                for key, value in video.items()
                if key not in {"previewImage", "preview_image"}
            }
            if isinstance(video, dict)
            else video
            for video in videos
        ]
    return DiscoveryProfileResponse(
        id=str(row["id"]),
        username=row["username"],
        display_name=row["display_name"],
        bio=row["bio"],
        photos=_parse_json_list(row["photos"]),
        videos=videos or None,
        age_range=_age_range(_current_age(row["date_of_birth"])),
        area=row["area"],
        latitude=round(latitude, 2) if latitude is not None else None,
        longitude=round(longitude, 2) if longitude is not None else None,
        distance_km=round(distance_km, 1) if distance_km is not None else None,
        interests=_parse_json_list(row["interests"]),
        discoverable_by=row["discoverable_by"],
        wants_to_discover=row["wants_to_discover"],
        identity=row["identity"],
        show_identity=bool(row["show_identity"]),
        subscription_tier=_effective_subscription_tier(row["subscription_tier"], row["vip_expires_at"]),
        is_demo=row["demo_cohort_id"] is not None,
    )


def _viewer_profile(db: Session, account_id: str) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT identity, subscription_tier, vip_expires_at, latitude, longitude
            FROM profiles
            WHERE account_id = :account_id
            """
        ),
        {"account_id": account_id},
    ).mappings().first()
    if row is None:
        raise ApiException("NO_PROFILE", "Finish onboarding to create your profile.", 404)
    profile = dict(row)
    profile["subscription_tier"] = _effective_subscription_tier(
        profile["subscription_tier"],
        profile["vip_expires_at"],
    )
    return profile


def _require_discovery_ready(account: IdentityVerifiedAccount) -> None:
    if not account["email_verified"]:
        raise ApiException("CONTACT_NOT_VERIFIED", "Verify your contact before discovering profiles.", 403)
    if not account["onboarding_complete"]:
        raise ApiException("ONBOARDING_REQUIRED", "Complete onboarding before discovering profiles.", 403)


@router.get("/me", response_model=OwnProfileResponse)
def get_own_profile(
    request: Request,
    account: CurrentAccount,
    db: Annotated[Session, Depends(db_session)],
) -> OwnProfileResponse:
    row = db.execute(
        text(
            """
            SELECT a.date_of_birth,
                   p.username, p.username_changed_at, p.display_name_changed_at,
                   p.display_name, p.bio, p.photos, p.videos, p.age_range, p.area,
                   p.latitude, p.longitude,
                   p.distance_km, p.interests, p.discoverable_by, p.wants_to_discover,
                   p.identity, p.show_identity, p.subscription_tier, p.moderation_status,
                   p.two_factor_enabled, p.two_factor_method, p.onboarding_complete,
                   p.document_verification,
                   p.document_type, p.vip_expires_at, p.location_shared_at
            FROM profiles p
            JOIN accounts a ON a.id = p.account_id
            WHERE p.account_id = :account_id
            """
        ),
        {"account_id": account.account_id},
    ).mappings().first()
    if row is None:
        raise ApiException("NO_PROFILE", "Finish onboarding to create your profile.", 404)

    record_audit_event(
        db,
        request,
        event_type="profile.own_viewed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
    )
    db.commit()
    profile = dict(row)
    profile["id"] = account.account_id
    username_available_at = _change_available_at(
        profile["username_changed_at"], USERNAME_CHANGE_COOLDOWN
    )
    display_name_available_at = _change_available_at(
        profile["display_name_changed_at"], DISPLAY_NAME_CHANGE_COOLDOWN
    )
    profile["username_change_available_at"] = (
        username_available_at.replace(tzinfo=timezone.utc) if username_available_at else None
    )
    profile["display_name_change_available_at"] = (
        display_name_available_at.replace(tzinfo=timezone.utc) if display_name_available_at else None
    )
    profile["distance_km"] = float(profile["distance_km"])
    profile["location_sharing_enabled"] = _location_sharing_active(profile["location_shared_at"])
    if isinstance(profile["photos"], str):
        profile["photos"] = json.loads(profile["photos"])
    if isinstance(profile["interests"], str):
        profile["interests"] = json.loads(profile["interests"])
    if isinstance(profile["videos"], str):
        profile["videos"] = _profile_videos(profile["videos"])
    elif profile["videos"] is not None:
        profile["videos"] = _profile_videos(profile["videos"])
    return OwnProfileResponse.model_validate(profile)


def _change_available_at(
    changed_at: datetime | str | None,
    cooldown: timedelta,
) -> datetime | None:
    if changed_at is None:
        return None
    timestamp = changed_at if isinstance(changed_at, datetime) else datetime.fromisoformat(changed_at)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
    return timestamp + cooldown


@router.put(
    "/me/location-sharing",
    response_model=LocationSharingResponse,
    dependencies=[Depends(require_csrf)],
)
def publish_live_location(
    request: Request,
    payload: LiveLocationUpdate,
    account: IdentityVerifiedAccount,
    db: Annotated[Session, Depends(db_session)],
) -> LocationSharingResponse:
    _require_discovery_ready(account)
    previous = db.execute(
        text("SELECT location_shared_at FROM profiles WHERE account_id = :account_id"),
        {"account_id": account.account_id},
    ).mappings().first()
    if previous is None:
        raise ApiException("NO_PROFILE", "Finish onboarding to create your profile.", 404)
    was_sharing = _location_sharing_active(previous["location_shared_at"])
    db.execute(
        text(
            """
            UPDATE profiles
            SET live_latitude = :latitude,
                live_longitude = :longitude,
                location_shared_at = :shared_at
            WHERE account_id = :account_id
            """
        ),
        {
            "latitude": payload.latitude,
            "longitude": payload.longitude,
            "shared_at": datetime.now(timezone.utc).replace(tzinfo=None),
            "account_id": account.account_id,
        },
    )
    if not was_sharing:
        record_audit_event(
            db,
            request,
            event_type="location.sharing_enabled",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=account.account_id,
            outcome="success",
        )
    db.commit()
    return LocationSharingResponse(location_sharing_enabled=True)


@router.delete(
    "/me/location-sharing",
    response_model=LocationSharingResponse,
    dependencies=[Depends(require_csrf)],
)
def stop_live_location_sharing(
    request: Request,
    account: IdentityVerifiedAccount,
    db: Annotated[Session, Depends(db_session)],
) -> LocationSharingResponse:
    _require_discovery_ready(account)
    previous = db.execute(
        text("SELECT location_shared_at FROM profiles WHERE account_id = :account_id"),
        {"account_id": account.account_id},
    ).mappings().first()
    if previous is None:
        raise ApiException("NO_PROFILE", "Finish onboarding to create your profile.", 404)
    was_sharing = _location_sharing_active(previous["location_shared_at"])
    db.execute(
        text(
            """
            UPDATE profiles
            SET live_latitude = NULL,
                live_longitude = NULL,
                location_shared_at = NULL
            WHERE account_id = :account_id
            """
        ),
        {"account_id": account.account_id},
    )
    if was_sharing:
        record_audit_event(
            db,
            request,
            event_type="location.sharing_disabled",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=account.account_id,
            outcome="success",
        )
    db.commit()
    return LocationSharingResponse(location_sharing_enabled=False)


@router.patch("/me", response_model=OwnProfileResponse, dependencies=[Depends(require_csrf)])
def save_own_profile(
    request: Request,
    payload: OwnProfilePatch,
    account: CurrentAccount,
    db: Annotated[Session, Depends(db_session)],
) -> OwnProfileResponse:
    changes = payload.model_dump(exclude_unset=True, by_alias=False)
    changes.pop("distance_km", None)
    if "username" in changes and changes["username"] is None:
        raise ApiException("USERNAME_REQUIRED", "Choose a username to continue.")
    if not changes:
        return get_own_profile(request, account, db)

    profile_state = db.execute(
        text(
            """
            SELECT username, username_changed_at, display_name, display_name_changed_at,
                   onboarding_complete
            FROM profiles
            WHERE account_id = :account_id
            """
        ),
        {"account_id": account.account_id},
    ).mappings().first()
    if profile_state is None:
        raise ApiException("NO_PROFILE", "Finish onboarding to create your profile.", 404)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    eligibility_conditions: list[str] = []
    eligibility_parameters: dict[str, datetime] = {}
    if "username" in changes:
        if changes["username"] == profile_state["username"]:
            changes.pop("username")
        else:
            username_taken = db.execute(
                text(
                    """
                    SELECT 1 FROM profiles
                    WHERE username = :username AND account_id != :account_id
                    """
                ),
                {"username": changes["username"], "account_id": account.account_id},
            ).first()
            if username_taken is not None:
                raise ApiException("USERNAME_TAKEN", "That username is already in use.", 409)
            changed_at = profile_state["username_changed_at"]
            if changed_at is not None:
                available_at = _change_available_at(changed_at, USERNAME_CHANGE_COOLDOWN)
                if available_at is not None and now < available_at:
                    raise ApiException(
                        "USERNAME_CHANGE_COOLDOWN",
                        f"You can change your username again after {available_at.isoformat()}Z.",
                        429,
                    )
                eligibility_parameters["username_cutoff"] = now - USERNAME_CHANGE_COOLDOWN
                eligibility_conditions.append("username_changed_at <= :username_cutoff")
            else:
                eligibility_conditions.append("username_changed_at IS NULL")
            changes["username_changed_at"] = now
    if "display_name" in changes:
        if changes["display_name"] == profile_state["display_name"]:
            changes.pop("display_name")
        elif profile_state["onboarding_complete"] and profile_state["display_name"]:
            changed_at = profile_state["display_name_changed_at"]
            if changed_at is not None:
                available_at = _change_available_at(changed_at, DISPLAY_NAME_CHANGE_COOLDOWN)
                if available_at is not None and now < available_at:
                    raise ApiException(
                        "DISPLAY_NAME_CHANGE_COOLDOWN",
                        f"You can change your display name again after {available_at.isoformat()}Z.",
                        429,
                    )
                eligibility_parameters["display_name_cutoff"] = now - DISPLAY_NAME_CHANGE_COOLDOWN
                eligibility_conditions.append("display_name_changed_at <= :display_name_cutoff")
            else:
                eligibility_conditions.append("display_name_changed_at IS NULL")
            changes["display_name_changed_at"] = now
    audit_changed_fields = sorted(
        field for field in changes if field not in {"username_changed_at", "display_name_changed_at"}
    )
    if not changes:
        return get_own_profile(request, account, db)

    if "photos" in changes and changes["photos"] is not None:
        photo_urls = changes["photos"]
        media_ids: list[str] = []
        for photo_url in photo_urls:
            match = re.fullmatch(r"/media/([0-9a-f]{32})", photo_url)
            if match is None:
                raise ApiException(
                    "INVALID_PROFILE_MEDIA",
                    "Profile photos must be uploaded through the media endpoint.",
                )
            media_ids.append(match.group(1))
        if media_ids:
            owned_count = db.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT id)
                    FROM media_objects
                    WHERE account_id = :account_id
                      AND purpose = 'profile-photo'
                      AND id IN :media_ids
                    """
                ).bindparams(bindparam("media_ids", expanding=True)),
                {"account_id": account.account_id, "media_ids": tuple(media_ids)},
            ).scalar_one()
            if owned_count != len(set(media_ids)):
                raise ApiException(
                    "INVALID_PROFILE_MEDIA",
                    "One or more profile photos are unavailable.",
                    400,
                )
    if "videos" in changes and changes["videos"] is not None:
        video_ids: list[str] = []
        for video in changes["videos"]:
            match = re.fullmatch(r"/media/([0-9a-f]{32})", video["url"])
            if match is None:
                raise ApiException(
                    "INVALID_PROFILE_MEDIA",
                    "Profile videos must be uploaded through the media endpoint.",
                )
            video_ids.append(match.group(1))
            if video.get("locked") and video.get("price_naira") is None:
                raise ApiException(
                    "VIDEO_PRICE_REQUIRED",
                    "Set a price for locked videos.",
                )
        if video_ids:
            owned_count = db.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT id)
                    FROM media_objects
                    WHERE account_id = :account_id
                      AND purpose = 'profile-video'
                      AND id IN :media_ids
                    """
                ).bindparams(bindparam("media_ids", expanding=True)),
                {"account_id": account.account_id, "media_ids": tuple(video_ids)},
            ).scalar_one()
            if owned_count != len(set(video_ids)):
                raise ApiException(
                    "INVALID_PROFILE_MEDIA",
                    "One or more profile videos are unavailable.",
                    400,
                )

    column_names = {
        "username": "username",
        "username_changed_at": "username_changed_at",
        "display_name_changed_at": "display_name_changed_at",
        "display_name": "display_name",
        "bio": "bio",
        "photos": "photos",
        "videos": "videos",
        "area": "area",
        "latitude": "latitude",
        "longitude": "longitude",
        "interests": "interests",
        "discoverable_by": "discoverable_by",
        "wants_to_discover": "wants_to_discover",
        "identity": "identity",
        "show_identity": "show_identity",
        "two_factor_enabled": "two_factor_enabled",
        "two_factor_method": "two_factor_method",
    }
    assignments: list[str] = []
    parameters: dict[str, Any] = {
        "account_id": account.account_id,
        **eligibility_parameters,
    }
    for field, value in changes.items():
        column = column_names[field]
        assignments.append(f"{column} = :{field}")
        parameters[field] = json.dumps(value) if field in {"photos", "videos", "interests"} else value

    where_clause = "account_id = :account_id"
    if eligibility_conditions:
        where_clause += " AND " + " AND ".join(eligibility_conditions)
    try:
        result = db.execute(
            text(f"UPDATE profiles SET {', '.join(assignments)} WHERE {where_clause}"),
            parameters,
        )
    except IntegrityError as exc:
        db.rollback()
        if "username" in audit_changed_fields:
            raise ApiException("USERNAME_TAKEN", "That username is already in use.", 409) from exc
        raise
    if result.rowcount == 0 and eligibility_conditions:
        db.rollback()
        if "username" in audit_changed_fields:
            raise ApiException("USERNAME_CHANGE_COOLDOWN", "Your username cannot be changed yet.", 429)
        raise ApiException("DISPLAY_NAME_CHANGE_COOLDOWN", "Your display name cannot be changed yet.", 429)
    record_audit_event(
        db,
        request,
        event_type="profile.updated",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
        metadata={"changedFields": audit_changed_fields},
    )
    db.commit()
    return get_own_profile(request, account, db)


@discovery_router.get("/search", response_model=list[ProfileSearchResult])
def search_discoverable_profiles(
    request: Request,
    account: IdentityVerifiedAccount,
    db: Annotated[Session, Depends(db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    q: str = Query(min_length=2, max_length=64),
    min_age: int = Query(default=21, alias="minAge", ge=18, le=99),
    max_age: int = Query(default=45, alias="maxAge", ge=18, le=99),
    looking_for: AudiencePreference = Query(default="everyone", alias="lookingFor"),
) -> list[ProfileSearchResult]:
    _require_discovery_ready(account)
    if max_age < min_age:
        raise ApiException("INVALID_DISCOVERY_FILTERS", "Maximum age must be at least the minimum age.", 422)
    search_term = q.strip().removeprefix("@").strip()
    if len(search_term) < 2:
        return []
    viewer = _viewer_profile(db, account.account_id)
    rows = _visible_profile_rows(
        db,
        account.account_id,
        viewer["identity"],
        settings.demo_profiles_enabled,
        search_term=search_term,
        limit=PROFILE_SEARCH_LIMIT,
        min_age=max(min_age, 21),
        max_age=max_age,
        target_identity={"men": "man", "women": "woman"}.get(looking_for),
    )
    results = [
        ProfileSearchResult(
            id=str(row["id"]),
            username=row["username"],
            display_name=row["display_name"],
            photo=next(iter(_parse_json_list(row["photos"])), None),
        )
        for row in rows
    ]
    record_audit_event(
        db,
        request,
        event_type="discovery.profile_search",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=None,
        outcome="success",
        metadata={"resultCount": len(results)},
    )
    db.commit()
    return results


@discovery_router.get("", response_model=DiscoveryFeedResponse)
def get_discovery_feed(
    request: Request,
    account: IdentityVerifiedAccount,
    db: Annotated[Session, Depends(db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    min_age: int = Query(default=20, alias="minAge", ge=18, le=99),
    max_age: int = Query(default=45, alias="maxAge", ge=18, le=99),
    max_distance_km: float | None = Query(default=None, alias="maxDistanceKm", gt=0, le=200),
    interests: list[str] = Query(default=[]),
    live_only: bool = Query(default=False, alias="liveOnly"),
    looking_for: AudiencePreference = Query(default="everyone", alias="lookingFor"),
    cursor: int = Query(default=0, ge=0),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
) -> DiscoveryFeedResponse:
    _require_discovery_ready(account)
    if max_age < min_age:
        raise ApiException("INVALID_DISCOVERY_FILTERS", "Maximum age must be at least the minimum age.", 422)
    if (latitude is None) != (longitude is None):
        raise ApiException("INVALID_LOCATION", "Provide both latitude and longitude.", 422)

    viewer = _viewer_profile(db, account.account_id)
    origin_latitude = latitude
    origin_longitude = longitude
    if origin_latitude is None and viewer["latitude"] is not None and viewer["longitude"] is not None:
        origin_latitude = float(viewer["latitude"])
        origin_longitude = float(viewer["longitude"])
    if max_distance_km is not None and origin_latitude is None:
        raise ApiException("LOCATION_REQUIRED", "Choose a location to filter by distance.", 400)

    visible_rows = _visible_profile_rows(
        db,
        account.account_id,
        viewer["identity"],
        settings.demo_profiles_enabled,
    )
    live_host_ids = (
        {
            str(row[0])
            for row in db.execute(
                text("SELECT host_account_id FROM live_streams WHERE status = 'live'")
            ).all()
        }
        if live_only
        else None
    )
    target_identity = {"men": "man", "women": "woman"}.get(looking_for)
    requested_interests = set(interests)
    candidates: list[DiscoveryProfileResponse] = []
    all_matching_candidates: list[DiscoveryProfileResponse] = []
    for row in visible_rows:
        if live_host_ids is not None and str(row["id"]) not in live_host_ids:
            continue
        age = _current_age(row["date_of_birth"])
        if age < max(min_age, 21) or age > max_age:
            continue
        if target_identity is not None and row["identity"] != target_identity:
            continue
        profile_interests = _parse_json_list(row["interests"])
        if requested_interests and not requested_interests.intersection(profile_interests):
            continue

        distance = None
        candidate_latitude, candidate_longitude = _profile_coordinates(row)
        if (
            origin_latitude is not None
            and origin_longitude is not None
            and candidate_latitude is not None
            and candidate_longitude is not None
        ):
            distance = _distance_km(
                candidate_latitude,
                candidate_longitude,
                origin_latitude,
                origin_longitude,
            )
        viewer_is_vip = viewer["subscription_tier"] == "vip"
        target_is_vip = (
            _effective_subscription_tier(row["subscription_tier"], row["vip_expires_at"]) == "vip"
        )
        distance_waived = viewer_is_vip and target_is_vip
        candidate = _member_profile(row, distance)
        all_matching_candidates.append(candidate)
        if (
            max_distance_km is not None
            and not distance_waived
            and (distance is None or distance > max_distance_km)
        ):
            continue
        candidates.append(candidate)

    distance_expanded = max_distance_km is not None and not candidates and bool(all_matching_candidates)
    if distance_expanded:
        candidates = all_matching_candidates
    if origin_latitude is not None and origin_longitude is not None:
        candidates.sort(key=lambda profile: (profile.distance_km is None, profile.distance_km or 0, profile.id))

    page = candidates[cursor : cursor + DISCOVERY_PAGE_SIZE]
    next_cursor = (
        cursor + DISCOVERY_PAGE_SIZE
        if cursor + DISCOVERY_PAGE_SIZE < len(candidates)
        else None
    )
    record_audit_event(
        db,
        request,
        event_type="discovery.feed_viewed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=None,
        outcome="success",
        metadata={"resultCount": len(page), "cursor": cursor},
    )
    db.commit()
    return DiscoveryFeedResponse(
        items=page,
        next_cursor=next_cursor,
        distance_expanded=distance_expanded,
    )


@router.get("/{profile_id}", response_model=DiscoveryProfileResponse)
def get_discoverable_profile(
    profile_id: str,
    request: Request,
    account: IdentityVerifiedAccount,
    db: Annotated[Session, Depends(db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> DiscoveryProfileResponse:
    _require_discovery_ready(account)
    viewer = _viewer_profile(db, account.account_id)
    visible_rows = _visible_profile_rows(
        db,
        account.account_id,
        viewer["identity"],
        settings.demo_profiles_enabled,
        profile_id,
    )
    if not visible_rows:
        raise ApiException("PROFILE_NOT_FOUND", "This profile is unavailable.", 404)
    row = visible_rows[0]
    age = _current_age(row["date_of_birth"])
    if age < 21:
        raise ApiException("PROFILE_NOT_FOUND", "This profile is unavailable.", 404)
    distance = None
    profile_latitude, profile_longitude = _profile_coordinates(row)
    if (
        viewer["latitude"] is not None
        and viewer["longitude"] is not None
        and profile_latitude is not None
        and profile_longitude is not None
    ):
        distance = _distance_km(
            profile_latitude,
            profile_longitude,
            float(viewer["latitude"]),
            float(viewer["longitude"]),
        )
    record_audit_event(
        db,
        request,
        event_type="profile.discoverable_viewed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=str(row["id"]),
        outcome="success",
    )
    db.commit()
    return _member_profile(row, distance, include_video_previews=True)
