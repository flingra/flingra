from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.dependencies import db_session
from app.errors import ApiException
from app.feature_schemas import MeetupPaymentResolutionRequest
from app.realtime import enqueue_realtime_event
from app.routes.admin import AdminAccount, require_admin_csrf, require_admin_roles
from app.wallet import credit_wallet

router = APIRouter(prefix="/admin/meetup-payments", tags=["admin", "meetup-payments"])
DbSession = Annotated[Session, Depends(db_session)]
SuperAdmin = Annotated[AdminAccount, Depends(require_admin_roles("super_admin"))]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@router.get("/disputes")
def list_meetup_payment_disputes(
    admin: SuperAdmin,
    db: DbSession,
    limit: int = 50,
) -> dict[str, list[dict[str, Any]]]:
    if limit < 1 or limit > 100:
        raise ApiException("INVALID_LIMIT", "Limit must be between 1 and 100.", 400)
    rows = db.execute(
        text(
            """
            SELECT id, thread_id, payer_id, recipient_id, payer_name, recipient_name,
                   amount_kobo, dispute_reason, dispute_opened_by, created_at, updated_at
            FROM meetup_payments
            WHERE status = 'disputed'
            ORDER BY updated_at, id
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings()
    return {
        "items": [
            {
                "id": str(row["id"]),
                "threadId": str(row["thread_id"]),
                "payerId": str(row["payer_id"]),
                "payerName": str(row["payer_name"]),
                "recipientId": str(row["recipient_id"]),
                "recipientName": str(row["recipient_name"]),
                "amountNaira": int(row["amount_kobo"]) // 100,
                "reason": str(row["dispute_reason"] or ""),
                "openedBy": str(row["dispute_opened_by"] or ""),
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
            }
            for row in rows
        ]
    }


@router.post(
    "/{payment_id}/resolve",
    dependencies=[Depends(require_admin_csrf)],
)
def resolve_meetup_payment_dispute(
    payment_id: str,
    body: MeetupPaymentResolutionRequest,
    request: Request,
    admin: SuperAdmin,
    db: DbSession,
) -> dict[str, str]:
    suffix = " FOR UPDATE" if db.get_bind().dialect.name != "sqlite" else ""
    payment = db.execute(
        text(
            """
            SELECT payer_id, recipient_id, payer_name, recipient_name,
                   amount_kobo, created_at, status
            FROM meetup_payments WHERE id = :id
            """
            + suffix
        ),
        {"id": payment_id},
    ).mappings().first()
    if payment is None:
        raise ApiException("PAYMENT_NOT_FOUND", "This meetup payment is unavailable.", 404)
    if payment["status"] != "disputed":
        raise ApiException("PAYMENT_NOT_DISPUTED", "Only disputed payments can be resolved.", 409)

    reason = body.reason.strip()
    if not reason:
        raise ApiException("INVALID_RESOLUTION_REASON", "Add the reason for this resolution.", 400)
    recipient_id = str(payment["recipient_id"])
    payer_id = str(payment["payer_id"])
    amount_kobo = int(payment["amount_kobo"])
    recipient = body.resolution == "release"
    credit_wallet(
        db,
        recipient_id if recipient else payer_id,
        amount_kobo,
        transaction_type=(
            "meetup-payment-released" if recipient else "meetup-payment-refunded"
        ),
        description=(
            "Disputed meetup payment released by admin"
            if recipient
            else "Disputed meetup payment refunded by admin"
        ),
    )
    status = "released" if recipient else "refunded"
    now = _now()
    db.execute(
        text(
            """
            UPDATE meetup_payments
            SET status = :status, resolution_reason = :reason,
                resolved_by_admin_id = :admin_id, resolved_at = :now, updated_at = :now
            WHERE id = :id AND status = 'disputed'
            """
        ),
        {
            "id": payment_id,
            "status": status,
            "reason": reason,
            "admin_id": admin.admin_id,
            "now": now,
        },
    )
    record_audit_event(
        db,
        request,
        event_type=f"meetup_payment.dispute_{status}",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=recipient_id,
        outcome="success",
        metadata={"paymentId": payment_id, "reason": reason},
    )
    event = {
        "id": payment_id,
        "fromId": payer_id,
        "fromName": str(payment["payer_name"]),
        "toId": recipient_id,
        "toName": str(payment["recipient_name"]),
        "amountNaira": amount_kobo // 100,
        "status": status,
        "createdAt": payment["created_at"].isoformat()
        if isinstance(payment["created_at"], datetime)
        else str(payment["created_at"]),
        "resolvedAt": now.isoformat(),
    }
    for recipient_account_id in {payer_id, recipient_id}:
        enqueue_realtime_event(
            db,
            recipient_account_id,
            "meetup_payment.updated",
            event,
        )
    db.commit()
    return {"id": payment_id, "status": status}
