import json
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.dependencies import db_session
from app.errors import ApiException, ServiceUnavailable
from app.feature_schemas import (
    BlockCreateRequest,
    BlockedAccountResponse,
    EmergencyContactRequest,
    EmergencyContactResponse,
    ReportCreateRequest,
    SafetyCheckInCreateRequest,
    SafetyCheckInResponse,
)
from app.routes.auth import CurrentAccount, require_csrf
from app.routes.auth import get_app_settings
from app.config import Settings
from app.termii import send_sms

router = APIRouter(prefix="/safety", tags=["safety"])
DbSession = Annotated[Session, Depends(db_session)]
SettingsDependency = Annotated[Settings, Depends(get_app_settings)]
PHONE_PATTERN = re.compile(r"^[+]?[0-9][0-9 ()-]{5,30}$")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _target_profile(db: Session, target_id: str, actor_id: str) -> dict[str, Any]:
    if target_id == actor_id:
        raise ApiException("INVALID_TARGET", "You cannot report or block your own account.", 400)
    row = db.execute(
        text(
            """
            SELECT a.id, p.display_name, p.photos
            FROM accounts a
            JOIN profiles p ON p.account_id = a.id
            WHERE a.id = :target_id
            """
        ),
        {"target_id": target_id},
    ).mappings().first()
    if row is None:
        raise ApiException("PROFILE_NOT_FOUND", "This member is unavailable.", 404)
    return dict(row)


def _create_block(db: Session, request: Request, actor_id: str, target_id: str) -> None:
    existing = db.execute(
        text(
            """
            SELECT 1 FROM safety_blocks
            WHERE blocker_id = :actor_id AND blocked_id = :target_id
            """
        ),
        {"actor_id": actor_id, "target_id": target_id},
    ).first()
    if existing is not None:
        return
    created_at = _now()
    insert_statement = """
            INSERT INTO safety_blocks (blocker_id, blocked_id, created_at)
            VALUES (:actor_id, :target_id, :created_at)
    """
    if db.get_bind().dialect.name == "sqlite":
        insert_statement = insert_statement.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)
    else:
        insert_statement = insert_statement.replace("INSERT INTO", "INSERT IGNORE INTO", 1)
    inserted = db.execute(
        text(insert_statement),
        {"actor_id": actor_id, "target_id": target_id, "created_at": created_at},
    )
    if inserted.rowcount != 1:
        return
    review_id = uuid.uuid4().hex
    db.execute(
        text(
            """
            INSERT INTO moderation_review_requests (
                id, requester_id, target_account_id, source_type, source_id,
                reason, status, created_at
            )
            VALUES (
                :id, :requester_id, :target_id, 'block', :source_id,
                'Blocked by a member', 'open', :created_at
            )
            """
        ),
        {
            "id": review_id,
            "requester_id": actor_id,
            "target_id": target_id,
            "source_id": uuid.uuid4().hex,
            "created_at": created_at,
        },
    )
    record_audit_event(
        db,
        request,
        event_type="safety.member_blocked",
        actor_type="user",
        actor_id=actor_id,
        subject_account_id=target_id,
        outcome="success",
    )


@router.get("/blocks", response_model=list[BlockedAccountResponse])
def list_blocked_accounts(
    request: Request,
    account: CurrentAccount,
    db: DbSession,
) -> list[BlockedAccountResponse]:
    rows = db.execute(
        text(
            """
            SELECT a.id, p.display_name, p.photos, b.created_at
            FROM safety_blocks b
            JOIN accounts a ON a.id = b.blocked_id
            JOIN profiles p ON p.account_id = a.id
            WHERE b.blocker_id = :account_id
            ORDER BY b.created_at DESC, a.id
            """
        ),
        {"account_id": account.account_id},
    ).mappings()
    result: list[BlockedAccountResponse] = []
    for row in rows:
        photos = json.loads(row["photos"]) if isinstance(row["photos"], str) else row["photos"]
        result.append(
            BlockedAccountResponse(
                id=str(row["id"]),
                display_name=row["display_name"],
                photo=photos[0] if photos else None,
                blocked_at=row["created_at"],
            )
        )
    record_audit_event(
        db,
        request,
        event_type="safety.blocks_viewed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
    )
    db.commit()
    return result


@router.post("/blocks", status_code=204, dependencies=[Depends(require_csrf)])
def block_member(
    body: BlockCreateRequest,
    request: Request,
    account: CurrentAccount,
    db: DbSession,
) -> None:
    _target_profile(db, body.target_id, account.account_id)
    _create_block(db, request, account.account_id, body.target_id)
    db.commit()


