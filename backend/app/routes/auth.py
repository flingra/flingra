import hmac
import json
import logging
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.dependencies import db_session
from app.errors import ApiException, ServiceUnavailable
from app.notifications import send_password_reset, send_verification_code
from app.schemas import (
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    SessionResponse,
    SignInRequest,
    SignUpRequest,
    StageResponse,
    VerifyContactRequest,
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


def _age_on(birth_date: date, today: date) -> int:
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
    response.set_cookie(
        settings.session_cookie_name,
        raw_token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "flingra_csrf",
        csrf_token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookies(response: Response, request: Request) -> None:
    settings = get_app_settings(request)
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie("flingra_csrf", path="/", secure=settings.session_cookie_secure, samesite="lax")


def require_csrf(
    request: Request,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    settings = get_app_settings(request)
    origin = request.headers.get("origin")
    if settings.allowed_origins and (
        origin is None or origin not in settings.allowed_origins
    ):
        raise ApiException("CSRF_FAILED", "Refresh the page and try again.", 403)

    cookie_token = request.cookies.get("flingra_csrf")
    if not cookie_token or not csrf_header or not re.fullmatch(r"[A-Za-z0-9_-]{20,128}", csrf_header):
        raise ApiException("CSRF_FAILED", "Refresh the page and try again.", 403)
    if not hmac.compare_digest(cookie_token, csrf_header):
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
    if result is None:
        raise ApiException("UNAUTHENTICATED", "Sign in to continue.", 401)
    return AuthenticatedAccount(result)


CurrentAccount = Annotated[AuthenticatedAccount, Depends(get_authenticated_account)]


def _create_session(db: Session, account_id: str, request: Request, response: Response) -> None:
    settings = get_app_settings(request)
    raw_token = generate_token()
    db.execute(
        text(
            """
            INSERT INTO sessions (id, account_id, session_token_hash, expires_at)
            VALUES (:id, :account_id, :token_hash, :expires_at)
            """
        ),
        {
            "id": uuid.uuid4().hex,
            "account_id": account_id,
            "token_hash": hash_token(raw_token),
            "expires_at": _now() + timedelta(hours=settings.session_ttl_hours),
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
    return code


@router.post("/signup", response_model=StageResponse, status_code=201)
def sign_up(
    body: SignUpRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: SettingsDependency,
) -> StageResponse:
    if not body.accepted_terms:
        raise ApiException("TERMS_REQUIRED", "Accept the terms and privacy notice to continue.")

    normalized, identifier_type, email = _normalize_identifier(body.identifier, body.sex)
    age = _age_on(body.date_of_birth, date.today())
    minimum_age = 21 if body.sex == "woman" else 18
    if age < minimum_age:
        message = (
            "Flingra requires female accounts to be 21 or older."
            if body.sex == "woman"
            else "Flingra is only available to adults 18 and older."
        )
        raise ApiException("INELIGIBLE_AGE", message)

    if identifier_type != "email":
        raise ServiceUnavailable("SMS verification is not configured for phone accounts.")

    if db.execute(
        text("SELECT 1 FROM accounts WHERE identifier = :identifier"),
        {"identifier": normalized},
    ).first():
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
                "referred_by_code": body.referral_code,
                "terms_version": settings.terms_version,
                "privacy_version": settings.privacy_version,
            },
        )
        db.execute(
            text(
                """
                INSERT INTO profiles (account_id, bio, photos, age_range, interests, identity)
                VALUES (:account_id, '', '[]', :age_range, '[]', :identity)
                """
            ),
            {
                "account_id": account_id,
                "age_range": _age_range(body.date_of_birth),
                "identity": body.sex,
            },
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
        _create_session(db, account_id, request, response)
        _send_contact_code(settings, normalized, identifier_type, code)
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
            SELECT id, identifier, identifier_type, password_hash, email_verified,
                   login_failed_attempts, locked_until
            FROM accounts
            WHERE identifier = :identifier
            """
        ),
        {"identifier": identifier},
    ).mappings().first()
    if account is None:
        raise ApiException("INVALID_CREDENTIALS", "That email/password combination doesn't match our records.", 401)

    now = _now()
    if account["locked_until"] is not None and _as_datetime(account["locked_until"]) > now:
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
        db.commit()
        if locked_until is not None:
            raise ApiException("ACCOUNT_LOCKED", "Too many attempts. Try again later or reset your password.", 423)
        raise ApiException("INVALID_CREDENTIALS", "That email/password combination doesn't match our records.", 401)

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
    db.commit()
    return _session_response(authenticated)


@router.post(
    "/verify-contact",
    response_model=StageResponse,
    dependencies=[Depends(require_csrf)],
)
def verify_contact(
    body: VerifyContactRequest,
    account: CurrentAccount,
    db: DbSession,
) -> StageResponse:
    if account.stage != "needs-verification":
        raise ApiException("INVALID_CODE", "This account does not need contact verification.")
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
        or not hmac.compare_digest(token["token_hash"], hash_token(body.code))
    ):
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
    db.execute(
        text("DELETE FROM email_verification_tokens WHERE account_id = :account_id"),
        {"account_id": account.account_id},
    )
    db.commit()
    return StageResponse(stage="needs-onboarding")


@router.post("/resend-code", status_code=204, dependencies=[Depends(require_csrf)])
def resend_code(account: CurrentAccount, db: DbSession, settings: SettingsDependency) -> Response:
    if account.stage != "needs-verification":
        return Response(status_code=204)
    existing = db.execute(
        text("SELECT created_at FROM email_verification_tokens WHERE account_id = :account_id"),
        {"account_id": account.account_id},
    ).first()
    if existing is not None and _as_datetime(existing[0]) > _now() - timedelta(seconds=60):
        raise ApiException("CODE_RESEND_TOO_SOON", "Wait a minute before requesting another code.", 429)

    code = _new_verification_code(db, account.account_id)
    _send_contact_code(settings, account["identifier"], account["identifier_type"], code)
    db.commit()
    return Response(status_code=204)


@router.post("/password/forgot", status_code=204)
def request_password_reset(
    body: PasswordResetRequest,
    db: DbSession,
    settings: SettingsDependency,
) -> Response:
    identifier = body.identifier.strip().lower()
    account = db.execute(
        text("SELECT id, email FROM accounts WHERE identifier = :identifier"),
        {"identifier": identifier},
    ).mappings().first()
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
        db.commit()
        try:
            send_password_reset(settings, account["email"], token)
        except ServiceUnavailable as exc:
            logger.error("Password-reset email delivery failed: %s", exc.message)
    return Response(status_code=204)


@router.post("/password/reset", status_code=204)
def reset_password(body: PasswordResetConfirmRequest, db: DbSession) -> Response:
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
    db.commit()
    return Response(status_code=204)


@router.get("/session", response_model=SessionResponse | None)
def current_session(request: Request, db: DbSession) -> SessionResponse | None:
    settings = get_app_settings(request)
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
        db.execute(
            text(
                """
                UPDATE sessions SET revoked_at = :now
                WHERE session_token_hash = :token_hash AND revoked_at IS NULL
                """
            ),
            {"now": _now(), "token_hash": hash_token(raw_token)},
        )
        db.commit()
    _clear_session_cookies(response, request)
    response.status_code = 204
    return response


@router.post("/onboarding/complete", response_model=SessionResponse, dependencies=[Depends(require_csrf)])
def complete_onboarding(
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
    db.commit()
    completed = AuthenticatedAccount({**account, "onboarding_complete": True})
    return _session_response(completed)
