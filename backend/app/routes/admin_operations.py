import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.dependencies import db_session
from app.errors import ApiException, ServiceUnavailable
from app.routes.admin import AdminAccount, require_admin_csrf, require_admin_roles
from app.routes.livestreams import _broadcast_stream_event
from app.livekit import create_room_token, delete_room
from app.storage import ObjectStorage, get_object_storage
from app.wallet import credit_wallet, debit_wallet

router = APIRouter(prefix="/admin", tags=["admin operations"])
DbSession = Annotated[Session, Depends(db_session)]
Manager = Annotated[AdminAccount, Depends(require_admin_roles("super_admin", "admin"))]
SafetyManager = Annotated[
    AdminAccount,
    Depends(require_admin_roles("super_admin", "admin", "safety_admin")),
]
SuperManager = Annotated[AdminAccount, Depends(require_admin_roles("super_admin"))]
StorageDependency = Annotated[ObjectStorage, Depends(get_object_storage)]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AccountStatusRequest(BaseModel):
    status: Literal["active", "suspended", "banned"]
    reason: str = Field(min_length=1, max_length=1000)


class SafetyReportDecisionRequest(BaseModel):
    decision: Literal["reviewed", "dismissed"]
    reason: str = Field(min_length=1, max_length=1000)


class WalletAdjustmentRequest(BaseModel):
    amount_kobo: int = Field(ge=-100_000_000_000, le=100_000_000_000)
    reason: str = Field(min_length=1, max_length=500)


class CallCreditAdjustmentRequest(BaseModel):
    amount: int = Field(ge=-1_000_000, le=1_000_000)
    reason: str = Field(min_length=1, max_length=500)


class GiftCatalogCreateRequest(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]{1,40}$")
    name: str = Field(min_length=1, max_length=80)
    emoji: str = Field(min_length=1, max_length=16)
    price_kobo: int = Field(gt=0, le=100_000_000)


class GiftCatalogUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    emoji: str | None = Field(default=None, min_length=1, max_length=16)
    price_kobo: int | None = Field(default=None, gt=0, le=100_000_000)
    active: bool | None = None


class SubscriptionPlanUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    duration_days: int | None = Field(default=None, gt=0, le=3650)
    price_kobo: int | None = Field(default=None, ge=0, le=100_000_000_000)
    active: bool | None = None


class UserSubscriptionRequest(BaseModel):
    tier: Literal["free", "vip"]
    expires_at: datetime | None = None
    reason: str = Field(min_length=1, max_length=1000)


class LiveStreamWarningRequest(BaseModel):
    severity: Literal["warning", "violation"] = "warning"
    reason: str = Field(min_length=1, max_length=500)


class AdminMediaRemovalRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


