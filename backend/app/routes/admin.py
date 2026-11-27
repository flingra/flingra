import hmac
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, cast

import pyotp
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.config import Settings
from app.dependencies import db_session
from app.errors import ApiException, ServiceUnavailable
from app.routes.auth import get_app_settings
from app.schemas import (
    AdminAccountUpdateRequest,
    AdminAccountCreateRequest,
    AdminLoginRequest,
    AdminMfaVerifyRequest,
    AdminPasswordChangeRequest,
    AdminReviewDecisionRequest,
    AdminRole,
    AdminSessionResponse,
)
from app.feature_schemas import CallCreditPriceRequest
from app.security import generate_token, hash_password, hash_token, mask_contact, verify_password
from app.storage import ObjectStorage, get_object_storage

router = APIRouter(prefix="/admin", tags=["admin"])
DbSession = Annotated[Session, Depends(db_session)]
SettingsDependency = Annotated[Settings, Depends(get_app_settings)]
StorageDependency = Annotated[ObjectStorage, Depends(get_object_storage)]
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
REVIEW_ID_PATTERN = re.compile(r"^verification-([0-9a-f]{32})$")
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)
DUMMY_PASSWORD_HASH = hash_password(generate_token())
ADMIN_COOKIE_PATH = "/"


class AdminAccount(dict[str, str]):
    @property
    def admin_id(self) -> str:
        return self["id"]

    @property
    def role(self) -> AdminRole:
        return cast(AdminRole, self["role"])


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _as_datetime(value: datetime | str) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def _clear_admin_cookies(response: Response, settings: Settings) -> None:
    same_site = "none" if settings.session_cookie_secure else "lax"
    response.delete_cookie(
        "flingra_admin_session",
        path=ADMIN_COOKIE_PATH,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=same_site,
    )
    response.delete_cookie(
        "flingra_admin_csrf",
        path=ADMIN_COOKIE_PATH,
        secure=settings.session_cookie_secure,
        samesite=same_site,
    )


def _check_admin_origin(request: Request, settings: Settings) -> None:
    origin = request.headers.get("origin")
    allowed_origins = settings.admin_allowed_origins or settings.allowed_origins
    if allowed_origins and (origin is None or origin not in allowed_origins):
        raise ApiException("CSRF_FAILED", "Refresh the page and try again.", 403)


