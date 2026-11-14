import json
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.orm import Session

ActorType = Literal["user", "admin", "anonymous", "system"]
AuditOutcome = Literal["success", "failure", "denied"]


def record_audit_event(
    db: Session,
    request: Request | None,
    *,
    event_type: str,
    actor_type: ActorType,
    actor_id: str | None,
    subject_account_id: str | None,
    outcome: AuditOutcome,
    metadata: dict[str, object] | None = None,
) -> None:
    safe_metadata = metadata or {}
    metadata_json = json.dumps(safe_metadata, separators=(",", ":"), ensure_ascii=True)
    if len(metadata_json) > 4096:
        raise ValueError("Audit metadata exceeds the maximum permitted size.")
    db.execute(
        text(
            """
            INSERT INTO platform_audit_events (
                id, event_type, actor_type, actor_id, subject_account_id,
                outcome, request_id, metadata, created_at
            )
            VALUES (
                :id, :event_type, :actor_type, :actor_id, :subject_account_id,
                :outcome, :request_id, :metadata, :created_at
            )
            """
        ),
        {
            "id": uuid.uuid4().hex,
            "event_type": event_type,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "subject_account_id": subject_account_id,
            "outcome": outcome,
            "request_id": (
                request.state.request_id if request is not None else uuid.uuid4().hex
            ),
            "metadata": metadata_json,
            "created_at": datetime.now(UTC).replace(tzinfo=None),
        },
    )
