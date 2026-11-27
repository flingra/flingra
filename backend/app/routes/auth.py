import hmac
import base64
import io
import json
import logging
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal
from urllib.parse import quote

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.id_token import verify_oauth2_token
import pyotp
import qrcode
from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.config import Settings
from app.dependencies import db_session
from app.errors import ApiException, ServiceUnavailable
from app.notifications import send_password_reset, send_two_factor_code, send_verification_code
from app.referrals import ensure_referral_code, normalize_referral_code
from app.schemas import (
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    GoogleAuthRequest,
    SessionResponse,
    SignInRequest,
    SignUpRequest,
    StageResponse,
    VerifyContactRequest,
    TwoFactorCodeRequest,
)
from app.security import (
    generate_token,
    generate_verification_code,
    hash_password,
    hash_token,
    mask_contact,
    verify_password,
)

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/auth", tags=["auth"])
DbSession = Annotated[Session, Depends(db_session)]
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_CLEANUP = re.compile(r"[\s().-]")
PHONE_PATTERN = re.compile(r"^\+?\d{7,15}$")
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)
VERIFICATION_LIFETIME = timedelta(minutes=10)
RESET_LIFETIME = timedelta(minutes=30)
TWO_FACTOR_LIFETIME = timedelta(minutes=10)
MINIMUM_ACCOUNT_AGE = 21


class AuthenticatedAccount(dict[str, Any]):
    @property
    def account_id(self) -> str:
        return str(self["id"])

    @property
    def stage(self) -> str:
        if not self["email_verified"]:
            return "needs-verification"
        return "active" if self["onboarding_complete"] else "needs-onboarding"


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


SettingsDependency = Annotated[Settings, Depends(get_app_settings)]


def _normalize_identifier(value: str, sex: str) -> tuple[str, str, str | None]:
    identifier = value.strip()
    if EMAIL_PATTERN.fullmatch(identifier):
        email = identifier.lower()
        return email, "email", email
    if sex == "woman":
        raise ApiException("EMAIL_REQUIRED", "Enter a valid email address.")
    normalized_phone = PHONE_CLEANUP.sub("", identifier)
    if PHONE_PATTERN.fullmatch(normalized_phone):
        return normalized_phone, "phone", None
    raise ApiException("INVALID_IDENTIFIER", "Enter a valid email address or mobile number.")


def _age_on(birth_date: date | str, today: date) -> int:
    if isinstance(birth_date, str):
        birth_date = date.fromisoformat(birth_date)
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def _age_range(birth_date: date) -> str:
    age = _age_on(birth_date, date.today())
    lower = (age // 5) * 5
    return f"{lower}–{lower + 5}"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _as_datetime(value: datetime | str) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def _stage(account: AuthenticatedAccount) -> str:
    return account.stage


def _set_session_cookies(response: Response, request: Request, raw_token: str) -> None:
    settings = get_app_settings(request)
    csrf_token = generate_token()
    response.headers["X-CSRF-Token"] = csrf_token
    same_site = "none" if settings.session_cookie_secure else "lax"
    response.set_cookie(
        settings.session_cookie_name,
        raw_token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=same_site,
        path="/",
    )
    response.set_cookie(
        "flingra_csrf",
        csrf_token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite=same_site,
        path="/",
    )


def _clear_session_cookies(response: Response, request: Request) -> None:
    settings = get_app_settings(request)
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="none" if settings.session_cookie_secure else "lax",
    )
    response.delete_cookie(
        "flingra_csrf",
        path="/",
        secure=settings.session_cookie_secure,
        samesite="none" if settings.session_cookie_secure else "lax",
    )


