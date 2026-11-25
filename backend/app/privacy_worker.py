import json
import logging
import argparse
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import bindparam, inspect, text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_engine
from app.errors import ServiceUnavailable
from app.storage import CloudinaryObjectStorage, ObjectStorage

logger = logging.getLogger("uvicorn.error")
PROCESSING_TIMEOUT = timedelta(minutes=15)
EXPORT_TABLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "emergency_contacts": ("account_id", ("id", "name", "phone", "relationship", "created_at")),
    "safety_check_ins": (
        "account_id",
        ("id", "message", "location_link", "status", "notified_contacts_json", "created_at"),
    ),
    "member_posts": ("author_id", ("id", "photos", "video_url", "caption", "created_at")),
    "member_statuses": ("author_id", ("id", "media_url", "media_kind", "created_at", "expires_at")),
    "media_objects": ("account_id", ("id", "purpose", "object_key", "content_type", "size_bytes", "created_at")),
    "wallet_accounts": ("account_id", ("balance_kobo", "updated_at")),
    "wallet_transactions": (
        "account_id",
        ("id", "transaction_type", "amount_kobo", "description", "status", "created_at"),
    ),
    "wallet_payment_intents": (
        "account_id",
        ("id", "reference", "amount_kobo", "currency", "status", "created_at", "settled_at"),
    ),
    "gift_inventory": ("account_id", ("gift_type_id", "quantity")),
    "payout_requests": ("account_id", ("id", "reference", "amount_kobo", "status", "created_at")),
    "payout_bank_accounts": (
        "account_id",
        ("bank_name", "account_name", "account_last4", "created_at"),
    ),
    "referral_codes": ("account_id", ("code", "created_at")),
}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _export_account_data(db: Session, account_id: str) -> dict[str, Any]:
    account = db.execute(
        text(
            """
            SELECT id, email, identifier, identifier_type, date_of_birth, gender,
                   terms_version, privacy_version, email_verified, account_state, created_at
            FROM accounts WHERE id = :account_id
            """
        ),
        {"account_id": account_id},
    ).mappings().one_or_none()
    if account is None:
        raise ValueError("The account associated with this export no longer exists.")
    profile = db.execute(
        text("SELECT * FROM profiles WHERE account_id = :account_id"),
        {"account_id": account_id},
    ).mappings().one_or_none()
    export: dict[str, Any] = {
        "account": dict(account),
        "profile": dict(profile) if profile is not None else None,
        "data": {},
    }

    tables = set(inspect(db.get_bind()).get_table_names())
    for table, (column, columns) in EXPORT_TABLES.items():
        if table not in tables:
            continue
        rows = db.execute(
            text(
                f"SELECT {', '.join(columns)} FROM {table} "
                f"WHERE {column} = :account_id"
            ),
            {"account_id": account_id},
        ).mappings()
        export["data"][table] = [dict(row) for row in rows]

    for table, where in {
        "safety_blocks": "blocker_id = :account_id OR blocked_id = :account_id",
        "safety_reports": "reporter_id = :account_id OR target_account_id = :account_id",
        "received_gifts": "sender_id = :account_id OR recipient_id = :account_id",
        "meetup_payments": "payer_id = :account_id OR recipient_id = :account_id",
        "referral_rewards": (
            "referred_account_id = :account_id OR referrer_account_id = :account_id"
        ),
        "privacy_requests": "account_id = :account_id",
    }.items():
        if table not in tables:
            continue
        columns = {
            "safety_blocks": ("blocker_id", "blocked_id", "created_at"),
            "safety_reports": ("id", "reporter_id", "target_account_id", "reason", "description", "status", "created_at"),
            "received_gifts": ("id", "recipient_id", "sender_id", "gift_type_id", "value_kobo", "redeemed", "created_at"),
            "meetup_payments": ("id", "payer_id", "recipient_id", "amount_kobo", "status", "created_at", "resolved_at"),
            "referral_rewards": (
                "referred_account_id",
                "referrer_account_id",
                "referral_code",
                "bonus_kobo",
                "created_at",
            ),
            "privacy_requests": ("id", "request_type", "status", "created_at", "updated_at"),
        }[table]
        rows = db.execute(
            text(f"SELECT {', '.join(columns)} FROM {table} WHERE {where}"),
            {"account_id": account_id},
        ).mappings()
        export["data"][table] = [dict(row) for row in rows]

    thread_ids = db.execute(
        text(
            """
            SELECT id FROM chat_threads
            WHERE participant_a_id = :account_id OR participant_b_id = :account_id
            """
        ),
        {"account_id": account_id},
    ).scalars().all()
    export["data"]["chat_threads"] = [
        dict(row)
        for row in db.execute(
            text(
                """
                SELECT id, participant_a_id, participant_b_id, created_at, last_message_at
                FROM chat_threads
                WHERE participant_a_id = :account_id OR participant_b_id = :account_id
                """
            ),
            {"account_id": account_id},
        ).mappings()
    ]
    if thread_ids:
        export["data"]["chat_messages"] = [
            dict(row)
            for row in db.execute(
                text(
                    """
                    SELECT id, thread_id, author_id, message_text, attachment_json, payment_id, created_at
                    FROM chat_messages
                    WHERE thread_id IN :thread_ids
                    ORDER BY created_at, id
                    """
                ).bindparams(bindparam("thread_ids", expanding=True)),
                {"thread_ids": tuple(thread_ids)},
            ).mappings()
        ]
    else:
        export["data"]["chat_messages"] = []

    return export