@router.delete("/blocks/{target_id}", status_code=204, dependencies=[Depends(require_csrf)])
def unblock_member(
    target_id: str,
    request: Request,
    account: CurrentAccount,
    db: DbSession,
) -> None:
    result = db.execute(
        text(
            """
            DELETE FROM safety_blocks
            WHERE blocker_id = :account_id AND blocked_id = :target_id
            """
        ),
        {"account_id": account.account_id, "target_id": target_id},
    )
    if result.rowcount:
        record_audit_event(
            db,
            request,
            event_type="safety.member_unblocked",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=target_id,
            outcome="success",
        )
    db.commit()


@router.post("/reports", status_code=201, dependencies=[Depends(require_csrf)])
def report_member(
    body: ReportCreateRequest,
    request: Request,
    account: CurrentAccount,
    db: DbSession,
) -> dict[str, str]:
    _target_profile(db, body.target_id, account.account_id)
    report_id = uuid.uuid4().hex
    created_at = _now()
    db.execute(
        text(
            """
            INSERT INTO safety_reports (
                id, reporter_id, target_account_id, reason, description, status, created_at
            )
            VALUES (
                :id, :reporter_id, :target_id, :reason, :description, 'open', :created_at
            )
            """
        ),
        {
            "id": report_id,
            "reporter_id": account.account_id,
            "target_id": body.target_id,
            "reason": body.reason,
            "description": body.description.strip() if body.description else None,
            "created_at": created_at,
        },
    )
    db.execute(
        text(
            """
            INSERT INTO moderation_review_requests (
                id, requester_id, target_account_id, source_type, source_id,
                reason, status, created_at
            )
            VALUES (
                :id, :requester_id, :target_id, 'report', :source_id,
                :reason, 'open', :created_at
            )
            """
        ),
        {
            "id": uuid.uuid4().hex,
            "requester_id": account.account_id,
            "target_id": body.target_id,
            "source_id": report_id,
            "reason": body.description.strip() if body.description else body.reason,
            "created_at": created_at,
        },
    )
    if body.also_block:
        _create_block(db, request, account.account_id, body.target_id)
    record_audit_event(
        db,
        request,
        event_type="safety.member_reported",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=body.target_id,
        outcome="success",
        metadata={"reason": body.reason},
    )
    db.commit()
    return {"id": report_id}


@router.get("/emergency-contacts", response_model=list[EmergencyContactResponse])
def list_emergency_contacts(
    request: Request,
    account: CurrentAccount,
    db: DbSession,
) -> list[EmergencyContactResponse]:
    rows = db.execute(
        text(
            """
            SELECT id, name, phone, relationship
            FROM emergency_contacts
            WHERE account_id = :account_id
            ORDER BY created_at, id
            """
        ),
        {"account_id": account.account_id},
    ).mappings()
    contacts = [EmergencyContactResponse(**dict(row)) for row in rows]
    record_audit_event(
        db,
        request,
        event_type="safety.emergency_contacts_viewed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
    )
    db.commit()
    return contacts


