import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dependencies import db_session
from app.errors import ApiException
from app.routes.auth import CurrentAccount, require_csrf
from app.schemas import OwnProfilePatch, OwnProfileResponse

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("/me", response_model=OwnProfileResponse)
def get_own_profile(account: CurrentAccount, db: Annotated[Session, Depends(db_session)]) -> OwnProfileResponse:
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
    payload: OwnProfilePatch,
    account: CurrentAccount,
    db: Annotated[Session, Depends(db_session)],
) -> OwnProfileResponse:
    changes = payload.model_dump(exclude_unset=True, by_alias=False)
    changes.pop("distance_km", None)
    if not changes:
        return get_own_profile(account, db)

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
    db.commit()
    return get_own_profile(account, db)
