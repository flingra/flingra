import hmac
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.config import Settings
from app.dependencies import db_session
from app.errors import ApiException, ServiceUnavailable
from app.routes.auth import get_app_settings
from app.schemas import AdminLoginRequest, AdminReviewDecisionRequest, AdminSessionResponse
from app.security import generate_token, hash_password, hash_token, mask_contact, verify_password
from app.storage import ObjectStorage, get_object_storage

router = APIRouter(prefix="/admin", tags=["admin"])
DbSession = Annotated[Session, Depends(db_session)]
SettingsDependency = Annotated[Settings, Depends(get_app_settings)]
StorageDependency = Annotated[ObjectStorage, Depends(get_object_storage)]
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
REVIEW_ID_PATTERN = re.compile(r"^(profile|document)-([0-9a-f]{32})$")
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)
DUMMY_PASSWORD_HASH = hash_password(generate_token())


class AdminAccount(dict[str, str]):
    @property
    def admin_id(self) -> str:
        return self["id"]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _as_datetime(value: datetime | str) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def _clear_admin_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        "flingra_admin_session",
        path="/admin",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.delete_cookie(
        "flingra_admin_csrf",
        path="/admin",
        secure=settings.session_cookie_secure,
        samesite="strict",
    )


def _check_admin_origin(request: Request, settings: Settings) -> None:
    origin = request.headers.get("origin")
    allowed_origins = settings.admin_allowed_origins or settings.allowed_origins
    if allowed_origins and (origin is None or origin not in allowed_origins):
        raise ApiException("CSRF_FAILED", "Refresh the page and try again.", 403)