@router.post(
    "/emergency-contacts",
    response_model=EmergencyContactResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def add_emergency_contact(
    body: EmergencyContactRequest,
    request: Request,
    account: CurrentAccount,
    db: DbSession,
) -> EmergencyContactResponse:
    name = body.name.strip()
    phone = body.phone.strip()
    relationship = body.relationship.strip()
    if not name or not phone or not relationship or not PHONE_PATTERN.fullmatch(phone):
        raise ApiException("INVALID_CONTACT", "Enter a valid contact name, phone number and relationship.")
    contact_id = uuid.uuid4().hex
    db.execute(
        text(
            """
            INSERT INTO emergency_contacts (id, account_id, name, phone, relationship)
            VALUES (:id, :account_id, :name, :phone, :relationship)
            """
        ),
        {
            "id": contact_id,
            "account_id": account.account_id,
            "name": name,
            "phone": phone,
            "relationship": relationship,
        },
    )
    record_audit_event(
        db,
        request,
        event_type="safety.emergency_contact_added",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
    )
    db.commit()
    return EmergencyContactResponse(
        id=contact_id,
        name=name,
        phone=phone,
        relationship=relationship,
    )


@router.delete(
    "/emergency-contacts/{contact_id}",
    status_code=204,
    dependencies=[Depends(require_csrf)],
)
def remove_emergency_contact(
    contact_id: str,
    request: Request,
    account: CurrentAccount,
    db: DbSession,
) -> None:
    result = db.execute(
        text(
            """
            DELETE FROM emergency_contacts
            WHERE id = :contact_id AND account_id = :account_id
            """
        ),
        {"contact_id": contact_id, "account_id": account.account_id},
    )
    if result.rowcount:
        record_audit_event(
            db,
            request,
            event_type="safety.emergency_contact_removed",
            actor_type="user",
            actor_id=account.account_id,
            subject_account_id=account.account_id,
            outcome="success",
        )
    db.commit()


@router.get("/check-ins", response_model=list[SafetyCheckInResponse])
def list_safety_check_ins(
    request: Request,
    account: CurrentAccount,
    db: DbSession,
) -> list[SafetyCheckInResponse]:
    rows = db.execute(
        text(
            """
            SELECT id, message, notified_contacts_json, status, location_link, created_at
            FROM safety_check_ins
            WHERE account_id = :account_id
            ORDER BY created_at DESC, id
            """
        ),
        {"account_id": account.account_id},
    ).mappings()
    check_ins = [
        SafetyCheckInResponse(
            id=str(row["id"]),
            message=row["message"],
            notified_contacts=(
                json.loads(row["notified_contacts_json"])
                if row["notified_contacts_json"]
                else []
            ),
            status=row["status"],
            location_link=row["location_link"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
    record_audit_event(
        db,
        request,
        event_type="safety.check_ins_viewed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
    )
    db.commit()
    return check_ins


@router.post(
    "/check-ins",
    response_model=SafetyCheckInResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_safety_check_in(
    body: SafetyCheckInCreateRequest,
    request: Request,
    account: CurrentAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> SafetyCheckInResponse:
    contacts = db.execute(
        text(
            """
            SELECT name, phone
            FROM emergency_contacts
            WHERE account_id = :account_id
            ORDER BY created_at, id
            """
        ),
        {"account_id": account.account_id},
    ).mappings().all()
    if not contacts:
        raise ApiException("NO_CONTACTS", "Add at least one emergency contact first.")

    check_in_id = uuid.uuid4().hex
    created_at = _now()
    message = body.message.strip()
    db.execute(
        text(
            """
            INSERT INTO safety_check_ins (
                id, account_id, message, location_link, status, notified_contacts_json, created_at
            )
            VALUES (
                :id, :account_id, :message, :location_link, 'sending', '[]', :created_at
            )
            """
        ),
        {
            "id": check_in_id,
            "account_id": account.account_id,
            "message": message,
            "location_link": body.location_link,
            "created_at": created_at,
        },
    )
    db.commit()

    profile_name = db.execute(
        text("SELECT display_name FROM profiles WHERE account_id = :account_id"),
        {"account_id": account.account_id},
    ).scalar_one_or_none()
    sms_parts = [f"Flingra safety check-in from {profile_name or 'a Flingra member'}."]
    if message:
        sms_parts.append(f"Message: {message}")
    if body.location_link:
        sms_parts.append(f"Location: {body.location_link}")
    sms_message = "\n".join(sms_parts)

    notified_contacts: list[str] = []
    failed_count = 0
    for contact in contacts:
        try:
            send_sms(settings, str(contact["phone"]), sms_message)
        except ServiceUnavailable:
            failed_count += 1
        else:
            notified_contacts.append(str(contact["name"]))

    status = (
        "sent"
        if notified_contacts and not failed_count
        else "partially_sent"
        if notified_contacts
        else "failed"
    )
    db.execute(
        text(
            """
            UPDATE safety_check_ins
            SET status = :status, notified_contacts_json = :notified_contacts_json
            WHERE id = :id AND account_id = :account_id
            """
        ),
        {
            "id": check_in_id,
            "account_id": account.account_id,
            "status": status,
            "notified_contacts_json": json.dumps(notified_contacts, separators=(",", ":")),
        },
    )
    record_audit_event(
        db,
        request,
        event_type="safety.check_in_sent",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success" if notified_contacts else "failure",
        metadata={
            "checkInId": check_in_id,
            "notifiedCount": len(notified_contacts),
            "failedCount": failed_count,
        },
    )
    db.commit()
    if not notified_contacts:
        raise ServiceUnavailable(
            "Emergency contact notifications could not be delivered; no contact was notified."
        )
    return SafetyCheckInResponse(
        id=check_in_id,
        message=message,
        notified_contacts=notified_contacts,
        status=status,
        location_link=body.location_link,
        created_at=created_at,
    )
