from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.dependencies import db_session
from app.errors import ApiException
from app.feature_schemas import AdminSafetyDecisionRequest
from app.routes.admin import AdminAccount, require_admin_csrf, require_admin_roles

router = APIRouter(prefix="/admin/safety", tags=["admin safety"])
DbSession = Annotated[Session, Depends(db_session)]
SafetyAdmin = Annotated[
    AdminAccount,
    Depends(require_admin_roles("super_admin", "safety_admin", "reviewer")),
]


@router.get("/reviews")
def list_safety_reviews(
    request: Request,
    db: DbSession,
    admin: SafetyAdmin,
    status: Literal["open", "reviewed", "dismissed", "all"] = Query(default="open"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    status_filter = "" if status == "all" else "AND r.status = :status"
    parameters: dict[str, object] = {"limit": limit, "offset": offset}
    if status != "all":
        parameters["status"] = status
    rows = list(db.execute(
        text(
            f"""
            SELECT r.id, r.source_type, r.source_id, r.reason, r.status, r.created_at,
                   r.target_account_id, target.display_name AS target_name,
                   r.requester_id, reporter.display_name AS requester_name
            FROM moderation_review_requests r
            JOIN profiles target ON target.account_id = r.target_account_id
            JOIN profiles reporter ON reporter.account_id = r.requester_id
            WHERE 1 = 1 {status_filter}
            ORDER BY r.created_at ASC, r.id
            LIMIT :limit OFFSET :offset
            """
        ),
        parameters,
    ).mappings())
    total = db.execute(
        text(
            f"SELECT COUNT(*) FROM moderation_review_requests r WHERE 1 = 1 {status_filter}"
        ),
        {key: value for key, value in parameters.items() if key == "status"},
    ).scalar_one()
    record_audit_event(
        db,
        request,
        event_type="admin.safety.review_queue_viewed",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=None,
        outcome="success",
        metadata={"status": status, "count": len(rows)},
    )
    db.commit()
    return {
        "items": [
            {
                "id": str(row["id"]),
                "sourceType": row["source_type"],
                "sourceId": str(row["source_id"]),
                "targetId": str(row["target_account_id"]),
                "targetName": row["target_name"],
                "requesterId": str(row["requester_id"]),
                "requesterName": row["requester_name"],
                "reason": row["reason"],
                "status": row["status"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ],
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


@router.post(
    "/reviews/{review_id}/decision",
    dependencies=[Depends(require_admin_csrf)],
)
def decide_safety_review(
    review_id: str,
    body: AdminSafetyDecisionRequest,
    request: Request,
    db: DbSession,
    admin: SafetyAdmin,
) -> dict[str, str]:
    review = db.execute(
        text(
            """
            SELECT target_account_id, source_type, source_id, status
            FROM moderation_review_requests
            WHERE id = :review_id
            """
        ),
        {"review_id": review_id},
    ).mappings().first()
    if review is None:
        raise ApiException("SAFETY_REVIEW_NOT_FOUND", "This safety review is unavailable.", 404)
    if review["status"] != "open":
        raise ApiException("SAFETY_REVIEW_ALREADY_RESOLVED", "This safety review has already been resolved.", 409)
    now = datetime.now(UTC).replace(tzinfo=None)
    result = db.execute(
        text(
            """
            UPDATE moderation_review_requests
            SET status = :decision
            WHERE id = :review_id AND status = 'open'
            """
        ),
        {"decision": body.decision, "review_id": review_id},
    )
    if result.rowcount != 1:
        raise ApiException(
            "SAFETY_REVIEW_ALREADY_RESOLVED",
            "This safety review has already been resolved.",
            409,
        )
    if review["source_type"] == "report":
        db.execute(
            text(
                """
                UPDATE safety_reports
                SET status = :decision, resolved_at = :resolved_at
                WHERE id = :source_id AND status = 'open'
                """
            ),
            {
                "decision": body.decision,
                "resolved_at": now,
                "source_id": review["source_id"],
            },
        )
    record_audit_event(
        db,
        request,
        event_type="admin.safety.review_decided",
        actor_type="admin",
        actor_id=admin.admin_id,
        subject_account_id=str(review["target_account_id"]),
        outcome="success",
        metadata={"decision": body.decision, "reason": body.reason},
    )
    db.commit()
    return {"id": review_id, "status": body.decision}
