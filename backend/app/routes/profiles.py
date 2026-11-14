import json
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.dependencies import db_session
from app.errors import ApiException
from app.routes.auth import CurrentAccount, require_csrf
from app.schemas import OwnProfilePatch, OwnProfileResponse

router = APIRouter(prefix="/profiles", tags=["profiles"])


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
                   p.display_name, p.bio, p.photos, p.videos, p.age_range, p.area,
                   p.distance_km, p.interests, p.discoverable_by, p.wants_to_discover,
                   p.identity, p.show_identity, p.subscription_tier, p.moderation_status,
                   p.two_factor_enabled, p.two_factor_method, p.onboarding_complete,
                   p.document_verification,
                   p.document_type, p.vip_expires_at
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
    profile["distance_km"] = float(profile["distance_km"])
    if isinstance(profile["photos"], str):
        profile["photos"] = json.loads(profile["photos"])
    if isinstance(profile["interests"], str):
        profile["interests"] = json.loads(profile["interests"])
    if isinstance(profile["videos"], str):
        profile["videos"] = json.loads(profile["videos"])
    return OwnProfileResponse.model_validate(profile)


@router.patch("/me", response_model=OwnProfileResponse, dependencies=[Depends(require_csrf)])
def save_own_profile(
    request: Request,
    payload: OwnProfilePatch,
    account: CurrentAccount,
    db: Annotated[Session, Depends(db_session)],
) -> OwnProfileResponse:
    changes = payload.model_dump(exclude_unset=True, by_alias=False)
    changes.pop("distance_km", None)
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

    column_names = {
        "display_name": "display_name",
        "bio": "bio",
        "photos": "photos",
        "videos": "videos",
        "area": "area",
        "interests": "interests",
        "discoverable_by": "discoverable_by",
        "wants_to_discover": "wants_to_discover",
        "identity": "identity",
        "show_identity": "show_identity",
        "two_factor_enabled": "two_factor_enabled",
        "two_factor_method": "two_factor_method",
    }
    assignments: list[str] = []
    parameters: dict[str, Any] = {"account_id": account.account_id}
    for field, value in changes.items():
        column = column_names[field]
        assignments.append(f"{column} = :{field}")
        parameters[field] = json.dumps(value) if field in {"photos", "videos", "interests"} else value

    db.execute(
        text(f"UPDATE profiles SET {', '.join(assignments)} WHERE account_id = :account_id"),
        parameters,
    )
    record_audit_event(
        db,
        request,
        event_type="profile.updated",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
        metadata={"changedFields": sorted(changes)},
    )
    db.commit()
    return get_own_profile(request, account, db)