def require_admin_csrf(
    request: Request,
    response: Response,
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
        if cookie_token and re.fullmatch(r"[A-Za-z0-9_-]{20,128}", cookie_token):
            response.headers["X-CSRF-Token"] = cookie_token
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
            SELECT a.id, a.email, a.role
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


def require_admin_roles(*roles: AdminRole):
    def dependency(
        request: Request,
        db: DbSession,
        admin: CurrentAdmin,
    ) -> AdminAccount:
        if admin.role not in roles:
            record_audit_event(
                db,
                request,
                event_type="admin.authorization.denied",
                actor_type="admin",
                actor_id=admin.admin_id,
                subject_account_id=None,
                outcome="denied",
                metadata={"role": admin.role, "requiredRoles": list(roles)},
            )
            db.commit()
            raise ApiException("ADMIN_FORBIDDEN", "You do not have permission to perform this action.", 403)
        return admin

    return dependency


def _review_parts(review_id: str) -> tuple[Literal["account-verification"], str]:
    match = REVIEW_ID_PATTERN.fullmatch(review_id)
    if match is None:
        raise ApiException("REVIEW_NOT_FOUND", "This review is unavailable.", 404)
    return "account-verification", match.group(1)


def _admin_session_response(admin: AdminAccount) -> AdminSessionResponse:
    return AdminSessionResponse(admin_id=admin.admin_id, email=admin["email"], role=admin.role)


def _record_admin_account_denial(
    db: Session,
    request: Request,
    admin: AdminAccount,
    *,
    target_admin_id: str,
    reason: str,
) -> None:
    record_audit_event(
        db,
        request,
        event_type="admin.account.update_denied",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="denied",
        metadata={"targetAdminId": target_admin_id, "reason": reason},
    )
    db.commit()


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
                SELECT id, email, password_hash, failed_login_attempts, locked_until, role,
                       totp_secret, totp_enabled
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

    if admin["totp_enabled"]:
        code = body.mfa_code or ""
        secret = admin["totp_secret"]
        if not code:
            record_audit_event(
                db,
                request,
                event_type="admin.login",
                actor_type="anonymous",
                actor_id=None,
                subject_account_id=None,
                outcome="denied",
                metadata={"reason": "mfa_required"},
            )
            db.commit()
            raise ApiException("ADMIN_MFA_REQUIRED", "Enter your authenticator code to continue.", 401)
        if not secret or not pyotp.TOTP(str(secret)).verify(code, valid_window=1):
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
            record_audit_event(
                db,
                request,
                event_type="admin.login",
                actor_type="anonymous",
                actor_id=None,
                subject_account_id=None,
                outcome="failure",
                metadata={"reason": "invalid_mfa"},
            )
            db.commit()
            raise ApiException("ADMIN_MFA_INVALID", "The authenticator code is invalid.", 401)

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
    response.headers["X-CSRF-Token"] = csrf_token
    same_site = "none" if settings.session_cookie_secure else "lax"
    response.set_cookie(
        "flingra_admin_session",
        raw_token,
        max_age=settings.admin_session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=same_site,
        path=ADMIN_COOKIE_PATH,
    )
    response.set_cookie(
        "flingra_admin_csrf",
        csrf_token,
        max_age=settings.admin_session_ttl_hours * 3600,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite=same_site,
        path=ADMIN_COOKIE_PATH,
    )
    return _admin_session_response(
        AdminAccount({"id": admin["id"], "email": admin["email"], "role": admin["role"]})
    )


@router.get("/auth/session", response_model=AdminSessionResponse | None)
def admin_session(request: Request, response: Response, db: DbSession) -> AdminSessionResponse | None:
    raw_token = request.cookies.get("flingra_admin_session")
    if not raw_token:
        return None
    csrf_token = request.cookies.get("flingra_admin_csrf")
    if csrf_token:
        response.headers["X-CSRF-Token"] = csrf_token
    admin = db.execute(
        text(
            """
            SELECT a.id, a.email, a.role
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


@router.post(
    "/auth/mfa/setup",
    dependencies=[Depends(require_admin_csrf)],
)
def setup_admin_mfa(
    request: Request,
    db: DbSession,
    admin: CurrentAdmin,
) -> dict[str, str]:
    secret = pyotp.random_base32()
    db.execute(
        text("UPDATE admin_users SET totp_pending_secret = :secret WHERE id = :id"),
        {"secret": secret, "id": admin.admin_id},
    )
    record_audit_event(
        db,
        request,
        event_type="admin.mfa.setup_started",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
    )
    db.commit()
    return {
        "secret": secret,
        "provisioningUri": pyotp.TOTP(secret).provisioning_uri(
            name=admin["email"],
            issuer_name="Flingra Admin",
        ),
    }


@router.get("/auth/mfa/status")
def get_admin_mfa_status(
    db: DbSession,
    admin: CurrentAdmin,
) -> dict[str, bool]:
    enabled = db.execute(
        text("SELECT totp_enabled FROM admin_users WHERE id = :id"),
        {"id": admin.admin_id},
    ).scalar_one()
    return {"enabled": bool(enabled)}


@router.post(
    "/auth/mfa/enable",
    dependencies=[Depends(require_admin_csrf)],
)
def enable_admin_mfa(
    body: AdminMfaVerifyRequest,
    request: Request,
    db: DbSession,
    admin: CurrentAdmin,
) -> dict[str, bool]:
    secret = db.execute(
        text("SELECT totp_pending_secret FROM admin_users WHERE id = :id"),
        {"id": admin.admin_id},
    ).scalar_one_or_none()
    if not secret or not pyotp.TOTP(str(secret)).verify(body.code, valid_window=1):
        raise ApiException("ADMIN_MFA_CODE_INVALID", "The authenticator code is invalid.", 400)
    db.execute(
        text(
            """
            UPDATE admin_users
            SET totp_secret = :secret, totp_pending_secret = NULL, totp_enabled = TRUE
            WHERE id = :id
            """
        ),
        {"secret": secret, "id": admin.admin_id},
    )
    raw_token = request.cookies.get("flingra_admin_session", "")
    db.execute(
        text(
            """
            UPDATE admin_sessions SET revoked_at = :now
            WHERE admin_id = :admin_id AND revoked_at IS NULL
              AND session_token_hash != :token_hash
            """
        ),
        {"now": _now(), "admin_id": admin.admin_id, "token_hash": hash_token(raw_token)},
    )
    record_audit_event(
        db,
        request,
        event_type="admin.mfa.enabled",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
    )
    db.commit()
    return {"enabled": True}


@router.post(
    "/auth/mfa/disable",
    dependencies=[Depends(require_admin_csrf)],
)
def disable_admin_mfa(
    body: AdminMfaVerifyRequest,
    request: Request,
    db: DbSession,
    admin: CurrentAdmin,
) -> dict[str, bool]:
    secret = db.execute(
        text("SELECT totp_secret FROM admin_users WHERE id = :id AND totp_enabled = TRUE"),
        {"id": admin.admin_id},
    ).scalar_one_or_none()
    if not secret or not pyotp.TOTP(str(secret)).verify(body.code, valid_window=1):
        raise ApiException("ADMIN_MFA_CODE_INVALID", "The authenticator code is invalid.", 400)
    db.execute(
        text(
            """
            UPDATE admin_users
            SET totp_secret = NULL, totp_pending_secret = NULL, totp_enabled = FALSE
            WHERE id = :id
            """
        ),
        {"id": admin.admin_id},
    )
    record_audit_event(
        db,
        request,
        event_type="admin.mfa.disabled",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
    )
    db.commit()
    return {"enabled": False}


@router.post(
    "/auth/password",
    dependencies=[Depends(require_admin_csrf)],
)
def change_admin_password(
    body: AdminPasswordChangeRequest,
    request: Request,
    db: DbSession,
    admin: CurrentAdmin,
) -> dict[str, str]:
    password_hash = db.execute(
        text("SELECT password_hash FROM admin_users WHERE id = :id"),
        {"id": admin.admin_id},
    ).scalar_one()
    if not verify_password(password_hash, body.current_password):
        record_audit_event(
            db,
            request,
            event_type="admin.password.change_denied",
            actor_type="admin",
            actor_id=admin.admin_id,
            subject_account_id=None,
            outcome="denied",
            metadata={"reason": "current_password_invalid"},
        )
        db.commit()
        raise ApiException("ADMIN_PASSWORD_INVALID", "Current password is incorrect.", 400)
    if body.current_password == body.new_password:
        raise ApiException("ADMIN_PASSWORD_UNCHANGED", "Choose a new password different from the current one.", 400)
    db.execute(
        text("UPDATE admin_users SET password_hash = :password_hash WHERE id = :id"),
        {"password_hash": hash_password(body.new_password), "id": admin.admin_id},
    )
    raw_token = request.cookies.get("flingra_admin_session", "")
    db.execute(
        text(
            """
            UPDATE admin_sessions SET revoked_at = :now
            WHERE admin_id = :admin_id AND revoked_at IS NULL
              AND session_token_hash != :token_hash
            """
        ),
        {"now": _now(), "admin_id": admin.admin_id, "token_hash": hash_token(raw_token)},
    )
    record_audit_event(
        db,
        request,
        event_type="admin.password.changed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
    )
    db.commit()
    return {"status": "updated"}


@router.get("/call-credits/price")
def get_call_credit_price(
    request: Request,
    db: DbSession,
    admin: Annotated[AdminAccount, Depends(require_admin_roles("super_admin"))],
) -> dict[str, int]:
    price = db.execute(
        text("SELECT price_naira FROM call_credit_pricing WHERE id = 1")
    ).scalar_one_or_none()
    if price is None:
        raise ServiceUnavailable("Call-credit pricing is not configured.")
    record_audit_event(
        db,
        request,
        event_type="admin.call_credit_price.viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
    )
    db.commit()
    return {"priceNaira": int(price)}


@router.put(
    "/call-credits/price",
    dependencies=[Depends(require_admin_csrf)],
)
def set_call_credit_price(
    body: CallCreditPriceRequest,
    request: Request,
    db: DbSession,
    admin: Annotated[AdminAccount, Depends(require_admin_roles("super_admin"))],
) -> dict[str, int]:
    result = db.execute(
        text(
            """
            UPDATE call_credit_pricing
            SET price_naira = :price_naira, updated_at = :now
            WHERE id = 1
            """
        ),
        {"price_naira": body.price_naira, "now": _now()},
    )
    if result.rowcount != 1:
        raise ServiceUnavailable("Call-credit pricing is not configured.")
    record_audit_event(
        db,
        request,
        event_type="admin.call_credit_price.updated",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
        metadata={"priceNaira": body.price_naira},
    )
    db.commit()
    return {"priceNaira": body.price_naira}


@router.get("/admins")
def list_admin_accounts(
    request: Request,
    db: DbSession,
    admin: Annotated[AdminAccount, Depends(require_admin_roles("super_admin"))],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    rows = db.execute(
        text(
            """
            SELECT id, email, role, disabled_at, created_at
            FROM admin_users
            ORDER BY email, id
            LIMIT :limit OFFSET :offset
            """
        ),
        {"limit": limit + 1, "offset": offset},
    ).mappings().all()
    has_more = len(rows) > limit
    record_audit_event(
        db,
        request,
        event_type="admin.account.list_viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
        metadata={"itemCount": min(len(rows), limit), "offset": offset},
    )
    db.commit()
    return {
        "items": [
            {
                "adminId": row["id"],
                "email": row["email"],
                "role": row["role"],
                "disabled": row["disabled_at"] is not None,
                "createdAt": row["created_at"],
            }
            for row in rows[:limit]
        ],
        "nextOffset": offset + limit if has_more else None,
    }


@router.post(
    "/admins",
    dependencies=[Depends(require_admin_csrf)],
)
def create_admin_account(
    body: AdminAccountCreateRequest,
    request: Request,
    db: DbSession,
    admin: Annotated[AdminAccount, Depends(require_admin_roles("super_admin"))],
) -> dict[str, object]:
    email = body.email.strip().lower()
    if not EMAIL_PATTERN.fullmatch(email):
        raise ApiException("INVALID_ADMIN_EMAIL", "Enter a valid admin email address.")
    admin_id = uuid.uuid4().hex
    try:
        db.execute(
            text(
                """
                INSERT INTO admin_users (id, email, password_hash, role)
                VALUES (:id, :email, :password_hash, :role)
                """
            ),
            {"id": admin_id, "email": email, "password_hash": hash_password(body.password), "role": body.role},
        )
    except Exception as exc:
        db.rollback()
        if "Duplicate" in str(exc):
            raise ApiException("ADMIN_EXISTS", "An admin account with that email already exists.", 409) from None
        raise
    record_audit_event(
        db,
        request,
        event_type="admin.account.created",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
        metadata={"targetAdminId": admin_id, "role": body.role},
    )
    db.commit()
    return {"adminId": admin_id, "email": email, "role": body.role, "disabled": False, "createdAt": _now()}


@router.patch(
    "/admins/{target_admin_id}",
    dependencies=[Depends(require_admin_csrf)],
)
def update_admin_account(
    target_admin_id: str,
    body: AdminAccountUpdateRequest,
    request: Request,
    db: DbSession,
    admin: Annotated[AdminAccount, Depends(require_admin_roles("super_admin"))],
) -> dict[str, object]:
    if target_admin_id == admin.admin_id:
        _record_admin_account_denial(
            db,
            request,
            admin,
            target_admin_id=target_admin_id,
            reason="self_update",
        )
        raise ApiException("ADMIN_SELF_UPDATE_DENIED", "Use another super admin to change your own account.", 400)

    target_query = """
        SELECT id, email, role, disabled_at, created_at
        FROM admin_users
        WHERE id = :admin_id
    """
    if db.get_bind().dialect.name == "mysql":
        target_query += " FOR UPDATE"
    target = db.execute(
        text(target_query),
        {"admin_id": target_admin_id},
    ).mappings().first()
    if target is None:
        raise ApiException("ADMIN_NOT_FOUND", "This admin account is unavailable.", 404)

    changes = body.model_dump(exclude_unset=True)
    role = body.role if body.role is not None else target["role"]
    disabled_at = (
        _now()
        if body.disabled is True
        else None
        if body.disabled is False
        else target["disabled_at"]
    )
    removes_active_super_admin = (
        target["role"] == "super_admin"
        and target["disabled_at"] is None
        and (role != "super_admin" or disabled_at is not None)
    )
    if removes_active_super_admin:
        if db.get_bind().dialect.name == "mysql":
            active_super_admin_rows = db.execute(
                text(
                    """
                    SELECT id FROM admin_users
                    WHERE role = 'super_admin' AND disabled_at IS NULL
                    FOR UPDATE
                    """
                )
            ).all()
            active_super_admins = len(active_super_admin_rows)
        else:
            active_super_admins = db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM admin_users
                    WHERE role = 'super_admin' AND disabled_at IS NULL
                    """
                )
            ).scalar_one()
        if active_super_admins <= 1:
            _record_admin_account_denial(
                db,
                request,
                admin,
                target_admin_id=target_admin_id,
                reason="last_super_admin",
            )
            raise ApiException(
                "LAST_SUPER_ADMIN",
                "At least one active super admin must remain.",
                409,
            )

    db.execute(
        text(
            """
            UPDATE admin_users
            SET role = :role, disabled_at = :disabled_at
            WHERE id = :admin_id
            """
        ),
        {"role": role, "disabled_at": disabled_at, "admin_id": target_admin_id},
    )
    if body.disabled is True:
        db.execute(
            text(
                """
                UPDATE admin_sessions
                SET revoked_at = :now
                WHERE admin_id = :admin_id AND revoked_at IS NULL
                """
            ),
            {"now": _now(), "admin_id": target_admin_id},
        )

    record_audit_event(
        db,
        request,
        event_type="admin.account.updated",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
        metadata={
            "targetAdminId": target_admin_id,
            "changedFields": sorted(changes),
            "role": role,
            "disabled": disabled_at is not None,
        },
    )
    db.commit()
    return {
        "adminId": target["id"],
        "email": target["email"],
        "role": role,
        "disabled": disabled_at is not None,
        "createdAt": target["created_at"],
    }


@router.get("/reviews")
def list_reviews(
    request: Request,
    db: DbSession,
    admin: Annotated[
        AdminAccount,
        Depends(require_admin_roles("super_admin", "reviewer")),
    ],
    review_type: Literal["all", "account-verification"] = Query(default="all", alias="type"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    rows = db.execute(
        text(
            """
            SELECT CONCAT('verification-', p.account_id) AS review_id,
                   p.account_id, p.display_name, p.moderation_status,
                   p.document_verification, p.document_type, m.created_at
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
            ORDER BY m.created_at DESC, review_id DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {
            "limit": limit + 1,
            "offset": offset,
        },
    ).mappings().all()
    has_more = len(rows) > limit
    items = [
        {
            "reviewId": row["review_id"],
            "type": "account-verification",
            "accountId": row["account_id"],
            "displayName": row["display_name"],
            "status": "pending",
            "profileStatus": row["moderation_status"],
            "documentStatus": row["document_verification"],
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
            metadata={"reviewType": "account-verification", "reviewId": row["review_id"]},
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
    admin: Annotated[
        AdminAccount,
        Depends(require_admin_roles("super_admin", "safety_admin", "auditor")),
    ],
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
    admin: Annotated[
        AdminAccount,
        Depends(require_admin_roles("super_admin", "reviewer")),
    ],
) -> dict[str, object]:
    review_type, account_id = _review_parts(review_id)
    row = db.execute(
        text(
            """
            SELECT p.account_id, p.display_name, p.bio, p.photos, p.area, p.identity,
                   p.moderation_status, p.document_type, p.document_verification,
                   a.identifier, a.identifier_type, a.date_of_birth, a.account_state,
                   m.id AS document_id, m.content_type, m.size_bytes, m.created_at
            FROM profiles p
            JOIN accounts a ON a.id = p.account_id
            JOIN media_objects m ON m.account_id = p.account_id
            WHERE p.account_id = :account_id
              AND p.onboarding_complete = TRUE
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
        ),
        {"account_id": account_id},
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
        "accountStatus": row["account_state"],
        "profileStatus": row["moderation_status"],
        "documentStatus": row["document_verification"],
        "documentType": row["document_type"],
        "contentType": row["content_type"],
        "sizeBytes": row["size_bytes"],
        "documentSubmittedAt": row["created_at"],
    }


@router.get("/reviews/{review_id}/document")
def get_review_document(
    review_id: str,
    request: Request,
    db: DbSession,
    admin: Annotated[
        AdminAccount,
        Depends(require_admin_roles("super_admin", "reviewer")),
    ],
    storage: StorageDependency,
) -> RedirectResponse:
    review_type, account_id = _review_parts(review_id)
    row = db.execute(
        text(
            """
            SELECT m.account_id, m.object_key
            FROM media_objects m
            JOIN profiles p ON p.account_id = m.account_id
            WHERE m.account_id = :account_id
              AND m.purpose = 'identity-document'
              AND p.document_verification = 'pending'
              AND p.onboarding_complete = TRUE
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
        ),
        {"account_id": account_id},
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
            subject_account_id=str(row["account_id"]),
            outcome="failure",
            metadata={"reviewId": review_id, "reason": "storage_unavailable"},
        )
        db.commit()
        raise
    record_audit_event(
        db,
        request,
        event_type="admin.review.document_viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=str(row["account_id"]),
        outcome="success",
        metadata={"reviewId": review_id},
    )
    db.commit()
    return RedirectResponse(
        signed_url,
        status_code=307,
        headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"},
    )


@router.get("/reviews/{review_id}/profile-photos/{media_id}")
def get_review_profile_photo(
    review_id: str,
    media_id: str,
    request: Request,
    db: DbSession,
    admin: Annotated[
        AdminAccount,
        Depends(require_admin_roles("super_admin", "reviewer")),
    ],
    storage: StorageDependency,
) -> RedirectResponse:
    review_type, account_id = _review_parts(review_id)
    row = db.execute(
        text(
            """
            SELECT m.object_key
            FROM media_objects m
            JOIN profiles p ON p.account_id = m.account_id
            WHERE m.id = :media_id
              AND m.account_id = :account_id
              AND m.purpose = 'profile-photo'
              AND p.onboarding_complete = TRUE
              AND p.document_verification = 'pending'
              AND EXISTS (
                  SELECT 1 FROM media_objects doc
                  WHERE doc.account_id = p.account_id
                    AND doc.purpose = 'identity-document'
                    AND NOT EXISTS (
                        SELECT 1 FROM media_objects newer
                        WHERE newer.account_id = doc.account_id
                          AND newer.purpose = 'identity-document'
                          AND (
                              newer.created_at > doc.created_at
                              OR (newer.created_at = doc.created_at AND newer.id > doc.id)
                          )
                    )
              )
            """
        ),
        {"account_id": account_id, "media_id": media_id},
    ).mappings().first()
    if row is None:
        raise ApiException("REVIEW_NOT_FOUND", "This review is unavailable.", 404)
    try:
        signed_url = storage.get_url(row["object_key"])
    except ServiceUnavailable:
        record_audit_event(
            db,
            request,
            event_type="admin.review.profile_photo_viewed",
            actor_type="admin",
            actor_id=admin.admin_id,
            subject_account_id=account_id,
            outcome="failure",
            metadata={"reviewId": review_id, "mediaId": media_id, "reason": "storage_unavailable"},
        )
        db.commit()
        raise
    record_audit_event(
        db,
        request,
        event_type="admin.review.profile_photo_viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=account_id,
        outcome="success",
        metadata={"reviewType": review_type, "reviewId": review_id, "mediaId": media_id},
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
    admin: Annotated[
        AdminAccount,
        Depends(require_admin_roles("super_admin", "reviewer")),
    ],
) -> dict[str, str]:
    reason = body.reason.strip()
    if not reason:
        raise ApiException("INVALID_REVIEW_DECISION", "A non-empty decision reason is required.")
    review_type, account_id = _review_parts(review_id)
    result = db.execute(
        text(
            """
            UPDATE profiles
            SET moderation_status = :decision,
                document_verification = :document_status
            WHERE account_id = :account_id
              AND onboarding_complete = TRUE
              AND document_verification = 'pending'
              AND EXISTS (
                  SELECT 1 FROM media_objects doc
                  WHERE doc.account_id = profiles.account_id
                    AND doc.purpose = 'identity-document'
                    AND NOT EXISTS (
                        SELECT 1 FROM media_objects newer
                        WHERE newer.account_id = doc.account_id
                          AND newer.purpose = 'identity-document'
                          AND (
                              newer.created_at > doc.created_at
                              OR (newer.created_at = doc.created_at AND newer.id > doc.id)
                          )
                    )
              )
            """
        ),
        {
            "decision": body.decision,
            "document_status": "verified" if body.decision == "approved" else "rejected",
            "account_id": account_id,
        },
    )
    if result.rowcount != 1:
        db.rollback()
        raise ApiException("REVIEW_NOT_FOUND", "This review is unavailable or has already been decided.", 404)
    record_audit_event(
        db,
        request,
        event_type="admin.review.decided",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=account_id,
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