def require_csrf(
    request: Request,
    db: DbSession,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    settings = get_app_settings(request)
    origin = request.headers.get("origin")
    failure_reason = (
        "origin_not_allowed"
        if settings.allowed_origins and (origin is None or origin not in settings.allowed_origins)
        else None
    )

    cookie_token = request.cookies.get("flingra_csrf")
    if not cookie_token or not csrf_header or not re.fullmatch(r"[A-Za-z0-9_-]{20,128}", csrf_header):
        failure_reason = failure_reason or "token_missing_or_malformed"
    elif not hmac.compare_digest(cookie_token, csrf_header):
        failure_reason = failure_reason or "token_mismatch"
    if failure_reason is not None:
        raw_token = request.cookies.get(settings.session_cookie_name)
        account_id = (
            db.execute(
                text(
                    """
                    SELECT account_id FROM sessions
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
            event_type="auth.csrf.denied",
            actor_type="user" if account_id is not None else "anonymous",
            actor_id=str(account_id) if account_id is not None else None,
            subject_account_id=str(account_id) if account_id is not None else None,
            outcome="denied",
            metadata={"reason": failure_reason},
        )
        db.commit()
        raise ApiException("CSRF_FAILED", "Refresh the page and try again.", 403)


def get_authenticated_account(
    request: Request,
    db: DbSession,
) -> AuthenticatedAccount:
    settings = get_app_settings(request)
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise ApiException("UNAUTHENTICATED", "Sign in to continue.", 401)

    result = db.execute(
        text(
            """
            SELECT s.id AS session_id, s.last_active_at, a.id, a.identifier, a.identifier_type,
                   a.email_verified, a.date_of_birth, a.account_state, p.onboarding_complete
            FROM sessions s
            JOIN accounts a ON a.id = s.account_id
            LEFT JOIN profiles p ON p.account_id = a.id
            WHERE s.session_token_hash = :token_hash
              AND s.revoked_at IS NULL
              AND s.expires_at > :now
            """
        ),
        {"token_hash": hash_token(raw_token), "now": _now()},
    ).mappings().first()
    if result is None:
        raise ApiException("UNAUTHENTICATED", "Sign in to continue.", 401)
    if result["account_state"] in {"deletion_requested", "deleted"}:
        raise ApiException("ACCOUNT_DELETION_PENDING", "This account is scheduled for deletion.", 403)
    if result["account_state"] in {"suspended", "banned"}:
        raise ApiException("ACCOUNT_SUSPENDED", "This account is not permitted to sign in.", 403)
    if result["last_active_at"] is None or _as_datetime(result["last_active_at"]) < _now() - timedelta(minutes=1):
        db.execute(
            text("UPDATE sessions SET last_active_at = :now WHERE id = :session_id"),
            {"now": _now(), "session_id": result["session_id"]},
        )
        db.commit()
    if _age_on(result["date_of_birth"], date.today()) < MINIMUM_ACCOUNT_AGE:
        db.execute(
            text("UPDATE sessions SET revoked_at = :revoked_at WHERE id = :session_id"),
            {"revoked_at": _now(), "session_id": result["session_id"]},
        )
        record_audit_event(
            db,
            request,
            event_type="auth.session.age_denied",
            actor_type="user",
            actor_id=str(result["id"]),
            subject_account_id=str(result["id"]),
            outcome="denied",
            metadata={"reason": "minimum_age_not_met"},
        )
        db.commit()
        raise ApiException("INELIGIBLE_AGE", "Flingra is only available to adults 21 and older.", 403)
    return AuthenticatedAccount(result)


CurrentAccount = Annotated[AuthenticatedAccount, Depends(get_authenticated_account)]


def require_identity_verified(
    request: Request,
    account: CurrentAccount,
    db: DbSession,
) -> AuthenticatedAccount:
    verification_status = db.execute(
        text(
            """
            SELECT document_verification
            FROM profiles
            WHERE account_id = :account_id
            """
        ),
        {"account_id": account.account_id},
    ).scalar_one_or_none()
    if verification_status != "verified":
        record_audit_event(
            db,
            request,
            event_type="identity.verification.access_denied",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=account.account_id,
            outcome="denied",
            metadata={"verificationStatus": verification_status or "unverified"},
        )
        db.commit()
        raise ApiException(
            "IDENTITY_VERIFICATION_REQUIRED",
            "Identity verification must be approved before using this feature.",
            403,
        )
    return account


IdentityVerifiedAccount = Annotated[AuthenticatedAccount, Depends(require_identity_verified)]


def _create_session(db: Session, account_id: str, request: Request, response: Response) -> None:
    settings = get_app_settings(request)
    raw_token = generate_token()
    db.execute(
        text(
            """
            INSERT INTO sessions (
                id, account_id, session_token_hash, expires_at, device_label, last_active_at
            )
            VALUES (
                :id, :account_id, :token_hash, :expires_at, :device_label, :last_active_at
            )
            """
        ),
        {
            "id": uuid.uuid4().hex,
            "account_id": account_id,
            "token_hash": hash_token(raw_token),
            "expires_at": _now() + timedelta(hours=settings.session_ttl_hours),
            "device_label": request.headers.get("user-agent", "Unknown device")[:255],
            "last_active_at": _now(),
        },
    )
    _set_session_cookies(response, request, raw_token)


def _session_response(account: AuthenticatedAccount) -> SessionResponse:
    return SessionResponse(
        account_id=account.account_id,
        masked_contact=mask_contact(account["identifier"], account["identifier_type"]),
        stage=_stage(account),
    )


def _send_contact_code(settings: Settings, identifier: str, identifier_type: str, code: str) -> None:
    if identifier_type != "email":
        raise ServiceUnavailable("SMS verification is not configured for phone accounts.")
    send_verification_code(settings, identifier, code)


def _new_verification_code(db: Session, account_id: str) -> str:
    code = generate_verification_code()
    _store_verification_code(db, account_id, code)
    return code


def _store_verification_code(db: Session, account_id: str, code: str) -> None:
    db.execute(
        text("DELETE FROM email_verification_tokens WHERE account_id = :account_id"),
        {"account_id": account_id},
    )
    db.execute(
        text(
            """
            INSERT INTO email_verification_tokens (account_id, token_hash, expires_at, attempt_count)
            VALUES (:account_id, :token_hash, :expires_at, 0)
            """
        ),
        {
            "account_id": account_id,
            "token_hash": hash_token(code),
            "expires_at": _now() + VERIFICATION_LIFETIME,
        },
    )


def _record_rejected_signup(
    db: Session,
    request: Request,
    reason: str,
    *,
    outcome: Literal["denied", "failure"] = "denied",
    subject_account_id: str | None = None,
) -> None:
    record_audit_event(
        db,
        request,
        event_type="auth.signup",
        actor_type="anonymous",
        actor_id=None,
        subject_account_id=subject_account_id,
        outcome=outcome,
        metadata={"reason": reason},
    )
    db.commit()


@router.post("/signup", response_model=StageResponse, status_code=201)
def sign_up(
    body: SignUpRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: SettingsDependency,
) -> StageResponse:
    if not body.accepted_terms:
        _record_rejected_signup(db, request, "terms_not_accepted")
        raise ApiException("TERMS_REQUIRED", "Accept the terms and privacy notice to continue.")

    try:
        normalized, identifier_type, email = _normalize_identifier(body.identifier, body.sex)
    except ApiException as exc:
        _record_rejected_signup(db, request, exc.code)
        raise
    age = _age_on(body.date_of_birth, date.today())
    if age < MINIMUM_ACCOUNT_AGE:
        _record_rejected_signup(db, request, "minimum_age_not_met")
        raise ApiException("INELIGIBLE_AGE", "Flingra is only available to adults 21 and older.")

    referral_code = normalize_referral_code(body.referral_code)

    if identifier_type != "email":
        _record_rejected_signup(db, request, "sms_provider_unavailable", outcome="failure")
        raise ServiceUnavailable("SMS verification is not configured for phone accounts.")

    existing_account_id = db.execute(
        text("SELECT id FROM accounts WHERE identifier = :identifier"),
        {"identifier": normalized},
    ).scalar_one_or_none()
    if existing_account_id is not None:
        _record_rejected_signup(
            db,
            request,
            "account_exists",
            outcome="failure",
            subject_account_id=str(existing_account_id),
        )
        raise ApiException(
            "ACCOUNT_EXISTS",
            "If an account already exists for these details, sign in instead or reset your password.",
            409,
        )

    account_id = uuid.uuid4().hex
    code = generate_verification_code()
    try:
        db.execute(
            text(
                """
                INSERT INTO accounts (
                    id, email, identifier, identifier_type, password_hash, date_of_birth,
                    gender, referred_by_code, terms_version, privacy_version,
                    email_verified, account_state
                )
                VALUES (
                    :id, :email, :identifier, :identifier_type, :password_hash, :date_of_birth,
                    :gender, :referred_by_code, :terms_version, :privacy_version,
                    FALSE, 'needs-verification'
                )
                """
            ),
            {
                "id": account_id,
                "email": email,
                "identifier": normalized,
                "identifier_type": identifier_type,
                "password_hash": hash_password(body.password),
                "date_of_birth": body.date_of_birth,
                "gender": body.sex,
                "referred_by_code": referral_code,
                "terms_version": settings.terms_version,
                "privacy_version": settings.privacy_version,
            },
        )
        db.execute(
            text(
                """
                INSERT INTO profiles (
                    account_id, bio, photos, age_range, interests, identity, document_verification
                )
                VALUES (:account_id, '', '[]', :age_range, '[]', :identity, 'unverified')
                """
            ),
            {
                "account_id": account_id,
                "age_range": _age_range(body.date_of_birth),
                "identity": body.sex,
            },
        )
        ensure_referral_code(db, account_id)
        db.execute(
            text(
                """
                INSERT INTO email_verification_tokens (account_id, token_hash, expires_at, attempt_count)
                VALUES (:account_id, :token_hash, :expires_at, 0)
                """
            ),
            {
                "account_id": account_id,
                "token_hash": hash_token(code),
                "expires_at": _now() + VERIFICATION_LIFETIME,
            },
        )
        _create_session(db, account_id, request, response)
        _send_contact_code(settings, normalized, identifier_type, code)
        record_audit_event(
            db,
            request,
            event_type="auth.signup",
            actor_type="user",
            actor_id=account_id,
            subject_account_id=account_id,
            outcome="success",
            metadata={"identifierType": identifier_type},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiException(
            "ACCOUNT_EXISTS",
            "If an account already exists for these details, sign in instead or reset your password.",
            409,
        ) from exc
    return StageResponse(stage="needs-verification")


@router.post("/login", response_model=SessionResponse)
def sign_in(
    body: SignInRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> SessionResponse:
    identifier = body.identifier.strip().lower()
    if not EMAIL_PATTERN.fullmatch(identifier):
        identifier = PHONE_CLEANUP.sub("", identifier)
    account = db.execute(
        text(
            """
            SELECT id, identifier, identifier_type, password_hash, email_verified, account_state,
                   date_of_birth, login_failed_attempts, locked_until
            FROM accounts
            WHERE identifier = :identifier
            """
        ),
        {"identifier": identifier},
    ).mappings().first()
    if account is None:
        record_audit_event(
            db,
            request,
            event_type="auth.login",
            actor_type="anonymous",
            actor_id=None,
            subject_account_id=None,
            outcome="failure",
            metadata={"reason": "invalid_credentials"},
        )
        db.commit()
        raise ApiException("INVALID_CREDENTIALS", "Invalid email or password.", 401)

    now = _now()
    if account["locked_until"] is not None and _as_datetime(account["locked_until"]) > now:
        record_audit_event(
            db,
            request,
            event_type="auth.login",
            actor_type="anonymous",
            actor_id=None,
            subject_account_id=str(account["id"]),
            outcome="denied",
            metadata={"reason": "account_locked"},
        )
        db.commit()
        raise ApiException("ACCOUNT_LOCKED", "Too many attempts. Try again later or reset your password.", 423)

    if not verify_password(account["password_hash"], body.password):
        failures = int(account["login_failed_attempts"]) + 1
        locked_until = now + LOCKOUT_DURATION if failures >= MAX_LOGIN_ATTEMPTS else None
        db.execute(
            text(
                """
                UPDATE accounts
                SET login_failed_attempts = :failures, locked_until = :locked_until
                WHERE id = :account_id
                """
            ),
            {"failures": failures, "locked_until": locked_until, "account_id": account["id"]},
        )
        record_audit_event(
            db,
            request,
            event_type="auth.login",
            actor_type="anonymous",
            actor_id=None,
            subject_account_id=str(account["id"]),
            outcome="failure",
            metadata={"reason": "invalid_credentials"},
        )
        db.commit()
        if locked_until is not None:
            raise ApiException("ACCOUNT_LOCKED", "Too many attempts. Try again later or reset your password.", 423)
        raise ApiException("INVALID_CREDENTIALS", "Invalid email or password.", 401)

    if _age_on(account["date_of_birth"], date.today()) < MINIMUM_ACCOUNT_AGE:
        record_audit_event(
            db,
            request,
            event_type="auth.login",
            actor_type="anonymous",
            actor_id=None,
            subject_account_id=str(account["id"]),
            outcome="denied",
            metadata={"reason": "minimum_age_not_met"},
        )
        db.commit()
        raise ApiException("INELIGIBLE_AGE", "Flingra is only available to adults 21 and older.", 403)

    if account["account_state"] in {"deletion_requested", "deleted"}:
        record_audit_event(
            db,
            request,
            event_type="auth.login",
            actor_type="anonymous",
            actor_id=None,
            subject_account_id=str(account["id"]),
            outcome="denied",
            metadata={"reason": "account_deletion_pending"},
        )
        db.commit()
        raise ApiException("ACCOUNT_DELETION_PENDING", "This account is scheduled for deletion.", 403)
    if account["account_state"] in {"suspended", "banned"}:
        record_audit_event(
            db,
            request,
            event_type="auth.login",
            actor_type="anonymous",
            actor_id=None,
            subject_account_id=str(account["id"]),
            outcome="denied",
            metadata={"reason": "account_suspended"},
        )
        db.commit()
        raise ApiException("ACCOUNT_SUSPENDED", "This account is not permitted to sign in.", 403)

    db.execute(
        text("UPDATE accounts SET login_failed_attempts = 0, locked_until = NULL WHERE id = :account_id"),
        {"account_id": account["id"]},
    )
    profile = db.execute(
        text("SELECT onboarding_complete FROM profiles WHERE account_id = :account_id"),
        {"account_id": account["id"]},
    ).mappings().first()
    db.commit()

    authenticated = AuthenticatedAccount(
        {
            "id": account["id"],
            "identifier": account["identifier"],
            "identifier_type": account["identifier_type"],
            "email_verified": account["email_verified"],
            "onboarding_complete": bool(profile and profile["onboarding_complete"]),
        }
    )
    _create_session(db, account["id"], request, response)
    record_audit_event(
        db,
        request,
        event_type="auth.login",
        actor_type="user",
        actor_id=str(account["id"]),
        subject_account_id=str(account["id"]),
        outcome="success",
    )
    db.commit()
    return _session_response(authenticated)


@router.post(
    "/2fa/email/request",
    dependencies=[Depends(require_csrf)],
)
def request_two_factor_code(
    request: Request,
    account: CurrentAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> dict[str, str]:
    if account["identifier_type"] != "email":
        raise ApiException("TWO_FACTOR_EMAIL_UNAVAILABLE", "Email two-factor authentication requires an email account.")
    code = generate_verification_code()
    try:
        db.execute(
            text("DELETE FROM two_factor_challenges WHERE account_id = :account_id"),
            {"account_id": account.account_id},
        )
        db.execute(
            text(
                """
                INSERT INTO two_factor_challenges (account_id, code_hash, expires_at, attempt_count)
                VALUES (:account_id, :code_hash, :expires_at, 0)
                """
            ),
            {
                "account_id": account.account_id,
                "code_hash": hash_token(code).hex(),
                "expires_at": _now() + TWO_FACTOR_LIFETIME,
            },
        )
        send_two_factor_code(settings, account["identifier"], code)
        db.commit()
    except ServiceUnavailable:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        database_error_code = (
            exc.orig.args[0]
            if exc.orig.args and isinstance(exc.orig.args[0], int)
            else "unknown"
        )
        logger.error(
            "Email 2FA challenge persistence failed (%s, database error code %s).",
            type(exc).__name__,
            database_error_code,
        )
        raise ServiceUnavailable("Two-factor setup is temporarily unavailable. Check the database migration.") from exc
    return {"status": "sent"}


@router.post(
    "/2fa/email/verify",
    dependencies=[Depends(require_csrf)],
)
def verify_two_factor_code(
    body: TwoFactorCodeRequest,
    account: CurrentAccount,
    db: DbSession,
) -> dict[str, str]:
    normalized_code = re.sub(r"\D", "", body.code)
    challenge = db.execute(
        text(
            """
            SELECT code_hash, expires_at, attempt_count
            FROM two_factor_challenges
            WHERE account_id = :account_id
            """
        ),
        {"account_id": account.account_id},
    ).mappings().first()
    valid = (
        challenge is not None
        and _as_datetime(challenge["expires_at"]) > _now()
        and int(challenge["attempt_count"]) < 5
        and len(normalized_code) == 6
        and hmac.compare_digest(challenge["code_hash"], hash_token(normalized_code).hex())
    )
    if not valid:
        if challenge is not None and int(challenge["attempt_count"]) < 5:
            db.execute(
                text(
                    """
                    UPDATE two_factor_challenges
                    SET attempt_count = attempt_count + 1
                    WHERE account_id = :account_id
                    """
                ),
                {"account_id": account.account_id},
            )
        db.commit()
        raise ApiException("INVALID_CODE", "That code didn't work. Check the digits and try again.")

    db.execute(
        text(
            """
            UPDATE profiles
            SET two_factor_enabled = TRUE, two_factor_method = 'email'
            WHERE account_id = :account_id
            """
        ),
        {"account_id": account.account_id},
    )
    db.execute(
        text("DELETE FROM two_factor_challenges WHERE account_id = :account_id"),
        {"account_id": account.account_id},
    )
    db.commit()
    return {"status": "verified"}


@router.post("/2fa/authenticator/setup", dependencies=[Depends(require_csrf)])
def setup_authenticator(account: CurrentAccount, db: DbSession) -> dict[str, str]:
    existing_secret = db.execute(
        text(
            """
            SELECT totp_secret, two_factor_enabled
            FROM profiles
            WHERE account_id = :account_id
            """
        ),
        {"account_id": account.account_id},
    ).mappings().first()
    secret = str(existing_secret["totp_secret"]) if existing_secret and existing_secret["totp_secret"] else pyotp.random_base32()
    if not existing_secret or not existing_secret["totp_secret"]:
        db.execute(
            text("UPDATE profiles SET totp_secret = :secret WHERE account_id = :account_id"),
            {"secret": secret, "account_id": account.account_id},
        )
    db.commit()
    label = quote(f"Flingra:{account['identifier']}", safe="")
    uri = f"otpauth://totp/{label}?secret={secret}&issuer=Flingra&algorithm=SHA1&digits=6&period=30"
    qr = qrcode.make(uri)
    output = io.BytesIO()
    qr.save(output, format="PNG")
    return {
        "secret": secret,
        "otpauthUri": uri,
        "qrDataUrl": f"data:image/png;base64,{base64.b64encode(output.getvalue()).decode('ascii')}",
    }


@router.post("/2fa/authenticator/verify", dependencies=[Depends(require_csrf)])
def verify_authenticator(body: TwoFactorCodeRequest, account: CurrentAccount, db: DbSession) -> dict[str, str]:
    secret = db.execute(
        text("SELECT totp_secret FROM profiles WHERE account_id = :account_id"),
        {"account_id": account.account_id},
    ).scalar_one_or_none()
    code = re.sub(r"\D", "", body.code)
    if len(code) != 6 or not secret or not pyotp.TOTP(secret).verify(code, valid_window=2):
        raise ApiException("INVALID_CODE", "That authenticator code is invalid or expired.")
    db.execute(
        text(
            """
            UPDATE profiles
            SET two_factor_enabled = TRUE, two_factor_method = 'authenticator'
            WHERE account_id = :account_id
            """
        ),
        {"account_id": account.account_id},
    )
    db.commit()
    return {"status": "verified"}


@router.get("/oauth/google/config")
def google_auth_config(settings: SettingsDependency) -> dict[str, str | None]:
    return {"clientId": settings.google_client_id}


@router.post("/oauth/google", response_model=SessionResponse)
def google_auth(
    body: GoogleAuthRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: SettingsDependency,
) -> SessionResponse:
    if not settings.google_client_id:
        raise ServiceUnavailable("Google sign-in is not configured.")

    origin = request.headers.get("origin")
    if settings.allowed_origins and (origin is None or origin not in settings.allowed_origins):
        record_audit_event(
            db,
            request,
            event_type="auth.google_login",
            actor_type="anonymous",
            actor_id=None,
            subject_account_id=None,
            outcome="denied",
            metadata={"reason": "origin_not_allowed"},
        )
        db.commit()
        raise ApiException("GOOGLE_LOGIN_DENIED", "Google sign-in could not be completed.", 403)

    try:
        claims = verify_oauth2_token(
            body.credential,
            GoogleRequest(),
            settings.google_client_id,
        )
    except ValueError as exc:
        record_audit_event(
            db,
            request,
            event_type="auth.google_login",
            actor_type="anonymous",
            actor_id=None,
            subject_account_id=None,
            outcome="failure",
            metadata={"reason": "invalid_google_credential"},
        )
        db.commit()
        raise ApiException("INVALID_GOOGLE_CREDENTIAL", "Google sign-in could not be verified.", 401) from exc
    except GoogleAuthError as exc:
        logger.error("Google token verification is temporarily unavailable.")
        raise ServiceUnavailable("Google sign-in is temporarily unavailable.") from exc

    token_nonce = claims.get("nonce")
    if (
        not isinstance(token_nonce, str)
        or not hmac.compare_digest(token_nonce, body.nonce)
        or claims.get("email_verified") is not True
    ):
        record_audit_event(
            db,
            request,
            event_type="auth.google_login",
            actor_type="anonymous",
            actor_id=None,
            subject_account_id=None,
            outcome="failure",
            metadata={"reason": "google_claims_rejected"},
        )
        db.commit()
        raise ApiException("INVALID_GOOGLE_CREDENTIAL", "Google sign-in could not be verified.", 401)

    google_sub = claims.get("sub")
    google_email = claims.get("email")
    if not isinstance(google_sub, str) or not google_sub or not isinstance(google_email, str):
        raise ApiException("INVALID_GOOGLE_CREDENTIAL", "Google sign-in could not be verified.", 401)
    normalized_email = google_email.strip().lower()
    if not EMAIL_PATTERN.fullmatch(normalized_email):
        raise ApiException("INVALID_GOOGLE_CREDENTIAL", "Google sign-in could not be verified.", 401)

    account = db.execute(
        text(
            """
            SELECT id, email, identifier, identifier_type, email_verified, account_state,
                   google_sub, login_failed_attempts, locked_until, date_of_birth
            FROM accounts
            WHERE google_sub = :google_sub
            """
        ),
        {"google_sub": google_sub},
    ).mappings().first()
    if account is None:
        account = db.execute(
            text(
                """
                SELECT id, email, identifier, identifier_type, email_verified, account_state,
                       google_sub, login_failed_attempts, locked_until, date_of_birth
                FROM accounts
                WHERE email = :email
                """
            ),
            {"email": normalized_email},
        ).mappings().first()

    if account is not None:
        if account["account_state"] in {"deletion_requested", "deleted"}:
            raise ApiException("ACCOUNT_DELETION_PENDING", "This account is scheduled for deletion.", 403)
        if account["account_state"] in {"suspended", "banned"}:
            raise ApiException("ACCOUNT_SUSPENDED", "This account is not permitted to sign in.", 403)
        if account["google_sub"] not in (None, google_sub):
            raise ApiException(
                "GOOGLE_ACCOUNT_LINKED_ELSEWHERE",
                "This account is linked to a different Google account.",
                409,
            )
        if account["locked_until"] is not None and _as_datetime(account["locked_until"]) > _now():
            record_audit_event(
                db,
                request,
                event_type="auth.google_login",
                actor_type="anonymous",
                actor_id=None,
                subject_account_id=str(account["id"]),
                outcome="denied",
                metadata={"reason": "account_locked"},
            )
            db.commit()
            raise ApiException(
                "ACCOUNT_LOCKED",
                "Too many attempts. Try again later or reset your password.",
                423,
            )

        if _age_on(account["date_of_birth"], date.today()) < MINIMUM_ACCOUNT_AGE:
            record_audit_event(
                db,
                request,
                event_type="auth.google_login",
                actor_type="anonymous",
                actor_id=None,
                subject_account_id=str(account["id"]),
                outcome="denied",
                metadata={"reason": "minimum_age_not_met"},
            )
            db.commit()
            raise ApiException(
                "INELIGIBLE_AGE",
                "Flingra is only available to adults 21 and older.",
                403,
            )

        if account["google_sub"] is None or not account["email_verified"]:
            db.execute(
                text(
                    """
                    UPDATE accounts
                    SET google_sub = :google_sub,
                        email_verified = TRUE,
                        account_state = CASE
                            WHEN account_state = 'needs-verification' THEN 'needs-onboarding'
                            ELSE account_state
                        END,
                        login_failed_attempts = 0,
                        locked_until = NULL
                    WHERE id = :account_id
                    """
                ),
                {"google_sub": google_sub, "account_id": account["id"]},
            )
            db.execute(
                text("DELETE FROM email_verification_tokens WHERE account_id = :account_id"),
                {"account_id": account["id"]},
            )
        profile = db.execute(
            text("SELECT onboarding_complete FROM profiles WHERE account_id = :account_id"),
            {"account_id": account["id"]},
        ).mappings().first()
        authenticated = AuthenticatedAccount(
            {
                "id": account["id"],
                "identifier": account["identifier"],
                "identifier_type": account["identifier_type"],
                "email_verified": True,
                "onboarding_complete": bool(profile and profile["onboarding_complete"]),
            }
        )
        _create_session(db, str(account["id"]), request, response)
        record_audit_event(
            db,
            request,
            event_type="auth.google_login",
            actor_type="user",
            actor_id=str(account["id"]),
            subject_account_id=str(account["id"]),
            outcome="success",
        )
        db.commit()
        return _session_response(authenticated)

    if body.sex is None or body.date_of_birth is None:
        raise ApiException(
            "GOOGLE_SIGNUP_REQUIRED",
            "Choose your account type and date of birth to finish creating your account.",
            409,
        )
    if not body.accepted_terms:
        raise ApiException("TERMS_REQUIRED", "Accept the terms and privacy notice to continue.")
    if _age_on(body.date_of_birth, date.today()) < MINIMUM_ACCOUNT_AGE:
        raise ApiException("INELIGIBLE_AGE", "Flingra is only available to adults 21 and older.")

    referral_code = normalize_referral_code(body.referral_code)
    account_id = uuid.uuid4().hex
    try:
        db.execute(
            text(
                """
                INSERT INTO accounts (
                    id, email, identifier, identifier_type, password_hash, date_of_birth,
                    gender, referred_by_code, terms_version, privacy_version,
                    email_verified, account_state, google_sub
                )
                VALUES (
                    :id, :email, :identifier, 'email', :password_hash, :date_of_birth,
                    :gender, :referred_by_code, :terms_version, :privacy_version,
                    TRUE, 'needs-onboarding', :google_sub
                )
                """
            ),
            {
                "id": account_id,
                "email": normalized_email,
                "identifier": normalized_email,
                "password_hash": hash_password(generate_token()),
                "date_of_birth": body.date_of_birth,
                "gender": body.sex,
                "referred_by_code": referral_code,
                "terms_version": settings.terms_version,
                "privacy_version": settings.privacy_version,
                "google_sub": google_sub,
            },
        )
        google_name = claims.get("name")
        if not isinstance(google_name, str) or not google_name.strip():
            google_name = claims.get("given_name")
        display_name = google_name.strip()[:80] if isinstance(google_name, str) and google_name.strip() else ""
        db.execute(
            text(
                """
                INSERT INTO profiles (
                    account_id, display_name, bio, photos, age_range, interests, identity,
                    document_verification
                )
                VALUES (:account_id, :display_name, '', '[]', :age_range, '[]', :identity, 'unverified')
                """
            ),
            {
                "account_id": account_id,
                "display_name": display_name,
                "age_range": _age_range(body.date_of_birth),
                "identity": body.sex,
            },
        )
        ensure_referral_code(db, account_id)
        authenticated = AuthenticatedAccount(
            {
                "id": account_id,
                "identifier": normalized_email,
                "identifier_type": "email",
                "email_verified": True,
                "onboarding_complete": False,
            }
        )
        _create_session(db, account_id, request, response)
        record_audit_event(
            db,
            request,
            event_type="auth.google_signup",
            actor_type="user",
            actor_id=account_id,
            subject_account_id=account_id,
            outcome="success",
            metadata={"identifierType": "email"},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiException(
            "ACCOUNT_EXISTS",
            "If an account already exists for these details, sign in instead or reset your password.",
            409,
        ) from exc
    return _session_response(authenticated)


@router.post(
    "/verify-contact",
    response_model=StageResponse,
    dependencies=[Depends(require_csrf)],
)
def verify_contact(
    body: VerifyContactRequest,
    request: Request,
    account: CurrentAccount,
    db: DbSession,
) -> StageResponse:
    if account.stage != "needs-verification":
        raise ApiException("INVALID_CODE", "This account does not need contact verification.")
    normalized_code = re.sub(r"\D", "", body.code)
    token = db.execute(
        text(
            """
            SELECT token_hash, expires_at, attempt_count
            FROM email_verification_tokens
            WHERE account_id = :account_id
            """
        ),
        {"account_id": account.account_id},
    ).mappings().first()
    if (
        token is None
        or _as_datetime(token["expires_at"]) <= _now()
        or int(token["attempt_count"]) >= 5
        or len(normalized_code) != 6
        or not hmac.compare_digest(token["token_hash"], hash_token(normalized_code))
    ):
        record_audit_event(
            db,
            request,
            event_type="auth.contact_verification",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=account.account_id,
            outcome="failure",
            metadata={"reason": "invalid_or_expired_code"},
        )
        if token is not None and int(token["attempt_count"]) < 5:
            db.execute(
                text(
                    """
                    UPDATE email_verification_tokens
                    SET attempt_count = attempt_count + 1
                    WHERE account_id = :account_id
                    """
                ),
                {"account_id": account.account_id},
            )
        db.commit()
        raise ApiException("INVALID_CODE", "That code didn't work. Check the digits and try again.")

    db.execute(
        text(
            """
            UPDATE accounts
            SET email_verified = TRUE, account_state = 'needs-onboarding'
            WHERE id = :account_id
            """
        ),
        {"account_id": account.account_id},
    )
    ensure_referral_code(db, account.account_id)
    db.execute(
        text("DELETE FROM email_verification_tokens WHERE account_id = :account_id"),
        {"account_id": account.account_id},
    )
    record_audit_event(
        db,
        request,
        event_type="auth.contact_verification",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
    )
    db.commit()
    return StageResponse(stage="needs-onboarding")


@router.post("/resend-code", status_code=204, dependencies=[Depends(require_csrf)])
def resend_code(
    request: Request,
    account: CurrentAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> Response:
    if account.stage != "needs-verification":
        record_audit_event(
            db,
            request,
            event_type="auth.verification_code_resend",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=account.account_id,
            outcome="denied",
            metadata={"reason": "verification_not_required"},
        )
        db.commit()
        return Response(status_code=204)
    existing = db.execute(
        text("SELECT created_at FROM email_verification_tokens WHERE account_id = :account_id"),
        {"account_id": account.account_id},
    ).first()
    if existing is not None and _as_datetime(existing[0]) > _now() - timedelta(seconds=60):
        record_audit_event(
            db,
            request,
            event_type="auth.verification_code_resend",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=account.account_id,
            outcome="denied",
            metadata={"reason": "cooldown"},
        )
        db.commit()
        raise ApiException("CODE_RESEND_TOO_SOON", "Wait a minute before requesting another code.", 429)

    code = generate_verification_code()
    try:
        _send_contact_code(settings, account["identifier"], account["identifier_type"], code)
    except ServiceUnavailable:
        db.rollback()
        raise
    _store_verification_code(db, account.account_id, code)
    record_audit_event(
        db,
        request,
        event_type="auth.verification_code_resend",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
    )
    db.commit()
    return Response(status_code=204)


@router.post("/password/forgot", status_code=204)
def request_password_reset(
    body: PasswordResetRequest,
    request: Request,
    db: DbSession,
    settings: SettingsDependency,
) -> Response:
    identifier = body.identifier.strip().lower()
    account = db.execute(
        text("SELECT id, email FROM accounts WHERE identifier = :identifier"),
        {"identifier": identifier},
    ).mappings().first()
    reset_email: tuple[str, str] | None = None
    if account is not None and account["email"]:
        token = generate_token()
        db.execute(
            text("DELETE FROM password_reset_tokens WHERE account_id = :account_id"),
            {"account_id": account["id"]},
        )
        db.execute(
            text(
                """
                INSERT INTO password_reset_tokens (account_id, token_hash, expires_at)
                VALUES (:account_id, :token_hash, :expires_at)
                """
            ),
            {
                "account_id": account["id"],
                "token_hash": hash_token(token),
                "expires_at": _now() + RESET_LIFETIME,
            },
        )
        reset_email = account["email"], token
    record_audit_event(
        db,
        request,
        event_type="auth.password_reset_requested",
        actor_type="anonymous",
        actor_id=None,
        subject_account_id=str(account["id"]) if account is not None else None,
        outcome="success",
    )
    db.commit()
    if reset_email is not None:
        try:
            send_password_reset(settings, *reset_email)
        except ServiceUnavailable as exc:
            logger.error("Password-reset email delivery failed: %s", exc.message)
    return Response(status_code=204)


@router.post("/password/reset", status_code=204)
def reset_password(
    body: PasswordResetConfirmRequest,
    request: Request,
    db: DbSession,
) -> Response:
    reset = db.execute(
        text(
            """
            SELECT account_id, expires_at
            FROM password_reset_tokens
            WHERE token_hash = :token_hash
            """
        ),
        {"token_hash": hash_token(body.token)},
    ).mappings().first()
    if reset is None or _as_datetime(reset["expires_at"]) <= _now():
        record_audit_event(
            db,
            request,
            event_type="auth.password_reset_completed",
            actor_type="anonymous",
            actor_id=None,
            subject_account_id=str(reset["account_id"]) if reset is not None else None,
            outcome="failure",
            metadata={"reason": "invalid_or_expired_token"},
        )
        db.commit()
        raise ApiException("TOKEN_EXPIRED", "This reset link has expired. Request a new one.")

    db.execute(
        text(
            """
            UPDATE accounts
            SET password_hash = :password_hash, login_failed_attempts = 0, locked_until = NULL
            WHERE id = :account_id
            """
        ),
        {"password_hash": hash_password(body.password), "account_id": reset["account_id"]},
    )
    db.execute(
        text("UPDATE sessions SET revoked_at = :now WHERE account_id = :account_id AND revoked_at IS NULL"),
        {"now": _now(), "account_id": reset["account_id"]},
    )
    db.execute(
        text("DELETE FROM password_reset_tokens WHERE account_id = :account_id"),
        {"account_id": reset["account_id"]},
    )
    record_audit_event(
        db,
        request,
        event_type="auth.password_reset_completed",
        actor_type="anonymous",
        actor_id=None,
        subject_account_id=str(reset["account_id"]),
        outcome="success",
    )
    db.commit()
    return Response(status_code=204)


@router.get("/session", response_model=SessionResponse | None)
def current_session(request: Request, response: Response, db: DbSession) -> SessionResponse | None:
    settings = get_app_settings(request)
    csrf_token = request.cookies.get("flingra_csrf")
    if csrf_token:
        response.headers["X-CSRF-Token"] = csrf_token
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        return None
    row = db.execute(
        text(
            """
            SELECT a.id, a.identifier, a.identifier_type, a.email_verified,
                   p.onboarding_complete
            FROM sessions s
            JOIN accounts a ON a.id = s.account_id
            LEFT JOIN profiles p ON p.account_id = a.id
            WHERE s.session_token_hash = :token_hash
              AND s.revoked_at IS NULL
              AND s.expires_at > :now
            """
        ),
        {"token_hash": hash_token(raw_token), "now": _now()},
    ).mappings().first()
    if row is None:
        return None
    return _session_response(AuthenticatedAccount(row))


@router.post("/logout", status_code=204, dependencies=[Depends(require_csrf)])
def sign_out(
    request: Request,
    response: Response,
    db: DbSession,
) -> Response:
    settings = get_app_settings(request)
    raw_token = request.cookies.get(settings.session_cookie_name)
    if raw_token:
        account_id = db.execute(
            text(
                """
                SELECT account_id FROM sessions
                WHERE session_token_hash = :token_hash AND revoked_at IS NULL
                """
            ),
            {"token_hash": hash_token(raw_token)},
        ).scalar_one_or_none()
        db.execute(
            text(
                """
                UPDATE sessions SET revoked_at = :now
                WHERE session_token_hash = :token_hash AND revoked_at IS NULL
                """
            ),
            {"now": _now(), "token_hash": hash_token(raw_token)},
        )
        if account_id is not None:
            record_audit_event(
                db,
                request,
                event_type="auth.logout",
                actor_type="user",
                actor_id=str(account_id),
                subject_account_id=str(account_id),
                outcome="success",
            )
        db.commit()
    _clear_session_cookies(response, request)
    response.status_code = 204
    return response


@router.post("/onboarding/complete", response_model=SessionResponse, dependencies=[Depends(require_csrf)])
def complete_onboarding(
    request: Request,
    account: CurrentAccount,
    db: DbSession,
) -> SessionResponse:
    if not account["email_verified"]:
        raise ApiException("CONTACT_NOT_VERIFIED", "Verify your contact before completing onboarding.", 403)
    profile = db.execute(
        text("SELECT display_name, photos FROM profiles WHERE account_id = :account_id"),
        {"account_id": account.account_id},
    ).mappings().first()
    if profile is None:
        raise ApiException("NO_PROFILE", "Finish onboarding to create your profile.", 404)
    photos = json.loads(profile["photos"]) if isinstance(profile["photos"], str) else profile["photos"]
    if not profile["display_name"].strip() or not photos:
        raise ApiException("ONBOARDING_INCOMPLETE", "Add a display name and profile photo to continue.")
    db.execute(
        text("UPDATE profiles SET onboarding_complete = TRUE WHERE account_id = :account_id"),
        {"account_id": account.account_id},
    )
    record_audit_event(
        db,
        request,
        event_type="profile.onboarding_completed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
    )
    db.commit()
    completed = AuthenticatedAccount({**account, "onboarding_complete": True})
    return _session_response(completed)