def require_admin_csrf(
    request: Request,
    db: DbSession,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    settings = get_app_settings(request)
    origin = request.headers.get("origin")
    allowed_origins = settings.admin_allowed_origins or settings.allowed_origins
    failure_reason = (
        "origin_not_allowed"
        if allowed_origins and (origin is None or origin not in allowed_origins)
        else None
    )
    cookie_token = request.cookies.get("flingra_admin_csrf")
    if not cookie_token or not csrf_header or not re.fullmatch(r"[A-Za-z0-9_-]{20,128}", csrf_header):
        failure_reason = failure_reason or "token_missing_or_malformed"
    elif not hmac.compare_digest(cookie_token, csrf_header):
        failure_reason = failure_reason or "token_mismatch"
    if failure_reason is not None:
        raw_token = request.cookies.get("flingra_admin_session")
        admin_id = (
            db.execute(
                text(
                    """
                    SELECT admin_id FROM admin_sessions
                    WHERE session_token_hash = :token_hash
                      AND revoked_at IS NULL AND expires_at > :now
                    """
                ),
                {"token_hash": hash_token(raw_token), "now": _now()},
            ).scalar_one_or_none()
            if raw_token
            else None
        )
        record_audit_event(
            db,
            request,
            event_type="admin.csrf.denied",
            actor_type="admin" if admin_id is not None else "anonymous",
            actor_id=str(admin_id) if admin_id is not None else None,
            subject_account_id=None,
            outcome="denied",
            metadata={"reason": failure_reason},
        )
        db.commit()
        raise ApiException("CSRF_FAILED", "Refresh the page and try again.", 403)


def get_admin(request: Request, db: DbSession) -> AdminAccount:
    raw_token = request.cookies.get("flingra_admin_session")
    if not raw_token:
        raise ApiException("ADMIN_UNAUTHENTICATED", "Sign in to the admin portal.", 401)
    admin = db.execute(
        text(
            """
            SELECT a.id, a.email
            FROM admin_sessions s
            JOIN admin_users a ON a.id = s.admin_id
            WHERE s.session_token_hash = :token_hash
              AND s.revoked_at IS NULL
              AND s.expires_at > :now
              AND a.disabled_at IS NULL
            """
        ),
        {"token_hash": hash_token(raw_token), "now": _now()},
    ).mappings().first()
    if admin is None:
        raise ApiException("ADMIN_UNAUTHENTICATED", "Sign in to the admin portal.", 401)
    return AdminAccount(admin)


CurrentAdmin = Annotated[AdminAccount, Depends(get_admin)]


def _review_parts(review_id: str) -> tuple[Literal["profile", "identity-document"], str]:
    match = REVIEW_ID_PATTERN.fullmatch(review_id)
    if match is None:
        raise ApiException("REVIEW_NOT_FOUND", "This review is unavailable.", 404)
    review_type = "profile" if match.group(1) == "profile" else "identity-document"
    return review_type, match.group(2)


def _admin_session_response(admin: AdminAccount) -> AdminSessionResponse:
    return AdminSessionResponse(admin_id=admin.admin_id, email=admin["email"])


@router.post("/auth/login", response_model=AdminSessionResponse)
def admin_login(
    body: AdminLoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: SettingsDependency,
) -> AdminSessionResponse:
    try:
        _check_admin_origin(request, settings)
    except ApiException:
        record_audit_event(
            db,
            request,
            event_type="admin.login_origin.denied",
            actor_type="anonymous",
            actor_id=None,
            subject_account_id=None,
            outcome="denied",
            metadata={"reason": "origin_not_allowed"},
        )
        db.commit()
        raise
    email = body.email.strip().lower()
    valid_email = bool(EMAIL_PATTERN.fullmatch(email))
    admin = (
        db.execute(
            text(
                """
                SELECT id, email, password_hash, failed_login_attempts, locked_until
                FROM admin_users
                WHERE email = :email AND disabled_at IS NULL
                """
            ),
            {"email": email},
        ).mappings().first()
        if valid_email
        else None
    )

    password_hash = admin["password_hash"] if admin is not None else DUMMY_PASSWORD_HASH
    password_valid = verify_password(password_hash, body.password)
    now = _now()
    locked = (
        admin is not None
        and admin["locked_until"] is not None
        and _as_datetime(admin["locked_until"]) > now
    )
    if admin is None or not password_valid or locked:
        record_audit_event(
            db,
            request,
            event_type="admin.login",
            actor_type="anonymous",
            actor_id=None,
            subject_account_id=None,
            outcome="denied" if locked else "failure",
            metadata={"reason": "locked" if locked else "invalid_credentials"},
        )
        if admin is not None and not locked:
            db.execute(
                text(
                    """
                    UPDATE admin_users
                    SET locked_until = CASE
                            WHEN failed_login_attempts >= :lock_threshold THEN :locked_until
                            ELSE NULL
                        END,
                        failed_login_attempts = failed_login_attempts + 1
                    WHERE id = :admin_id
                    """
                ),
                {
                    "lock_threshold": MAX_LOGIN_ATTEMPTS - 1,
                    "locked_until": now + LOCKOUT_DURATION,
                    "admin_id": admin["id"],
                },
            )
        db.commit()
        raise ApiException("INVALID_ADMIN_CREDENTIALS", "Email or password is incorrect.", 401)

    db.execute(
        text(
            """
            UPDATE admin_users
            SET failed_login_attempts = 0, locked_until = NULL
            WHERE id = :admin_id
            """
        ),
        {"admin_id": admin["id"]},
    )
    raw_token = generate_token()
    db.execute(
        text(
            """
            INSERT INTO admin_sessions (id, admin_id, session_token_hash, expires_at)
            VALUES (:id, :admin_id, :token_hash, :expires_at)
            """
        ),
        {
            "id": uuid.uuid4().hex,
            "admin_id": admin["id"],
            "token_hash": hash_token(raw_token),
            "expires_at": now + timedelta(hours=settings.admin_session_ttl_hours),
        },
    )
    record_audit_event(
        db,
        request,
        event_type="admin.login",
        actor_type="admin",
        actor_id=str(admin["id"]),
        subject_account_id=None,
        outcome="success",
    )
    db.commit()

    csrf_token = generate_token()
    response.set_cookie(
        "flingra_admin_session",
        raw_token,
        max_age=settings.admin_session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/admin",
    )
    response.set_cookie(
        "flingra_admin_csrf",
        csrf_token,
        max_age=settings.admin_session_ttl_hours * 3600,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/admin",
    )
    return _admin_session_response(AdminAccount({"id": admin["id"], "email": admin["email"]}))


@router.get("/auth/session", response_model=AdminSessionResponse | None)
def admin_session(request: Request, db: DbSession) -> AdminSessionResponse | None:
    raw_token = request.cookies.get("flingra_admin_session")
    if not raw_token:
        return None
    admin = db.execute(
        text(
            """
            SELECT a.id, a.email
            FROM admin_sessions s
            JOIN admin_users a ON a.id = s.admin_id
            WHERE s.session_token_hash = :token_hash
              AND s.revoked_at IS NULL
              AND s.expires_at > :now
              AND a.disabled_at IS NULL
            """
        ),
        {"token_hash": hash_token(raw_token), "now": _now()},
    ).mappings().first()
    return _admin_session_response(AdminAccount(admin)) if admin is not None else None


@router.post(
    "/auth/logout",
    status_code=204,
    dependencies=[Depends(require_admin_csrf)],
)
def admin_logout(
    request: Request,
    response: Response,
    db: DbSession,
    admin: CurrentAdmin,
    settings: SettingsDependency,
) -> Response:
    raw_token = request.cookies.get("flingra_admin_session")
    db.execute(
        text(
            """
            UPDATE admin_sessions SET revoked_at = :now
            WHERE session_token_hash = :token_hash
              AND admin_id = :admin_id AND revoked_at IS NULL
            """
        ),
        {
            "now": _now(),
            "token_hash": hash_token(raw_token or ""),
            "admin_id": admin.admin_id,
        },
    )
    record_audit_event(
        db,
        request,
        event_type="admin.logout",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
    )
    db.commit()
    _clear_admin_cookies(response, settings)
    response.status_code = 204
    return response


@router.get("/reviews")
def list_reviews(
    request: Request,
    db: DbSession,
    admin: CurrentAdmin,
    review_type: Literal["all", "profile", "identity-document"] = Query(
        default="all", alias="type"
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    rows = db.execute(
        text(
            """
            SELECT review_type, review_id, account_id, display_name, review_status,
                   document_type, created_at
            FROM (
                SELECT 'profile' AS review_type,
                       CONCAT('profile-', p.account_id) AS review_id,
                       p.account_id, p.display_name,
                       p.moderation_status AS review_status,
                       NULL AS document_type, p.updated_at AS created_at
                FROM profiles p
                WHERE p.onboarding_complete = TRUE
                  AND p.moderation_status = 'pending'
                  AND :include_profiles = 1
                UNION ALL
                SELECT 'identity-document' AS review_type,
                       CONCAT('document-', m.id) AS review_id,
                       p.account_id, p.display_name,
                       p.document_verification AS review_status,
                       p.document_type, m.created_at
                FROM media_objects m
                JOIN profiles p ON p.account_id = m.account_id
                WHERE m.purpose = 'identity-document'
                  AND p.document_verification = 'pending'
                  AND :include_documents = 1
                  AND NOT EXISTS (
                      SELECT 1 FROM media_objects newer
                      WHERE newer.account_id = m.account_id
                        AND newer.purpose = 'identity-document'
                        AND (
                            newer.created_at > m.created_at
                            OR (newer.created_at = m.created_at AND newer.id > m.id)
                        )
                  )
            ) pending_reviews
            ORDER BY created_at DESC, review_id DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {
            "include_profiles": int(review_type in {"all", "profile"}),
            "include_documents": int(review_type in {"all", "identity-document"}),
            "limit": limit + 1,
            "offset": offset,
        },
    ).mappings().all()
    has_more = len(rows) > limit
    items = [
        {
            "reviewId": row["review_id"],
            "type": row["review_type"],
            "accountId": row["account_id"],
            "displayName": row["display_name"],
            "status": row["review_status"],
            "documentType": row["document_type"],
            "createdAt": row["created_at"],
        }
        for row in rows[:limit]
    ]
    for row in rows[:limit]:
        record_audit_event(
            db,
            request,
            event_type="admin.review.queue_item_viewed",
            actor_type="admin",
            actor_id=admin.admin_id,
            subject_account_id=str(row["account_id"]),
            outcome="success",
            metadata={"reviewType": row["review_type"], "reviewId": row["review_id"]},
        )
    record_audit_event(
        db,
        request,
        event_type="admin.review.queue_viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
        metadata={"type": review_type, "itemCount": len(items), "offset": offset},
    )
    db.commit()
    return {"items": items, "nextOffset": offset + limit if has_more else None}


@router.get("/users/{account_id}/audit")
def get_user_audit_history(
    account_id: str,
    request: Request,
    db: DbSession,
    admin: CurrentAdmin,
    event_type: str | None = Query(default=None, alias="eventType", min_length=1, max_length=80),
    outcome: Literal["success", "failure", "denied"] | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    exists = db.execute(
        text("SELECT 1 FROM accounts WHERE id = :account_id"),
        {"account_id": account_id},
    ).first()
    if exists is None:
        raise ApiException("USER_NOT_FOUND", "This user is unavailable.", 404)

    record_audit_event(
        db,
        request,
        event_type="admin.audit.user_history_viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=account_id,
        outcome="success",
        metadata={"eventType": event_type, "outcome": outcome, "limit": limit, "offset": offset},
    )
    conditions = ["e.subject_account_id = :account_id"]
    parameters: dict[str, object] = {
        "account_id": account_id,
        "limit": limit + 1,
        "offset": offset,
    }
    if event_type is not None:
        conditions.append("e.event_type = :event_type")
        parameters["event_type"] = event_type
    if outcome is not None:
        conditions.append("e.outcome = :outcome")
        parameters["outcome"] = outcome
    rows = db.execute(
        text(
            f"""
            SELECT e.id, e.event_type, e.actor_type, e.actor_id, e.outcome,
                   e.request_id, e.metadata, e.created_at,
                   ua.identifier AS user_actor_identifier,
                   ua.identifier_type AS user_actor_identifier_type,
                   aa.email AS admin_actor_email
            FROM platform_audit_events e
            LEFT JOIN accounts ua ON e.actor_type = 'user' AND ua.id = e.actor_id
            LEFT JOIN admin_users aa ON e.actor_type = 'admin' AND aa.id = e.actor_id
            WHERE {' AND '.join(conditions)}
            ORDER BY e.created_at ASC, e.id ASC
            LIMIT :limit OFFSET :offset
            """
        ),
        parameters,
    ).mappings().all()
    has_more = len(rows) > limit
    events: list[dict[str, object]] = []
    for row in rows[:limit]:
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        if row["actor_type"] == "admin":
            actor_label = row["admin_actor_email"]
        elif row["user_actor_identifier"] is not None:
            actor_label = mask_contact(
                row["user_actor_identifier"],
                row["user_actor_identifier_type"],
            )
        else:
            actor_label = None
        events.append(
            {
                "id": row["id"],
                "eventType": row["event_type"],
                "actorType": row["actor_type"],
                "actorId": row["actor_id"],
                "actorLabel": actor_label,
                "outcome": row["outcome"],
                "requestId": row["request_id"],
                "metadata": metadata,
                "createdAt": row["created_at"],
            }
        )
    db.commit()
    return {"items": events, "nextOffset": offset + limit if has_more else None}


@router.get("/reviews/{review_id}")
def get_review(
    review_id: str,
    request: Request,
    db: DbSession,
    admin: CurrentAdmin,
) -> dict[str, object]:
    review_type, target_id = _review_parts(review_id)
    if review_type == "profile":
        row = db.execute(
            text(
                """
                SELECT p.account_id, p.display_name, p.bio, p.photos, p.area, p.identity,
                       p.moderation_status, p.onboarding_complete,
                       a.identifier, a.identifier_type, a.date_of_birth
                FROM profiles p
                JOIN accounts a ON a.id = p.account_id
                WHERE p.account_id = :account_id AND p.onboarding_complete = TRUE
                """
            ),
            {"account_id": target_id},
        ).mappings().first()
        if row is None:
            raise ApiException("REVIEW_NOT_FOUND", "This review is unavailable.", 404)
        record_audit_event(
            db,
            request,
            event_type="admin.review.details_viewed",
            actor_type="admin",
            actor_id=admin.admin_id,
            subject_account_id=str(row["account_id"]),
            outcome="success",
            metadata={"reviewType": review_type, "reviewId": review_id},
        )
        db.commit()
        photos = row["photos"]
        if isinstance(photos, str):
            photos = json.loads(photos)
        return {
            "reviewId": review_id,
            "type": review_type,
            "accountId": row["account_id"],
            "displayName": row["display_name"],
            "bio": row["bio"],
            "photos": photos,
            "area": row["area"],
            "identity": row["identity"],
            "dateOfBirth": row["date_of_birth"],
            "contact": mask_contact(row["identifier"], row["identifier_type"]),
            "status": row["moderation_status"],
        }

    row = db.execute(
        text(
            """
            SELECT m.id, m.account_id, m.object_key, m.content_type, m.size_bytes,
                   m.created_at, p.display_name, p.document_type, p.document_verification
            FROM media_objects m
            JOIN profiles p ON p.account_id = m.account_id
            WHERE m.id = :media_id AND m.purpose = 'identity-document'
              AND p.document_verification = 'pending'
            """
        ),
        {"media_id": target_id},
    ).mappings().first()
    if row is None:
        raise ApiException("REVIEW_NOT_FOUND", "This review is unavailable.", 404)
    try:
        signed_url = storage.get_url(row["object_key"])
    except ServiceUnavailable:
        record_audit_event(
            db,
            request,
            event_type="admin.review.document_viewed",
            actor_type="admin",
            actor_id=admin.admin_id,
            subject_account_id=str(owner_id),
            outcome="failure",
            metadata={"reviewId": review_id, "reason": "storage_unavailable"},
        )
        db.commit()
        raise
    record_audit_event(
        db,
        request,
        event_type="admin.review.details_viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=str(row["account_id"]),
        outcome="success",
        metadata={"reviewType": review_type, "reviewId": review_id},
    )
    db.commit()
    return {
        "reviewId": review_id,
        "type": review_type,
        "accountId": row["account_id"],
        "displayName": row["display_name"],
        "documentType": row["document_type"],
        "contentType": row["content_type"],
        "sizeBytes": row["size_bytes"],
        "createdAt": row["created_at"],
        "status": row["document_verification"],
    }


@router.get("/reviews/{review_id}/document")
def get_review_document(
    review_id: str,
    request: Request,
    db: DbSession,
    admin: CurrentAdmin,
    storage: StorageDependency,
) -> RedirectResponse:
    review_type, target_id = _review_parts(review_id)
    if review_type != "identity-document":
        raise ApiException("REVIEW_NOT_FOUND", "This review is unavailable.", 404)
    row = db.execute(
        text(
            """
            SELECT m.object_key
            FROM media_objects m
            JOIN profiles p ON p.account_id = m.account_id
            WHERE m.id = :media_id
              AND m.purpose = 'identity-document'
              AND p.document_verification = 'pending'
            """
        ),
        {"media_id": target_id},
    ).mappings().first()
    if row is None:
        raise ApiException("REVIEW_NOT_FOUND", "This review is unavailable.", 404)
    owner_id = db.execute(
        text("SELECT account_id FROM media_objects WHERE id = :media_id"),
        {"media_id": target_id},
    ).scalar_one()
    record_audit_event(
        db,
        request,
        event_type="admin.review.document_viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=str(owner_id),
        outcome="success",
        metadata={"reviewId": review_id},
    )
    db.commit()
    return RedirectResponse(
        signed_url,
        status_code=307,
        headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"},
    )


@router.post(
    "/reviews/{review_id}/decision",
    dependencies=[Depends(require_admin_csrf)],
)
def decide_review(
    review_id: str,
    body: AdminReviewDecisionRequest,
    request: Request,
    db: DbSession,
    admin: CurrentAdmin,
) -> dict[str, str]:
    reason = body.reason.strip()
    if not reason:
        raise ApiException("INVALID_REVIEW_DECISION", "A non-empty decision reason is required.")
    review_type, target_id = _review_parts(review_id)
    if review_type == "profile":
        result = db.execute(
            text(
                """
                UPDATE profiles
                SET moderation_status = :decision
                WHERE account_id = :account_id
                  AND onboarding_complete = TRUE
                  AND moderation_status = 'pending'
                """
            ),
            {"decision": body.decision, "account_id": target_id},
        )
    else:
        result = db.execute(
            text(
                """
                UPDATE profiles
                SET document_verification = :document_status
                WHERE account_id = (
                    SELECT account_id FROM media_objects
                    WHERE id = :media_id AND purpose = 'identity-document'
                )
                  AND document_verification = 'pending'
                  AND EXISTS (
                      SELECT 1 FROM media_objects m
                      WHERE m.id = :media_id
                        AND m.account_id = profiles.account_id
                        AND m.purpose = 'identity-document'
                  )
                """
            ),
            {
                "document_status": "verified" if body.decision == "approved" else "rejected",
                "media_id": target_id,
            },
        )
    if result.rowcount != 1:
        db.rollback()
        raise ApiException("REVIEW_NOT_FOUND", "This review is unavailable or has already been decided.", 404)
    subject_account_id = (
        target_id
        if review_type == "profile"
        else db.execute(
            text("SELECT account_id FROM media_objects WHERE id = :media_id"),
            {"media_id": target_id},
        ).scalar_one()
    )
    record_audit_event(
        db,
        request,
        event_type="admin.review.decided",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=str(subject_account_id),
        outcome="success",
        metadata={
            "reviewType": review_type,
            "reviewId": review_id,
            "decision": body.decision,
            "reason": reason,
        },
    )
    db.commit()
    return {"reviewId": review_id, "status": body.decision}