def _process_export(db: Session, request: dict[str, Any]) -> None:
    result = _export_account_data(db, str(request["account_id"]))
    db.execute(
        text(
            """
            UPDATE privacy_requests
            SET result_json = :result_json, status = 'completed', updated_at = :now
            WHERE id = :id AND status = 'processing'
            """
        ),
        {
            "id": request["id"],
            "result_json": json.dumps(result, default=str, separators=(",", ":")),
            "now": _now(),
        },
    )
    db.commit()


def _process_deletion(
    db: Session,
    request: dict[str, Any],
    settings: Settings,
    storage: ObjectStorage | None,
) -> None:
    account_id = str(request["account_id"])
    object_keys = [
        str(row[0])
        for row in db.execute(
            text("SELECT object_key FROM media_objects WHERE account_id = :account_id"),
            {"account_id": account_id},
        ).all()
    ]
    if object_keys and storage is None:
        storage = CloudinaryObjectStorage(settings)
    if storage is not None:
        for object_key in object_keys:
            storage.delete(object_key)
    db.execute(
        text("DELETE FROM accounts WHERE id = :account_id AND account_state = 'deletion_requested'"),
        {"account_id": account_id},
    )
    db.commit()


def process_privacy_requests(
    db: Session,
    settings: Settings,
    *,
    limit: int = 25,
    storage: ObjectStorage | None = None,
) -> int:
    if not 1 <= limit <= 100:
        raise ValueError("The worker limit must be between 1 and 100.")
    cutoff = _now() - PROCESSING_TIMEOUT
    suffix = " FOR UPDATE SKIP LOCKED" if db.get_bind().dialect.name != "sqlite" else ""
    rows = db.execute(
        text(
            """
            SELECT id, account_id, request_type
            FROM privacy_requests
            WHERE status = 'queued'
               OR (status = 'processing' AND updated_at < :cutoff)
            ORDER BY created_at, id
            LIMIT :limit
            """
            + suffix
        ),
        {"cutoff": cutoff, "limit": limit},
    ).mappings().all()
    requests = [dict(row) for row in rows]
    for request in requests:
        db.execute(
            text(
                """
                UPDATE privacy_requests
                SET status = 'processing', updated_at = :now
                WHERE id = :id
                """
            ),
            {"id": request["id"], "now": _now()},
        )
    db.commit()

    processed = 0
    for request in requests:
        try:
            if request["request_type"] == "data_export":
                _process_export(db, request)
            elif request["request_type"] == "account_deletion":
                _process_deletion(db, request, settings, storage)
            else:
                raise ValueError(f"Unknown privacy request type: {request['request_type']}")
        except ServiceUnavailable as exc:
            db.rollback()
            db.execute(
                text(
                    """
                    UPDATE privacy_requests
                    SET status = 'failed', updated_at = :now
                    WHERE id = :id AND status = 'processing'
                    """
                ),
                {"id": request["id"], "now": _now()},
            )
            db.commit()
            logger.error("Privacy request %s failed: %s", request["id"], exc.message)
            continue
        processed += 1
    return processed


def main() -> None:
    parser = argparse.ArgumentParser(description="Process queued Flingra privacy requests.")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    settings = get_settings()
    with Session(get_engine(settings), expire_on_commit=False) as db:
        processed = process_privacy_requests(db, settings, limit=args.limit)
    print(f"Processed privacy requests: {processed}")


if __name__ == "__main__":
    main()