@router.get("/users")
def list_users(
    request: Request,
    db: DbSession,
    admin: Manager,
    search: str | None = Query(default=None, min_length=1, max_length=254),
    status: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    clauses = ["(:search IS NULL OR a.id LIKE :like OR a.email LIKE :like OR p.display_name LIKE :like)"]
    params: dict[str, object] = {
        "search": search,
        "like": f"%{search}%" if search is not None else None,
        "status": status,
        "limit": limit + 1,
        "offset": offset,
    }
    if status is not None:
        clauses.append("a.account_state = :status")
    where = " AND ".join(clauses)
    rows = db.execute(
        text(
            f"""
            SELECT a.id, a.email, a.account_state, a.email_verified, a.created_at,
                   p.display_name, p.moderation_status, p.document_verification
            FROM accounts a
            LEFT JOIN profiles p ON p.account_id = a.id
            WHERE {where}
            ORDER BY a.created_at DESC, a.id
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()
    has_more = len(rows) > limit
    items = [
        {
            "accountId": str(row["id"]),
            "email": row["email"],
            "displayName": row["display_name"],
            "accountStatus": row["account_state"],
            "emailVerified": bool(row["email_verified"]),
            "moderationStatus": row["moderation_status"],
            "documentVerification": row["document_verification"],
            "createdAt": row["created_at"],
        }
        for row in rows[:limit]
    ]
    record_audit_event(
        db,
        request,
        event_type="admin.users.list_viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
        metadata={"count": len(items), "offset": offset, "filtered": search is not None or status is not None},
    )
    db.commit()
    return {"items": items, "nextOffset": offset + limit if has_more else None}


@router.get("/users/{account_id}")
def get_user(
    account_id: str,
    request: Request,
    db: DbSession,
    admin: Manager,
) -> dict[str, object]:
    row = db.execute(
        text(
            """
            SELECT a.id, a.email, a.identifier, a.identifier_type, a.account_state,
                   a.email_verified, a.date_of_birth, a.gender,
                   a.emergency_contact_name, a.emergency_contact_phone_e164,
                   a.terms_version, a.privacy_version, a.created_at, a.updated_at,
                   p.username, p.display_name, p.bio, p.age_range,
                   p.area, p.interests, p.identity, p.show_identity, p.discoverable_by,
                   p.wants_to_discover, p.onboarding_complete, p.moderation_status,
                   p.document_verification, p.document_type,
                   p.subscription_tier, p.vip_expires_at
            FROM accounts a
            LEFT JOIN profiles p ON p.account_id = a.id
            WHERE a.id = :account_id
            """
        ),
        {"account_id": account_id},
    ).mappings().first()
    if row is None:
        raise ApiException("USER_NOT_FOUND", "This member is unavailable.", 404)
    record_audit_event(
        db,
        request,
        event_type="admin.user.details_viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=account_id,
        outcome="success",
    )
    db.commit()
    return {
        "accountId": str(row["id"]),
        "email": row["email"],
        "contact": row["identifier"],
        "identifierType": row["identifier_type"],
        "accountStatus": row["account_state"],
        "emailVerified": bool(row["email_verified"]),
        "dateOfBirth": row["date_of_birth"],
        "gender": row["gender"],
        "emergencyContactName": row["emergency_contact_name"],
        "emergencyContactPhone": row["emergency_contact_phone_e164"],
        "termsVersion": row["terms_version"],
        "privacyVersion": row["privacy_version"],
        "username": row["username"],
        "displayName": row["display_name"],
        "bio": row["bio"],
        "ageRange": row["age_range"],
        "area": row["area"],
        "interests": json.loads(row["interests"]) if isinstance(row["interests"], str) else row["interests"],
        "identity": row["identity"],
        "showIdentity": bool(row["show_identity"]) if row["show_identity"] is not None else None,
        "discoverableBy": row["discoverable_by"],
        "wantsToDiscover": row["wants_to_discover"],
        "onboardingComplete": bool(row["onboarding_complete"]) if row["onboarding_complete"] is not None else None,
        "moderationStatus": row["moderation_status"],
        "documentVerification": row["document_verification"],
        "documentType": row["document_type"],
        "subscriptionTier": row["subscription_tier"],
        "vipExpiresAt": row["vip_expires_at"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


@router.get("/users/{account_id}/wallet")
def get_admin_user_wallet(
    account_id: str,
    request: Request,
    db: DbSession,
    admin: Manager,
) -> dict[str, object]:
    if db.execute(text("SELECT 1 FROM accounts WHERE id = :id"), {"id": account_id}).first() is None:
        raise ApiException("USER_NOT_FOUND", "This member is unavailable.", 404)

    wallet = db.execute(
        text("SELECT balance_kobo FROM wallet_accounts WHERE account_id = :id"),
        {"id": account_id},
    ).scalar_one_or_none()
    call_credits = db.execute(
        text("SELECT balance FROM call_credit_accounts WHERE account_id = :id"),
        {"id": account_id},
    ).scalar_one_or_none()
    wallet_spent = db.execute(
        text(
            """
            SELECT COALESCE(SUM(-amount_kobo), 0)
            FROM wallet_transactions
            WHERE account_id = :id AND amount_kobo < 0 AND status = 'completed'
            """
        ),
        {"id": account_id},
    ).scalar_one()
    credits_spent = db.execute(
        text(
            """
            SELECT COALESCE(SUM(-amount), 0)
            FROM call_credit_transactions
            WHERE account_id = :id AND amount < 0
            """
        ),
        {"id": account_id},
    ).scalar_one()
    transactions = db.execute(
        text(
            """
            SELECT 'wallet' AS ledger, transaction_type, amount_kobo AS amount,
                   description, status, created_at
            FROM wallet_transactions
            WHERE account_id = :id
            UNION ALL
            SELECT 'call credits' AS ledger, transaction_type, amount,
                   description, 'completed' AS status, created_at
            FROM call_credit_transactions
            WHERE account_id = :id
            ORDER BY created_at DESC
            LIMIT 100
            """
        ),
        {"id": account_id},
    ).mappings().all()
    record_audit_event(
        db,
        request,
        event_type="admin.user.wallet_viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=account_id,
        outcome="success",
        metadata={"transactionCount": len(transactions)},
    )
    db.commit()
    return {
        "walletBalanceKobo": int(wallet or 0),
        "callCreditBalance": int(call_credits or 0),
        "walletSpentKobo": int(wallet_spent or 0),
        "callCreditsSpent": int(credits_spent or 0),
        "transactions": [
            {
                "ledger": row["ledger"],
                "transactionType": row["transaction_type"],
                "amount": int(row["amount"]),
                "description": row["description"],
                "status": row["status"],
                "createdAt": row["created_at"],
            }
            for row in transactions
        ],
    }


@router.get("/users/{account_id}/media")
def list_admin_user_media(
    account_id: str,
    request: Request,
    db: DbSession,
    admin: SuperManager,
) -> dict[str, list[dict[str, object]]]:
    if db.execute(text("SELECT 1 FROM accounts WHERE id = :id"), {"id": account_id}).first() is None:
        raise ApiException("USER_NOT_FOUND", "This member is unavailable.", 404)
    rows = db.execute(
        text(
            """
            SELECT id, purpose, content_type, size_bytes, created_at
            FROM media_objects
            WHERE account_id = :account_id
            ORDER BY created_at DESC, id DESC
            """
        ),
        {"account_id": account_id},
    ).mappings().all()
    record_audit_event(
        db,
        request,
        event_type="admin.user.media_listed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=account_id,
        outcome="success",
        metadata={"mediaCount": len(rows)},
    )
    db.commit()
    return {
        "items": [
            {
                "mediaId": str(row["id"]),
                "purpose": row["purpose"],
                "contentType": row["content_type"],
                "sizeBytes": int(row["size_bytes"]),
                "createdAt": row["created_at"],
            }
            for row in rows
        ]
    }


@router.get("/users/{account_id}/media/{media_id}")
def get_admin_user_media(
    account_id: str,
    media_id: str,
    request: Request,
    db: DbSession,
    admin: SuperManager,
    storage: StorageDependency,
) -> RedirectResponse:
    row = db.execute(
        text(
            """
            SELECT object_key, purpose, content_type
            FROM media_objects
            WHERE id = :media_id AND account_id = :account_id
            """
        ),
        {"media_id": media_id, "account_id": account_id},
    ).mappings().first()
    if row is None:
        raise ApiException("MEDIA_NOT_FOUND", "This upload is unavailable.", 404)
    try:
        signed_url = storage.get_url(str(row["object_key"]), str(row["content_type"]))
    except ServiceUnavailable:
        record_audit_event(
            db,
            request,
            event_type="admin.user.media_viewed",
            actor_type="admin",
            actor_id=admin.admin_id,
            subject_account_id=account_id,
            outcome="failure",
            metadata={"purpose": row["purpose"], "reason": "storage_unavailable"},
        )
        db.commit()
        raise
    record_audit_event(
        db,
        request,
        event_type="admin.user.media_viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=account_id,
        outcome="success",
        metadata={"purpose": row["purpose"], "contentType": row["content_type"]},
    )
    db.commit()
    return RedirectResponse(
        signed_url,
        status_code=307,
        headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"},
    )


@router.delete(
    "/users/{account_id}/media/{media_id}",
    dependencies=[Depends(require_admin_csrf)],
)
def remove_admin_user_media(
    account_id: str,
    media_id: str,
    body: AdminMediaRemovalRequest,
    request: Request,
    db: DbSession,
    admin: SuperManager,
    storage: StorageDependency,
) -> dict[str, str]:
    reason = body.reason.strip()
    if not reason:
        raise ApiException("MEDIA_REMOVAL_REASON_REQUIRED", "Enter a reason for removing this upload.", 400)
    media = db.execute(
        text(
            """
            SELECT object_key, purpose, content_type
            FROM media_objects
            WHERE id = :media_id AND account_id = :account_id
            """
        ),
        {"media_id": media_id, "account_id": account_id},
    ).mappings().first()
    if media is None:
        raise ApiException("MEDIA_NOT_FOUND", "This upload is unavailable.", 404)
    if media["purpose"] == "identity-document" or not str(media["content_type"]).startswith(("image/", "video/")):
        raise ApiException("MEDIA_REMOVAL_FORBIDDEN", "This type of upload cannot be removed from this screen.", 403)

    media_url = f"/media/{media_id}"
    profile = db.execute(
        text("SELECT photos, videos FROM profiles WHERE account_id = :id"),
        {"id": account_id},
    ).mappings().first()
    if profile is not None:
        photos = json.loads(profile["photos"]) if isinstance(profile["photos"], str) else profile["photos"]
        videos = json.loads(profile["videos"]) if isinstance(profile["videos"], str) else profile["videos"]
        updated_photos = [photo for photo in photos or [] if photo != media_url]
        updated_videos = [
            video for video in videos or []
            if not isinstance(video, dict) or video.get("url") != media_url
        ]
        if updated_photos != (photos or []) or updated_videos != (videos or []):
            db.execute(
                text("UPDATE profiles SET photos = :photos, videos = :videos WHERE account_id = :id"),
                {
                    "photos": json.dumps(updated_photos, separators=(",", ":")),
                    "videos": json.dumps(updated_videos, separators=(",", ":")),
                    "id": account_id,
                },
            )

    posts = db.execute(
        text("SELECT id, photos, video_url FROM member_posts WHERE author_id = :id"),
        {"id": account_id},
    ).mappings().all()
    for post in posts:
        photos = json.loads(post["photos"]) if isinstance(post["photos"], str) else post["photos"]
        updated_photos = [photo for photo in photos or [] if photo != media_url]
        if updated_photos != (photos or []):
            db.execute(
                text("UPDATE member_posts SET photos = :photos WHERE id = :id"),
                {"photos": json.dumps(updated_photos, separators=(",", ":")), "id": post["id"]},
            )
        if post["video_url"] == media_url:
            db.execute(
                text("UPDATE member_posts SET video_url = NULL WHERE id = :id"),
                {"id": post["id"]},
            )
    db.execute(
        text("DELETE FROM member_statuses WHERE author_id = :id AND media_url = :url"),
        {"id": account_id, "url": media_url},
    )
    db.execute(
        text(
            """
            UPDATE chat_messages SET attachment_media_id = NULL, attachment_json = NULL
            WHERE attachment_media_id = :media_id
            """
        ),
        {"media_id": media_id},
    )
    try:
        storage.delete(str(media["object_key"]), str(media["content_type"]))
    except ServiceUnavailable:
        db.rollback()
        record_audit_event(
            db,
            request,
            event_type="admin.user.media_removed",
            actor_type="admin",
            actor_id=admin.admin_id,
            subject_account_id=account_id,
            outcome="failure",
            metadata={"purpose": media["purpose"], "reason": reason, "failure": "storage_unavailable"},
        )
        db.commit()
        raise
    db.execute(
        text("DELETE FROM media_objects WHERE id = :id AND account_id = :account_id"),
        {"id": media_id, "account_id": account_id},
    )
    record_audit_event(
        db,
        request,
        event_type="admin.user.media_removed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=account_id,
        outcome="success",
        metadata={"purpose": media["purpose"], "reason": reason},
    )
    db.commit()
    return {"mediaId": media_id, "status": "removed"}


@router.post(
    "/users/{account_id}/status",
    dependencies=[Depends(require_admin_csrf)],
)
def set_user_status(
    account_id: str,
    body: AccountStatusRequest,
    request: Request,
    db: DbSession,
    admin: SafetyManager,
) -> dict[str, str]:
    reason = body.reason.strip()
    if not reason:
        raise ApiException("INVALID_STATUS_REASON", "Add a reason for changing this member's status.", 400)
    row = db.execute(
        text("SELECT account_state FROM accounts WHERE id = :account_id"),
        {"account_id": account_id},
    ).mappings().first()
    if row is None:
        raise ApiException("USER_NOT_FOUND", "This member is unavailable.", 404)
    current_status = str(row["account_state"])
    if body.status == current_status:
        raise ApiException("USER_STATUS_UNCHANGED", "The member already has this status.", 409)
    if body.status == "active" and current_status not in {"suspended", "banned"}:
        raise ApiException("USER_STATUS_TRANSITION_INVALID", "Only a suspended or banned member can be reactivated.", 409)
    if body.status != "active" and current_status != "active":
        raise ApiException("USER_STATUS_TRANSITION_INVALID", "Only an active member can be suspended or banned.", 409)

    db.execute(
        text("UPDATE accounts SET account_state = :status WHERE id = :account_id"),
        {"status": body.status, "account_id": account_id},
    )
    if body.status != "active":
        db.execute(
            text(
                """
                UPDATE sessions SET revoked_at = :now
                WHERE account_id = :account_id AND revoked_at IS NULL
                """
            ),
            {"now": _now(), "account_id": account_id},
        )
    record_audit_event(
        db,
        request,
        event_type=f"admin.user.status_{body.status}",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=account_id,
        outcome="success",
        metadata={"previousStatus": current_status, "reason": reason},
    )
    db.commit()
    return {"accountId": account_id, "status": body.status}


@router.post(
    "/users/{account_id}/sessions/revoke",
    dependencies=[Depends(require_admin_csrf)],
)
def revoke_user_sessions(
    account_id: str,
    request: Request,
    db: DbSession,
    admin: Manager,
) -> dict[str, int]:
    if db.execute(text("SELECT 1 FROM accounts WHERE id = :id"), {"id": account_id}).first() is None:
        raise ApiException("USER_NOT_FOUND", "This member is unavailable.", 404)
    result = db.execute(
        text(
            """
            UPDATE sessions SET revoked_at = :now
            WHERE account_id = :account_id AND revoked_at IS NULL
            """
        ),
        {"now": _now(), "account_id": account_id},
    )
    record_audit_event(
        db,
        request,
        event_type="admin.user.sessions_revoked",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=account_id,
        outcome="success",
        metadata={"sessionCount": int(result.rowcount or 0)},
    )
    db.commit()
    return {"revokedCount": int(result.rowcount or 0)}


@router.get("/safety/reports")
def list_safety_reports(
    request: Request,
    db: DbSession,
    admin: SafetyManager,
    status: Literal["open", "reviewed", "dismissed", "all"] = "open",
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    status_filter = "" if status == "all" else "AND r.status = :status"
    params: dict[str, object] = {"limit": limit + 1, "offset": offset}
    if status != "all":
        params["status"] = status
    rows = db.execute(
        text(
            f"""
            SELECT r.id, r.reporter_id, r.target_account_id, r.reason, r.description,
                   r.status, r.created_at, reporter.display_name AS reporter_name,
                   target.display_name AS target_name
            FROM safety_reports r
            LEFT JOIN profiles reporter ON reporter.account_id = r.reporter_id
            LEFT JOIN profiles target ON target.account_id = r.target_account_id
            WHERE 1 = 1 {status_filter}
            ORDER BY r.created_at ASC, r.id
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()
    has_more = len(rows) > limit
    items = [
        {
            "reportId": str(row["id"]),
            "reporterId": str(row["reporter_id"]),
            "reporterName": row["reporter_name"],
            "targetId": str(row["target_account_id"]),
            "targetName": row["target_name"],
            "reason": row["reason"],
            "description": row["description"],
            "status": row["status"],
            "createdAt": row["created_at"],
        }
        for row in rows[:limit]
    ]
    record_audit_event(
        db,
        request,
        event_type="admin.safety.reports_viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
        metadata={"status": status, "count": len(items), "offset": offset},
    )
    db.commit()
    return {"items": items, "nextOffset": offset + limit if has_more else None}


@router.post(
    "/safety/reports/{report_id}/decision",
    dependencies=[Depends(require_admin_csrf)],
)
def decide_safety_report(
    report_id: str,
    body: SafetyReportDecisionRequest,
    request: Request,
    db: DbSession,
    admin: SafetyManager,
) -> dict[str, str]:
    reason = body.reason.strip()
    if not reason:
        raise ApiException("INVALID_DECISION_REASON", "Add a reason for this report decision.", 400)
    result = db.execute(
        text(
            """
            UPDATE safety_reports
            SET status = :decision, resolved_at = :resolved_at
            WHERE id = :report_id AND status = 'open'
            """
        ),
        {"decision": body.decision, "resolved_at": _now(), "report_id": report_id},
    )
    if result.rowcount != 1:
        exists = db.execute(
            text("SELECT status FROM safety_reports WHERE id = :id"),
            {"id": report_id},
        ).scalar_one_or_none()
        if exists is None:
            raise ApiException("SAFETY_REPORT_NOT_FOUND", "This safety report is unavailable.", 404)
        raise ApiException("SAFETY_REPORT_ALREADY_RESOLVED", "This safety report has already been resolved.", 409)
    target_id = db.execute(
        text("SELECT target_account_id FROM safety_reports WHERE id = :id"),
        {"id": report_id},
    ).scalar_one()
    record_audit_event(
        db,
        request,
        event_type="admin.safety.report_decided",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=str(target_id),
        outcome="success",
        metadata={"reportId": report_id, "decision": body.decision, "reason": reason},
    )
    db.commit()
    return {"reportId": report_id, "status": body.decision}


@router.get("/privacy/requests")
def list_privacy_requests(
    request: Request,
    db: DbSession,
    admin: Manager,
    status: Literal["queued", "processing", "completed", "failed", "cancelled", "all"] = "queued",
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    status_filter = "" if status == "all" else "AND pr.status = :status"
    params: dict[str, object] = {"limit": limit + 1, "offset": offset}
    if status != "all":
        params["status"] = status
    rows = db.execute(
        text(
            f"""
            SELECT pr.id, pr.account_id, a.email, pr.request_type, pr.status,
                   pr.created_at, pr.updated_at
            FROM privacy_requests pr
            JOIN accounts a ON a.id = pr.account_id
            WHERE 1 = 1 {status_filter}
            ORDER BY pr.created_at, pr.id
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()
    has_more = len(rows) > limit
    items = [
        {
            "requestId": str(row["id"]),
            "accountId": str(row["account_id"]),
            "email": row["email"],
            "requestType": row["request_type"],
            "status": row["status"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in rows[:limit]
    ]
    record_audit_event(
        db,
        request,
        event_type="admin.privacy.requests_viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
        metadata={"status": status, "count": len(items), "offset": offset},
    )
    db.commit()
    return {"items": items, "nextOffset": offset + limit if has_more else None}


@router.post(
    "/privacy/requests/{request_id}/retry",
    dependencies=[Depends(require_admin_csrf)],
)
def retry_privacy_request(
    request_id: str,
    request: Request,
    db: DbSession,
    admin: Manager,
) -> dict[str, str]:
    row = db.execute(
        text("SELECT account_id, request_type FROM privacy_requests WHERE id = :id AND status = 'failed'"),
        {"id": request_id},
    ).mappings().first()
    if row is None:
        raise ApiException("PRIVACY_REQUEST_NOT_RETRYABLE", "This failed privacy request is unavailable.", 409)
    db.execute(
        text("UPDATE privacy_requests SET status = 'queued', updated_at = :now WHERE id = :id"),
        {"now": _now(), "id": request_id},
    )
    record_audit_event(
        db,
        request,
        event_type="admin.privacy.request_retried",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=str(row["account_id"]),
        outcome="success",
        metadata={"requestId": request_id, "requestType": row["request_type"]},
    )
    db.commit()
    return {"requestId": request_id, "status": "queued"}


@router.get("/payouts")
def list_admin_payouts(
    request: Request,
    db: DbSession,
    admin: Manager,
    status: str | None = Query(default=None, max_length=24),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    rows = db.execute(
        text(
            """
            SELECT p.id, p.account_id, a.email, p.reference, p.amount_kobo, p.status,
                   p.transfer_code, p.created_at, p.updated_at
            FROM payout_requests p
            JOIN accounts a ON a.id = p.account_id
            WHERE (:status IS NULL OR p.status = :status)
            ORDER BY p.created_at DESC, p.id
            LIMIT :limit OFFSET :offset
            """
        ),
        {"status": status, "limit": limit + 1, "offset": offset},
    ).mappings().all()
    has_more = len(rows) > limit
    items = [
        {
            "payoutId": str(row["id"]),
            "accountId": str(row["account_id"]),
            "email": row["email"],
            "reference": row["reference"],
            "amountKobo": int(row["amount_kobo"]),
            "status": row["status"],
            "transferCode": row["transfer_code"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in rows[:limit]
    ]
    record_audit_event(
        db,
        request,
        event_type="admin.payouts.list_viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
        metadata={"status": status, "count": len(items), "offset": offset},
    )
    db.commit()
    return {"items": items, "nextOffset": offset + limit if has_more else None}


@router.post(
    "/users/{account_id}/wallet-adjustments",
    dependencies=[Depends(require_admin_csrf)],
)
def adjust_user_wallet(
    account_id: str,
    body: WalletAdjustmentRequest,
    request: Request,
    db: DbSession,
    admin: Manager,
) -> dict[str, int | str]:
    reason = body.reason.strip()
    if not reason or body.amount_kobo == 0:
        raise ApiException("INVALID_WALLET_ADJUSTMENT", "Provide a non-zero amount and a reason.", 400)
    if db.execute(text("SELECT 1 FROM accounts WHERE id = :id"), {"id": account_id}).first() is None:
        raise ApiException("USER_NOT_FOUND", "This member is unavailable.", 404)
    if body.amount_kobo > 0:
        balance = credit_wallet(
            db,
            account_id,
            body.amount_kobo,
            transaction_type="admin-adjustment",
            description=f"Admin adjustment: {reason}",
        )
    else:
        balance = debit_wallet(
            db,
            account_id,
            abs(body.amount_kobo),
            transaction_type="admin-adjustment",
            description=f"Admin adjustment: {reason}",
        )
    record_audit_event(
        db,
        request,
        event_type="admin.wallet.adjusted",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=account_id,
        outcome="success",
        metadata={"amountKobo": body.amount_kobo, "reason": reason},
    )
    db.commit()
    return {"accountId": account_id, "balanceKobo": balance}


@router.post(
    "/users/{account_id}/call-credit-adjustments",
    dependencies=[Depends(require_admin_csrf)],
)
def adjust_user_call_credits(
    account_id: str,
    body: CallCreditAdjustmentRequest,
    request: Request,
    db: DbSession,
    admin: Manager,
) -> dict[str, int | str]:
    reason = body.reason.strip()
    if not reason or body.amount == 0:
        raise ApiException("INVALID_CALL_CREDIT_ADJUSTMENT", "Provide a non-zero whole-coin amount and a reason.", 400)
    if db.execute(text("SELECT 1 FROM accounts WHERE id = :id"), {"id": account_id}).first() is None:
        raise ApiException("USER_NOT_FOUND", "This member is unavailable.", 404)
    account = db.execute(
        text("SELECT balance FROM call_credit_accounts WHERE account_id = :id"),
        {"id": account_id},
    ).first()
    if account is None:
        if db.get_bind().dialect.name == "sqlite":
            db.execute(
                text("INSERT INTO call_credit_accounts (account_id, balance) VALUES (:id, 0)"),
                {"id": account_id},
            )
        else:
            db.execute(
                text(
                    """
                    INSERT INTO call_credit_accounts (account_id, balance) VALUES (:id, 0)
                    ON DUPLICATE KEY UPDATE account_id = VALUES(account_id)
                    """
                ),
                {"id": account_id},
            )
    if body.amount > 0:
        db.execute(
            text("UPDATE call_credit_accounts SET balance = balance + :amount WHERE account_id = :id"),
            {"amount": body.amount, "id": account_id},
        )
    else:
        result = db.execute(
            text(
                """
                UPDATE call_credit_accounts SET balance = balance - :amount
                WHERE account_id = :id AND balance >= :amount
                """
            ),
            {"amount": abs(body.amount), "id": account_id},
        )
        if result.rowcount != 1:
            raise ApiException("INSUFFICIENT_CALL_CREDITS", "The member does not have enough call credits.", 409)
    balance = int(
        db.execute(
            text("SELECT balance FROM call_credit_accounts WHERE account_id = :id"),
            {"id": account_id},
        ).scalar_one()
    )
    db.execute(
        text(
            """
            INSERT INTO call_credit_transactions (
                id, account_id, call_id, tick_number, transaction_type, amount,
                description, idempotency_key, created_at
            )
            VALUES (:id, :account_id, NULL, NULL, 'admin-adjustment', :amount, :description, NULL, :now)
            """
        ),
        {
            "id": uuid.uuid4().hex,
            "account_id": account_id,
            "amount": body.amount,
            "description": f"Admin adjustment: {reason}"[:255],
            "now": _now(),
        },
    )
    record_audit_event(
        db,
        request,
        event_type="admin.call_credits.adjusted",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=account_id,
        outcome="success",
        metadata={"amount": body.amount, "reason": reason},
    )
    db.commit()
    return {"accountId": account_id, "balance": balance}


@router.get("/dashboard")
def get_admin_dashboard(
    request: Request,
    db: DbSession,
    admin: Annotated[
        AdminAccount,
        Depends(require_admin_roles("super_admin", "admin", "reviewer", "safety_admin", "auditor")),
    ],
) -> dict[str, object]:
    now = _now()
    signup_since = datetime.combine(now.date() - timedelta(days=29), datetime.min.time())
    active_since = now - timedelta(days=30)
    member_totals = db.execute(
        text(
            """
            SELECT COUNT(*) AS registered_members,
                   SUM(CASE WHEN account_state = 'active' THEN 1 ELSE 0 END) AS active_members,
                   SUM(CASE WHEN created_at >= :signup_since THEN 1 ELSE 0 END) AS new_members
            FROM accounts
            WHERE account_state NOT IN ('deletion_requested', 'deleted')
            """
        ),
        {"signup_since": signup_since},
    ).mappings().one()
    active_members = db.execute(
        text(
            """
            SELECT COUNT(DISTINCT s.account_id)
            FROM sessions s
            JOIN accounts a ON a.id = s.account_id
            WHERE a.account_state = 'active'
              AND COALESCE(s.last_active_at, s.created_at) >= :active_since
            """
        ),
        {"active_since": active_since},
    ).scalar_one()
    vip_members = db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM profiles p
            JOIN accounts a ON a.id = p.account_id
            WHERE a.account_state = 'active'
              AND p.subscription_tier = 'vip'
              AND p.vip_expires_at > :now
            """
        ),
        {"now": now},
    ).scalar_one()
    signup_rows = db.execute(
        text(
            """
            SELECT DATE(created_at) AS signup_date, COUNT(*) AS signup_count
            FROM accounts
            WHERE account_state NOT IN ('deletion_requested', 'deleted')
              AND created_at >= :signup_since
            GROUP BY DATE(created_at)
            """
        ),
        {"signup_since": signup_since},
    ).mappings().all()
    signup_counts = {
        (now.date() - timedelta(days=days_ago)).isoformat(): 0
        for days_ago in range(29, -1, -1)
    }
    for row in signup_rows:
        signup_counts[str(row["signup_date"])[:10]] = int(row["signup_count"])
    post_count = db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM member_posts p
            JOIN accounts a ON a.id = p.author_id
            WHERE p.created_at >= :since
              AND a.account_state NOT IN ('deletion_requested', 'deleted')
            """
        ),
        {"since": signup_since},
    ).scalar_one()
    active_status_count = db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM member_statuses s
            JOIN accounts a ON a.id = s.author_id
            WHERE s.expires_at > :now
              AND a.account_state NOT IN ('deletion_requested', 'deleted')
            """
        ),
        {"now": now},
    ).scalar_one()
    if admin.role == "super_admin":
        wallet_funding = db.execute(
            text(
                """
                SELECT COALESCE(SUM(amount_kobo), 0)
                FROM wallet_payment_intents
                WHERE status = 'settled' AND settled_at >= :since
                """
            ),
            {"since": signup_since},
        ).scalar_one()
    else:
        wallet_funding = None

    counts = {
        "registeredMembers": int(member_totals["registered_members"] or 0),
        "activeAccounts": int(member_totals["active_members"] or 0),
        "newMembersLast30Days": int(member_totals["new_members"] or 0),
        "activeMembersLast30Days": int(active_members or 0),
        "activeVipMembers": int(vip_members or 0),
        "postsLast30Days": int(post_count or 0),
        "activeStatuses": int(active_status_count or 0),
        **(
            {"walletFundingLast30DaysKobo": int(wallet_funding or 0)}
            if wallet_funding is not None
            else {}
        ),
        "pendingAccountVerifications": int(
            db.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM profiles p
                    JOIN media_objects m ON m.account_id = p.account_id
                    WHERE p.onboarding_complete = TRUE
                      AND p.document_verification = 'pending'
                      AND m.purpose = 'identity-document'
                      AND NOT EXISTS (
                          SELECT 1 FROM media_objects newer
                          WHERE newer.account_id = m.account_id
                            AND newer.purpose = 'identity-document'
                            AND (
                                newer.created_at > m.created_at
                                OR (newer.created_at = m.created_at AND newer.id > m.id)
                            )
                      )
                    """
                )
            ).scalar_one()
        ),
        "openSafetyReports": int(
            db.execute(text("SELECT COUNT(*) FROM safety_reports WHERE status = 'open'")).scalar_one()
        ),
        "openSafetyReviews": int(
            db.execute(text("SELECT COUNT(*) FROM moderation_review_requests WHERE status = 'open'")).scalar_one()
        ),
        "disputedMeetupPayments": int(
            db.execute(text("SELECT COUNT(*) FROM meetup_payments WHERE status = 'disputed'")).scalar_one()
        ),
        "pendingPayouts": int(
            db.execute(
                text("SELECT COUNT(*) FROM payout_requests WHERE status IN ('initiating', 'pending')")
            ).scalar_one()
        ),
        "failedPrivacyRequests": int(
            db.execute(text("SELECT COUNT(*) FROM privacy_requests WHERE status = 'failed'")).scalar_one()
        ),
        "activeLiveStreams": int(
            db.execute(text("SELECT COUNT(*) FROM live_streams WHERE status = 'live'")).scalar_one()
        ),
        "activeCalls": int(
            db.execute(
                text("SELECT COUNT(*) FROM call_sessions WHERE status IN ('ringing', 'connecting', 'active')")
            ).scalar_one()
        ),
        "lockedAdminAccounts": int(
            db.execute(
                text("SELECT COUNT(*) FROM admin_users WHERE locked_until > :now"),
                {"now": _now()},
            ).scalar_one()
        ),
    }
    record_audit_event(
        db,
        request,
        event_type="admin.dashboard.viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
    )
    db.commit()
    if admin.role == "reviewer":
        return {"pendingAccountVerifications": counts["pendingAccountVerifications"]}
    return {
        **counts,
        "memberSignupsByDay": [
            {"date": signup_date, "count": signup_count}
            for signup_date, signup_count in signup_counts.items()
        ],
    }


@router.get("/gift-catalog")
def list_admin_gift_catalog(
    request: Request,
    db: DbSession,
    admin: Manager,
) -> dict[str, list[dict[str, object]]]:
    rows = db.execute(
        text("SELECT id, name, emoji, price_kobo, active FROM gift_catalog ORDER BY id")
    ).mappings().all()
    record_audit_event(
        db,
        request,
        event_type="admin.gift_catalog.viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
    )
    db.commit()
    return {
        "items": [
            {
                "id": row["id"],
                "name": row["name"],
                "emoji": row["emoji"],
                "priceKobo": int(row["price_kobo"]),
                "active": bool(row["active"]),
            }
            for row in rows
        ]
    }


@router.get("/subscription-plans")
def list_admin_subscription_plans(
    request: Request,
    db: DbSession,
    admin: Manager,
) -> dict[str, list[dict[str, object]]]:
    rows = db.execute(
        text("SELECT id, name, duration_days, price_kobo, active FROM subscription_plans ORDER BY duration_days")
    ).mappings().all()
    record_audit_event(
        db,
        request,
        event_type="admin.subscription_plans.viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
    )
    db.commit()
    return {
        "items": [
            {
                "id": row["id"],
                "name": row["name"],
                "durationDays": int(row["duration_days"]),
                "priceKobo": int(row["price_kobo"]),
                "active": bool(row["active"]),
            }
            for row in rows
        ]
    }


@router.patch(
    "/subscription-plans/{plan_id}",
    dependencies=[Depends(require_admin_csrf)],
)
def update_subscription_plan(
    plan_id: str,
    body: SubscriptionPlanUpdateRequest,
    request: Request,
    db: DbSession,
    admin: Manager,
) -> dict[str, object]:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise ApiException("EMPTY_PLAN_UPDATE", "Provide at least one plan field to update.", 400)
    if "name" in changes and changes["name"] is not None:
        changes["name"] = changes["name"].strip()
        if not changes["name"]:
            raise ApiException("INVALID_PLAN_NAME", "Plan name cannot be empty.", 400)
    if db.execute(text("SELECT 1 FROM subscription_plans WHERE id = :id"), {"id": plan_id}).first() is None:
        raise ApiException("SUBSCRIPTION_PLAN_NOT_FOUND", "This subscription plan is unavailable.", 404)
    assignments = ", ".join(f"{key} = :{key}" for key in changes)
    db.execute(
        text(f"UPDATE subscription_plans SET {assignments} WHERE id = :id"),
        {**changes, "id": plan_id},
    )
    record_audit_event(
        db,
        request,
        event_type="admin.subscription_plan.updated",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
        metadata={"planId": plan_id, "fields": sorted(changes)},
    )
    db.commit()
    updated = db.execute(
        text("SELECT id, name, duration_days, price_kobo, active FROM subscription_plans WHERE id = :id"),
        {"id": plan_id},
    ).mappings().one()
    return {
        "id": updated["id"],
        "name": updated["name"],
        "durationDays": int(updated["duration_days"]),
        "priceKobo": int(updated["price_kobo"]),
        "active": bool(updated["active"]),
    }


@router.get("/subscriptions")
def list_admin_subscriptions(
    request: Request,
    db: DbSession,
    admin: Manager,
    tier: Literal["free", "vip", "all"] = "vip",
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    tier_filter = "" if tier == "all" else "AND p.subscription_tier = :tier"
    params: dict[str, object] = {"limit": limit + 1, "offset": offset}
    if tier != "all":
        params["tier"] = tier
    rows = db.execute(
        text(
            f"""
            SELECT a.id, a.email, p.display_name, p.subscription_tier, p.vip_expires_at
            FROM profiles p JOIN accounts a ON a.id = p.account_id
            WHERE 1 = 1 {tier_filter}
            ORDER BY p.vip_expires_at DESC, a.id
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()
    has_more = len(rows) > limit
    items = [
        {
            "accountId": str(row["id"]),
            "email": row["email"],
            "displayName": row["display_name"],
            "tier": row["subscription_tier"],
            "expiresAt": row["vip_expires_at"],
        }
        for row in rows[:limit]
    ]
    record_audit_event(
        db,
        request,
        event_type="admin.subscriptions.viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
        metadata={"tier": tier, "count": len(items), "offset": offset},
    )
    db.commit()
    return {"items": items, "nextOffset": offset + limit if has_more else None}


@router.put(
    "/users/{account_id}/subscription",
    dependencies=[Depends(require_admin_csrf)],
)
def update_user_subscription(
    account_id: str,
    body: UserSubscriptionRequest,
    request: Request,
    db: DbSession,
    admin: Manager,
) -> dict[str, str | None]:
    reason = body.reason.strip()
    if not reason:
        raise ApiException("INVALID_SUBSCRIPTION_REASON", "Add a reason for changing this subscription.", 400)
    if body.tier == "vip":
        if body.expires_at is None or body.expires_at <= datetime.now(UTC):
            raise ApiException("INVALID_SUBSCRIPTION_EXPIRY", "A future VIP expiry time is required.", 400)
        expires_at = body.expires_at.astimezone(UTC).replace(tzinfo=None)
    else:
        expires_at = None
    result = db.execute(
        text(
            """
            UPDATE profiles
            SET subscription_tier = :tier, vip_expires_at = :expires_at
            WHERE account_id = :account_id
            """
        ),
        {"tier": body.tier, "expires_at": expires_at, "account_id": account_id},
    )
    if result.rowcount != 1:
        raise ApiException("USER_NOT_FOUND", "This member profile is unavailable.", 404)
    record_audit_event(
        db,
        request,
        event_type="admin.subscription.updated",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=account_id,
        outcome="success",
        metadata={"tier": body.tier, "expiresAt": expires_at.isoformat() if expires_at else None, "reason": reason},
    )
    db.commit()
    return {"accountId": account_id, "tier": body.tier, "expiresAt": expires_at.isoformat() if expires_at else None}


@router.post("/gift-catalog", dependencies=[Depends(require_admin_csrf)])
def create_gift_catalog_item(
    body: GiftCatalogCreateRequest,
    request: Request,
    db: DbSession,
    admin: Manager,
) -> dict[str, object]:
    try:
        db.execute(
            text(
                """
                INSERT INTO gift_catalog (id, name, emoji, price_kobo, active)
                VALUES (:id, :name, :emoji, :price_kobo, TRUE)
                """
            ),
            {
                "id": body.id,
                "name": body.name.strip(),
                "emoji": body.emoji,
                "price_kobo": body.price_kobo,
            },
        )
    except IntegrityError as exc:
        db.rollback()
        raise ApiException("GIFT_ALREADY_EXISTS", "A gift with this ID already exists.", 409) from exc
    record_audit_event(
        db,
        request,
        event_type="admin.gift_catalog.created",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
        metadata={"giftId": body.id, "priceKobo": body.price_kobo},
    )
    db.commit()
    return {"id": body.id, "name": body.name.strip(), "emoji": body.emoji, "priceKobo": body.price_kobo, "active": True}


@router.patch(
    "/gift-catalog/{gift_id}",
    dependencies=[Depends(require_admin_csrf)],
)
def update_gift_catalog_item(
    gift_id: str,
    body: GiftCatalogUpdateRequest,
    request: Request,
    db: DbSession,
    admin: Manager,
) -> dict[str, object]:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise ApiException("EMPTY_GIFT_UPDATE", "Provide at least one gift field to update.", 400)
    if "name" in changes and changes["name"] is not None:
        changes["name"] = changes["name"].strip()
    row = db.execute(
        text("SELECT id FROM gift_catalog WHERE id = :id"),
        {"id": gift_id},
    ).first()
    if row is None:
        raise ApiException("GIFT_NOT_FOUND", "This gift is unavailable.", 404)
    assignments = ", ".join(f"{key} = :{key}" for key in changes)
    db.execute(
        text(f"UPDATE gift_catalog SET {assignments} WHERE id = :id"),
        {**changes, "id": gift_id},
    )
    record_audit_event(
        db,
        request,
        event_type="admin.gift_catalog.updated",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
        metadata={"giftId": gift_id, "fields": sorted(changes)},
    )
    db.commit()
    updated = db.execute(
        text("SELECT id, name, emoji, price_kobo, active FROM gift_catalog WHERE id = :id"),
        {"id": gift_id},
    ).mappings().one()
    return {
        "id": updated["id"],
        "name": updated["name"],
        "emoji": updated["emoji"],
        "priceKobo": int(updated["price_kobo"]),
        "active": bool(updated["active"]),
    }


@router.get("/live-streams")
def list_admin_live_streams(
    request: Request,
    db: DbSession,
    admin: SafetyManager,
    status: Literal["live", "ended", "all"] = "live",
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    status_filter = "" if status == "all" else "AND s.status = :status"
    params: dict[str, object] = {"limit": limit + 1, "offset": offset}
    if status != "all":
        params["status"] = status
    rows = db.execute(
        text(
            f"""
            SELECT s.id, s.host_account_id, p.display_name, s.title, s.status,
                   s.started_at, s.ended_at, s.room_closed_at
            FROM live_streams s
            LEFT JOIN profiles p ON p.account_id = s.host_account_id
            WHERE 1 = 1 {status_filter}
            ORDER BY s.started_at DESC, s.id
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).mappings().all()
    has_more = len(rows) > limit
    items = [
        {
            "streamId": str(row["id"]),
            "hostId": str(row["host_account_id"]),
            "hostName": row["display_name"],
            "title": row["title"],
            "status": row["status"],
            "startedAt": row["started_at"],
            "endedAt": row["ended_at"],
            "roomClosedAt": row["room_closed_at"],
        }
        for row in rows[:limit]
    ]
    record_audit_event(
        db,
        request,
        event_type="admin.live_streams.viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
        metadata={"status": status, "count": len(items), "offset": offset},
    )
    db.commit()
    return {"items": items, "nextOffset": offset + limit if has_more else None}


@router.post(
    "/live-streams/{stream_id}/monitor-token",
    dependencies=[Depends(require_admin_csrf)],
)
def create_admin_live_monitor_token(
    stream_id: str,
    request: Request,
    db: DbSession,
    admin: SafetyManager,
) -> dict[str, str]:
    stream = db.execute(
        text("SELECT room_name, host_account_id FROM live_streams WHERE id = :id AND status = 'live'"),
        {"id": stream_id},
    ).mappings().first()
    if stream is None:
        raise ApiException("LIVE_STREAM_NOT_ACTIVE", "This live stream is no longer active.", 409)
    url, token = create_room_token(
        request.app.state.settings,
        room_name=str(stream["room_name"]),
        identity=f"admin-{admin.admin_id}",
        can_publish=False,
        ttl_seconds=1800,
    )
    record_audit_event(
        db,
        request,
        event_type="admin.live_stream.monitor_started",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=str(stream["host_account_id"]),
        outcome="success",
        metadata={"streamId": stream_id},
    )
    db.commit()
    return {"url": url, "token": token}


@router.post(
    "/live-streams/{stream_id}/warnings",
    dependencies=[Depends(require_admin_csrf)],
)
def issue_admin_live_warning(
    stream_id: str,
    body: LiveStreamWarningRequest,
    request: Request,
    db: DbSession,
    admin: SafetyManager,
) -> dict[str, str]:
    reason = body.reason.strip()
    if not reason:
        raise ApiException("LIVE_WARNING_REQUIRED", "Enter a warning for the streamer.", 400)
    stream = db.execute(
        text("SELECT host_account_id, status FROM live_streams WHERE id = :id"),
        {"id": stream_id},
    ).mappings().first()
    if stream is None:
        raise ApiException("LIVE_STREAM_NOT_FOUND", "This live stream is unavailable.", 404)
    if stream["status"] != "live":
        raise ApiException("LIVE_STREAM_NOT_ACTIVE", "This live stream has already ended.", 409)
    message_id = uuid.uuid4().hex
    now = _now()
    warning_label = "Violation warning" if body.severity == "violation" else "Moderator warning"
    warning_text = f"{warning_label}: {reason}"
    db.execute(
        text(
            """
            INSERT INTO live_stream_messages
                (id, stream_id, author_id, kind, message_text, created_at)
            VALUES (:id, :stream_id, :host_id, 'warning', :message, :created_at)
            """
        ),
        {
            "id": message_id,
            "stream_id": stream_id,
            "host_id": str(stream["host_account_id"]),
            "message": warning_text,
            "created_at": now,
        },
    )
    record_audit_event(
        db,
        request,
        event_type="admin.live_stream.warning_issued",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=str(stream["host_account_id"]),
        outcome="success",
        metadata={"streamId": stream_id, "severity": body.severity, "reason": reason},
    )
    _broadcast_stream_event(
        db,
        stream_id,
        "livestream.message",
        {
            "id": message_id,
            "streamId": stream_id,
            "authorId": str(stream["host_account_id"]),
            "authorName": "Flingra moderation",
            "kind": "warning",
            "text": warning_text,
            "giftId": None,
            "createdAt": now.isoformat(),
        },
    )
    db.commit()
    return {"streamId": stream_id, "status": "warning_issued"}


@router.post(
    "/live-streams/{stream_id}/end",
    dependencies=[Depends(require_admin_csrf)],
)
def end_admin_live_stream(
    stream_id: str,
    request: Request,
    db: DbSession,
    admin: SafetyManager,
) -> dict[str, str]:
    stream = db.execute(
        text(
            "SELECT host_account_id, room_name, status, room_closed_at FROM live_streams "
            "WHERE id = :id"
            + (" FOR UPDATE" if db.get_bind().dialect.name != "sqlite" else "")
        ),
        {"id": stream_id},
    ).mappings().first()
    if stream is None:
        raise ApiException("LIVE_STREAM_NOT_FOUND", "This live stream is unavailable.", 404)
    cleanup_pending = stream["status"] == "ended" and stream["room_closed_at"] is None
    if stream["status"] != "live" and not cleanup_pending:
        raise ApiException("LIVE_STREAM_NOT_ACTIVE", "This live stream has already ended.", 409)
    if stream["status"] == "live":
        now = _now()
        db.execute(
            text(
                """
                UPDATE live_streams SET status = 'ended', ended_at = :now
                WHERE id = :id AND status = 'live'
                """
            ),
            {"id": stream_id, "now": now},
        )
        record_audit_event(
            db,
            request,
            event_type="admin.live_stream.ended",
            actor_type="admin",
            actor_id=admin.admin_id,
            subject_account_id=str(stream["host_account_id"]),
            outcome="success",
            metadata={"streamId": stream_id},
        )
        db.commit()

    delete_room(request.app.state.settings, str(stream["room_name"]))
    db.execute(
        text(
            """
            UPDATE live_streams SET room_closed_at = :now
            WHERE id = :id AND status = 'ended' AND room_closed_at IS NULL
            """
        ),
        {"id": stream_id, "now": _now()},
    )
    db.commit()
    return {"streamId": stream_id, "status": "ended"}


@router.get("/content/posts")
def list_admin_posts(
    request: Request,
    db: DbSession,
    admin: SafetyManager,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    rows = db.execute(
        text(
            """
            SELECT post.id, post.author_id, profile.display_name, post.photos,
                   post.video_url, post.caption, post.created_at
            FROM member_posts post
            LEFT JOIN profiles profile ON profile.account_id = post.author_id
            ORDER BY post.created_at DESC, post.id
            LIMIT :limit OFFSET :offset
            """
        ),
        {"limit": limit + 1, "offset": offset},
    ).mappings().all()
    has_more = len(rows) > limit
    items = []
    for row in rows[:limit]:
        photos = row["photos"]
        if isinstance(photos, str):
            photos = json.loads(photos)
        item: dict[str, object] = {
            "postId": str(row["id"]),
            "authorId": str(row["author_id"]),
            "authorName": row["display_name"],
            "caption": row["caption"],
            "createdAt": row["created_at"],
        }
        if admin.role == "super_admin":
            item["photos"] = photos
            item["videoUrl"] = row["video_url"]
        items.append(item)
    record_audit_event(
        db,
        request,
        event_type="admin.content.posts_viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
        metadata={"count": len(items), "offset": offset},
    )
    db.commit()
    return {"items": items, "nextOffset": offset + limit if has_more else None}


@router.delete(
    "/content/posts/{post_id}",
    dependencies=[Depends(require_admin_csrf)],
)
def remove_admin_post(
    post_id: str,
    request: Request,
    db: DbSession,
    admin: SafetyManager,
) -> dict[str, str]:
    author_id = db.execute(
        text("SELECT author_id FROM member_posts WHERE id = :id"),
        {"id": post_id},
    ).scalar_one_or_none()
    if author_id is None:
        raise ApiException("POST_NOT_FOUND", "This post is unavailable.", 404)
    db.execute(text("DELETE FROM member_posts WHERE id = :id"), {"id": post_id})
    record_audit_event(
        db,
        request,
        event_type="admin.content.post_removed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=str(author_id),
        outcome="success",
        metadata={"postId": post_id},
    )
    db.commit()
    return {"postId": post_id, "status": "removed"}


@router.get("/content/statuses")
def list_admin_statuses(
    request: Request,
    db: DbSession,
    admin: SafetyManager,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    rows = db.execute(
        text(
            """
            SELECT status.id, status.author_id, profile.display_name, status.media_url, status.media_kind,
                   status.created_at, status.expires_at
            FROM member_statuses status
            LEFT JOIN profiles profile ON profile.account_id = status.author_id
            ORDER BY status.created_at DESC, status.id
            LIMIT :limit OFFSET :offset
            """
        ),
        {"limit": limit + 1, "offset": offset},
    ).mappings().all()
    has_more = len(rows) > limit
    items = []
    for row in rows[:limit]:
        item: dict[str, object] = {
            "statusId": str(row["id"]),
            "authorId": str(row["author_id"]),
            "authorName": row["display_name"],
            "mediaKind": row["media_kind"],
            "createdAt": row["created_at"],
            "expiresAt": row["expires_at"],
        }
        if admin.role == "super_admin":
            item["mediaUrl"] = row["media_url"]
        items.append(item)
    record_audit_event(
        db,
        request,
        event_type="admin.content.statuses_viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
        metadata={"count": len(items), "offset": offset},
    )
    db.commit()
    return {"items": items, "nextOffset": offset + limit if has_more else None}


@router.delete(
    "/content/statuses/{status_id}",
    dependencies=[Depends(require_admin_csrf)],
)
def remove_admin_status(
    status_id: str,
    request: Request,
    db: DbSession,
    admin: SafetyManager,
) -> dict[str, str]:
    author_id = db.execute(
        text("SELECT author_id FROM member_statuses WHERE id = :id"),
        {"id": status_id},
    ).scalar_one_or_none()
    if author_id is None:
        raise ApiException("STATUS_NOT_FOUND", "This status is unavailable.", 404)
    db.execute(text("DELETE FROM member_statuses WHERE id = :id"), {"id": status_id})
    record_audit_event(
        db,
        request,
        event_type="admin.content.status_removed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=str(author_id),
        outcome="success",
        metadata={"statusId": status_id},
    )
    db.commit()
    return {"statusId": status_id, "status": "removed"}


@router.get("/audit/events")
def list_audit_events(
    request: Request,
    db: DbSession,
    admin: Annotated[AdminAccount, Depends(require_admin_roles("super_admin", "admin", "auditor"))],
    event_type: str | None = Query(default=None, alias="eventType", max_length=80),
    outcome: Literal["success", "failure", "denied"] | None = None,
    account_id: str | None = Query(default=None, alias="accountId", max_length=64),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    rows = db.execute(
        text(
            """
            SELECT event.id, event.event_type, event.actor_type, event.actor_id,
                   event.subject_account_id, event.outcome, event.request_id,
                   event.metadata, event.created_at,
                   COALESCE(actor_profile.display_name, actor_account.email, actor_admin.email) AS actor_name,
                   COALESCE(subject_profile.display_name, subject_account.email) AS account_name
            FROM platform_audit_events event
            LEFT JOIN accounts actor_account
                ON event.actor_type = 'user' AND actor_account.id = event.actor_id
            LEFT JOIN profiles actor_profile
                ON actor_profile.account_id = actor_account.id
            LEFT JOIN admin_users actor_admin
                ON event.actor_type = 'admin' AND actor_admin.id = event.actor_id
            LEFT JOIN accounts subject_account ON subject_account.id = event.subject_account_id
            LEFT JOIN profiles subject_profile ON subject_profile.account_id = subject_account.id
            WHERE (:event_type IS NULL OR event.event_type = :event_type)
              AND (:outcome IS NULL OR event.outcome = :outcome)
              AND (:account_id IS NULL OR event.subject_account_id = :account_id)
            ORDER BY event.created_at DESC, event.id DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {
            "event_type": event_type,
            "outcome": outcome,
            "account_id": account_id,
            "limit": limit + 1,
            "offset": offset,
        },
    ).mappings().all()
    has_more = len(rows) > limit
    record_audit_event(
        db,
        request,
        event_type="admin.audit.events_viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=account_id,
        outcome="success",
        metadata={"eventType": event_type, "outcome": outcome, "offset": offset},
    )
    db.commit()
    return {
        "items": [
            {
                "id": str(row["id"]),
                "eventType": row["event_type"],
                "actorType": row["actor_type"],
                "actorId": row["actor_id"],
                "accountId": row["subject_account_id"],
                "outcome": row["outcome"],
                "requestId": row["request_id"],
                "metadata": row["metadata"],
                "createdAt": row["created_at"],
                "actorName": row["actor_name"],
                "accountName": row["account_name"],
            }
            for row in rows[:limit]
        ],
        "nextOffset": offset + limit if has_more else None,
    }
