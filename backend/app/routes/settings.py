import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.dependencies import db_session
from app.errors import ApiException
from app.feature_schemas import (
    DeviceSessionResponse,
    PasswordChangeRequest,
    PrivacyRequestResponse,
    PrivacyRequestStatusResponse,
)
from app.routes.auth import (
    CurrentAccount,
    _clear_session_cookies,
    require_csrf,
)
from app.security import hash_password, verify_password

router = APIRouter(prefix="/settings", tags=["settings"])
DbSession = Annotated[Session, Depends(db_session)]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@router.post("/password", status_code=204, dependencies=[Depends(require_csrf)])
def change_password(
    body: PasswordChangeRequest,
    request: Request,
    account: CurrentAccount,
    db: DbSession,
) -> None:
    current_hash = db.execute(
        text("SELECT password_hash FROM accounts WHERE id = :account_id"),
        {"account_id": account.account_id},
    ).scalar_one_or_none()
    if current_hash is None or not verify_password(current_hash, body.current_password):
        record_audit_event(
            db,
            request,
            event_type="settings.password_changed",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=account.account_id,
            outcome="failure",
            metadata={"reason": "wrong_current_password"},
        )
        db.commit()
        raise ApiException("WRONG_PASSWORD", "Your current password is incorrect.", 403)
    if body.current_password == body.new_password:
        raise ApiException("PASSWORD_UNCHANGED", "Choose a password different from your current one.")
    db.execute(
        text("UPDATE accounts SET password_hash = :password_hash WHERE id = :account_id"),
        {"password_hash": hash_password(body.new_password), "account_id": account.account_id},
    )
    db.execute(
        text(
            """
            UPDATE sessions
            SET revoked_at = :revoked_at
            WHERE account_id = :account_id AND id != :current_session_id AND revoked_at IS NULL
            """
        ),
        {
            "revoked_at": _now(),
            "account_id": account.account_id,
            "current_session_id": account["session_id"],
        },
    )
    record_audit_event(
        db,
        request,
        event_type="settings.password_changed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
    )
    db.commit()


@router.get("/sessions", response_model=list[DeviceSessionResponse])
def list_sessions(
    request: Request,
    account: CurrentAccount,
    db: DbSession,
) -> list[DeviceSessionResponse]:
    rows = db.execute(
        text(
            """
            SELECT id, device_label, last_active_at, created_at
            FROM sessions
            WHERE account_id = :account_id
              AND revoked_at IS NULL
              AND expires_at > :now
            ORDER BY COALESCE(last_active_at, created_at) DESC, id
            """
        ),
        {"account_id": account.account_id, "now": _now()},
    ).mappings()
    sessions = [
        DeviceSessionResponse(
            id=str(row["id"]),
            device=row["device_label"] or "Unknown device",
            last_active=str(row["last_active_at"] or row["created_at"]),
            current=str(row["id"]) == str(account["session_id"]),
        )
        for row in rows
    ]
    record_audit_event(
        db,
        request,
        event_type="settings.sessions_viewed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
    )
    db.commit()
    return sessions


@router.delete(
    "/sessions/{session_id}",
    status_code=204,
    dependencies=[Depends(require_csrf)],
)
def revoke_session(
    session_id: str,
    request: Request,
    response: Response,
    account: CurrentAccount,
    db: DbSession,
) -> None:
    result = db.execute(
        text(
            """
            UPDATE sessions
            SET revoked_at = :revoked_at
            WHERE id = :session_id AND account_id = :account_id AND revoked_at IS NULL
            """
        ),
        {
            "revoked_at": _now(),
            "session_id": session_id,
            "account_id": account.account_id,
        },
    )
    if not result.rowcount:
        raise ApiException("SESSION_NOT_FOUND", "This session is unavailable.", 404)
    record_audit_event(
        db,
        request,
        event_type="settings.session_revoked",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
        metadata={"sessionId": session_id},
    )
    db.commit()
    if str(session_id) == str(account["session_id"]):
        _clear_session_cookies(response, request)


def _queue_privacy_request(
    request: Request,
    account: CurrentAccount,
    db: Session,
    request_type: str,
) -> PrivacyRequestResponse:
    existing = db.execute(
        text(
            """
            SELECT id
            FROM privacy_requests
            WHERE account_id = :account_id AND request_type = :request_type
              AND status IN ('queued', 'processing') AND created_at >= :since
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {
            "account_id": account.account_id,
            "request_type": request_type,
            "since": _now() - timedelta(days=1),
        },
    ).scalar_one_or_none()
    if existing is not None:
        return PrivacyRequestResponse(request_id=str(existing))

    request_id = uuid.uuid4().hex
    db.execute(
        text(
            """
            INSERT INTO privacy_requests (id, account_id, request_type, status, created_at)
            VALUES (:id, :account_id, :request_type, 'queued', :created_at)
            """
        ),
        {
            "id": request_id,
            "account_id": account.account_id,
            "request_type": request_type,
            "created_at": _now(),
        },
    )
    record_audit_event(
        db,
        request,
        event_type=f"privacy.{request_type}_requested",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
    )
    return PrivacyRequestResponse(request_id=request_id)


@router.post(
    "/data-export",
    response_model=PrivacyRequestResponse,
    status_code=202,
    dependencies=[Depends(require_csrf)],
)
def request_data_export(
    request: Request,
    account: CurrentAccount,
    db: DbSession,
) -> PrivacyRequestResponse:
    result = _queue_privacy_request(request, account, db, "data_export")
    db.commit()
    return result


@router.get(
    "/data-export/{request_id}",
    response_model=PrivacyRequestStatusResponse,
)
def get_data_export(
    request_id: str,
    account: CurrentAccount,
    db: DbSession,
) -> PrivacyRequestStatusResponse:
    row = db.execute(
        text(
            """
            SELECT id, status, result_json
            FROM privacy_requests
            WHERE id = :request_id AND account_id = :account_id AND request_type = 'data_export'
            """
        ),
        {"request_id": request_id, "account_id": account.account_id},
    ).mappings().first()
    if row is None:
        raise ApiException("PRIVACY_REQUEST_NOT_FOUND", "This privacy request is unavailable.", 404)
    result = json.loads(row["result_json"]) if row["result_json"] else None
    return PrivacyRequestStatusResponse(
        request_id=str(row["id"]),
        status=row["status"],
        result=result,
    )


@router.post(
    "/account/delete",
    response_model=PrivacyRequestResponse,
    status_code=202,
    dependencies=[Depends(require_csrf)],
)
def request_account_deletion(
    request: Request,
    account: CurrentAccount,
    db: DbSession,
) -> PrivacyRequestResponse:
    result = _queue_privacy_request(request, account, db, "account_deletion")
    db.execute(
        text("UPDATE accounts SET account_state = 'deletion_requested' WHERE id = :account_id"),
        {"account_id": account.account_id},
    )
    db.execute(
        text(
            """
            UPDATE sessions SET revoked_at = :revoked_at
            WHERE account_id = :account_id AND revoked_at IS NULL
            """
        ),
        {"revoked_at": _now(), "account_id": account.account_id},
    )
    record_audit_event(
        db,
        request,
        event_type="privacy.account_deletion_queued",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
        metadata={"requestId": result.request_id},
    )
    db.commit()
    return result
