import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.config import Settings
from app.dependencies import db_session
from app.errors import ApiException
from app.feature_schemas import PayoutBankAccountRequest, PayoutRequestBody
from app.paystack import (
    create_transfer_recipient,
    ensure_configured,
    initiate_transfer,
    list_nigerian_banks,
    resolve_bank_account,
)
from app.routes.auth import IdentityVerifiedAccount, get_app_settings, require_csrf
from app.wallet import credit_wallet, debit_wallet, require_wallet_ready

router = APIRouter(tags=["payouts"])
DbSession = Annotated[Session, Depends(db_session)]
SettingsDependency = Annotated[Settings, Depends(get_app_settings)]
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _payout_response(row: Any) -> dict[str, str | int]:
    created_at = row["created_at"]
    return {
        "id": str(row["id"]),
        "reference": str(row["reference"]),
        "amountNaira": int(row["amount_kobo"]) // 100,
        "status": str(row["status"]),
        "requestedAt": (
            created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)
        ),
    }


@router.get("/payout/banks")
def get_payout_banks(
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> list[dict[str, str]]:
    require_wallet_ready(account)
    banks = list_nigerian_banks(settings)
    return [
        {"code": str(bank["code"]), "name": str(bank["name"])}
        for bank in banks
        if bank.get("code") and bank.get("name")
    ]


@router.get("/payout/bank-account")
def get_payout_bank_account(
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> dict[str, str] | None:
    require_wallet_ready(account)
    row = db.execute(
        text(
            """
            SELECT bank_name, account_name, account_last4
            FROM payout_bank_accounts
            WHERE account_id = :account_id
            """
        ),
        {"account_id": account.account_id},
    ).mappings().first()
    if row is None:
        return None
    return {
        "bankName": str(row["bank_name"]),
        "accountName": str(row["account_name"]),
        "accountNumberMasked": f"****{row['account_last4']}",
    }


@router.put(
    "/payout/bank-account",
    dependencies=[Depends(require_csrf)],
)
def save_payout_bank_account(
    body: PayoutBankAccountRequest,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> dict[str, str]:
    require_wallet_ready(account)
    ensure_configured(settings)
    banks = list_nigerian_banks(settings)
    bank = next((item for item in banks if str(item.get("code")) == body.bank_code), None)
    if bank is None or not isinstance(bank.get("name"), str):
        raise ApiException("BANK_NOT_FOUND", "Choose a supported Nigerian bank.", 400)
    resolved = resolve_bank_account(
        settings,
        account_number=body.account_number,
        bank_code=body.bank_code,
    )
    account_name = str(resolved["account_name"]).strip()
    recipient_code = create_transfer_recipient(
        settings,
        account_name=account_name,
        account_number=body.account_number,
        bank_code=body.bank_code,
    )
    values = {
        "account_id": account.account_id,
        "recipient_code": recipient_code,
        "bank_code": body.bank_code,
        "bank_name": str(bank["name"])[:100],
        "account_name": account_name[:150],
        "account_last4": body.account_number[-4:],
        "now": _now(),
    }
    if db.get_bind().dialect.name == "sqlite":
        statement = """
            INSERT INTO payout_bank_accounts (
                account_id, recipient_code, bank_code, bank_name, account_name,
                account_last4, created_at, updated_at
            )
            VALUES (
                :account_id, :recipient_code, :bank_code, :bank_name, :account_name,
                :account_last4, :now, :now
            )
            ON CONFLICT(account_id) DO UPDATE SET
                recipient_code = excluded.recipient_code,
                bank_code = excluded.bank_code,
                bank_name = excluded.bank_name,
                account_name = excluded.account_name,
                account_last4 = excluded.account_last4,
                updated_at = excluded.updated_at
        """
    else:
        statement = """
            INSERT INTO payout_bank_accounts (
                account_id, recipient_code, bank_code, bank_name, account_name,
                account_last4, created_at, updated_at
            )
            VALUES (
                :account_id, :recipient_code, :bank_code, :bank_name, :account_name,
                :account_last4, :now, :now
            )
            ON DUPLICATE KEY UPDATE
                recipient_code = VALUES(recipient_code),
                bank_code = VALUES(bank_code),
                bank_name = VALUES(bank_name),
                account_name = VALUES(account_name),
                account_last4 = VALUES(account_last4),
                updated_at = VALUES(updated_at)
        """
    db.execute(text(statement), values)
    record_audit_event(
        db,
        request,
        event_type="payout.bank_account_saved",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
        metadata={"bankCode": body.bank_code, "accountLast4": body.account_number[-4:]},
    )
    db.commit()
    return {
        "bankName": str(bank["name"]),
        "accountName": account_name,
        "accountNumberMasked": f"****{body.account_number[-4:]}",
    }


@router.post("/payouts", status_code=201, dependencies=[Depends(require_csrf)])
def request_payout(
    body: PayoutRequestBody,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, str | int]:
    require_wallet_ready(account)
    ensure_configured(settings)
    if not idempotency_key or not IDEMPOTENCY_KEY_PATTERN.fullmatch(idempotency_key):
        raise ApiException("IDEMPOTENCY_KEY_REQUIRED", "Provide a valid Idempotency-Key header.", 400)

    existing = db.execute(
        text(
            """
            SELECT id, reference, amount_kobo, status, created_at
            FROM payout_requests
            WHERE account_id = :account_id AND idempotency_key = :idempotency_key
            """
        ),
        {"account_id": account.account_id, "idempotency_key": idempotency_key},
    ).mappings().first()
    amount_kobo = body.amount_naira * 100
    if existing is not None:
        if int(existing["amount_kobo"]) != amount_kobo:
            raise ApiException(
                "IDEMPOTENCY_KEY_REUSED",
                "This Idempotency-Key was already used for a different payout.",
                409,
            )
        return _payout_response(existing)

    bank = db.execute(
        text(
            """
            SELECT recipient_code
            FROM payout_bank_accounts
            WHERE account_id = :account_id
            """
        ),
        {"account_id": account.account_id},
    ).scalar_one_or_none()
    if bank is None:
        raise ApiException("NO_BANK_ACCOUNT", "Save a verified bank account before requesting a payout.", 400)

    payout_id = uuid.uuid4().hex
    transaction_id = uuid.uuid4().hex
    reference = f"flingra_payout_{payout_id}"
    now = _now()
    try:
        db.execute(
            text(
                """
                INSERT INTO payout_requests (
                    id, account_id, idempotency_key, reference, recipient_code, amount_kobo,
                    wallet_transaction_id, status, created_at, updated_at
                )
                VALUES (
                    :id, :account_id, :idempotency_key, :reference, :recipient_code, :amount_kobo,
                    :wallet_transaction_id, 'initiating', :now, :now
                )
                """
            ),
            {
                "id": payout_id,
                "account_id": account.account_id,
                "idempotency_key": idempotency_key,
                "reference": reference,
                "recipient_code": bank,
                "amount_kobo": amount_kobo,
                "wallet_transaction_id": transaction_id,
                "now": now,
            },
        )
    except IntegrityError:
        db.rollback()
        existing = db.execute(
            text(
                """
                SELECT id, reference, amount_kobo, status, created_at
                FROM payout_requests
                WHERE account_id = :account_id AND idempotency_key = :idempotency_key
                """
            ),
            {"account_id": account.account_id, "idempotency_key": idempotency_key},
        ).mappings().first()
        if existing is None:
            raise
        if int(existing["amount_kobo"]) != amount_kobo:
            raise ApiException(
                "IDEMPOTENCY_KEY_REUSED",
                "This Idempotency-Key was already used for a different payout.",
                409,
            )
        return _payout_response(existing)
    debit_wallet(
        db,
        account.account_id,
        amount_kobo,
        transaction_type="payout",
        description=f"Payout request {reference}",
        status="pending",
        transaction_id=transaction_id,
    )
    record_audit_event(
        db,
        request,
        event_type="payout.requested",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
        metadata={"payoutId": payout_id, "amountKobo": amount_kobo},
    )
    db.commit()

    transfer = initiate_transfer(
        settings,
        amount_kobo=amount_kobo,
        recipient_code=str(bank),
        reference=reference,
    )
    db.execute(
        text(
            """
            UPDATE payout_requests
            SET status = 'pending', transfer_code = :transfer_code, updated_at = :now
            WHERE id = :id AND status = 'initiating'
            """
        ),
        {"id": payout_id, "transfer_code": transfer.get("transfer_code"), "now": _now()},
    )
    db.commit()
    row = db.execute(
        text(
            """
            SELECT id, reference, amount_kobo, status, created_at
            FROM payout_requests WHERE id = :id
            """
        ),
        {"id": payout_id},
    ).mappings().one()
    return _payout_response(row)


@router.get("/payouts")
def list_payouts(
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> list[dict[str, str | int]]:
    rows = db.execute(
        text(
            """
            SELECT id, reference, amount_kobo, status, created_at
            FROM payout_requests
            WHERE account_id = :account_id
            ORDER BY created_at DESC, id DESC
            LIMIT 100
            """
        ),
        {"account_id": account.account_id},
    ).mappings()
    return [_payout_response(row) for row in rows]


def settle_paystack_transfer(
    db: Session,
    request: Request,
    event_type: str,
    data: dict[str, Any],
) -> bool:
    reference = data.get("reference")
    if not isinstance(reference, str):
        return False
    suffix = " FOR UPDATE" if db.get_bind().dialect.name != "sqlite" else ""
    payout = db.execute(
        text(
            """
            SELECT id, account_id, amount_kobo, wallet_transaction_id, status
            FROM payout_requests WHERE reference = :reference
            """
            + suffix
        ),
        {"reference": reference},
    ).mappings().first()
    if payout is None:
        return False

    if event_type == "transfer.success":
        if payout["status"] != "pending" and payout["status"] != "initiating":
            return False
        status = "completed"
    elif event_type == "transfer.reversed":
        if payout["status"] in {"failed", "reversed"}:
            return False
        status = "reversed"
    elif event_type == "transfer.failed":
        if payout["status"] in {"completed", "failed", "reversed"}:
            return False
        status = "failed"
    else:
        return False

    now = _now()
    if status in {"failed", "reversed"}:
        credit_wallet(
            db,
            str(payout["account_id"]),
            int(payout["amount_kobo"]),
            transaction_type="payout-refund",
            description=f"Refund for payout {reference}",
        )
    db.execute(
        text(
            """
            UPDATE payout_requests
            SET status = :status, updated_at = :now
            WHERE id = :id AND status IN ('initiating', 'pending', 'completed')
            """
        ),
        {"id": payout["id"], "status": status, "now": now},
    )
    db.execute(
        text(
            """
            UPDATE wallet_transactions SET status = 'completed'
            WHERE id = :transaction_id AND account_id = :account_id
            """
        ),
        {
            "transaction_id": payout["wallet_transaction_id"],
            "account_id": payout["account_id"],
        },
    )
    record_audit_event(
        db,
        request,
        event_type=f"payout.{status}",
        actor_type="system",
        actor_id=None,
        subject_account_id=str(payout["account_id"]),
        outcome="success",
        metadata={"reference": reference, "amountKobo": int(payout["amount_kobo"])},
    )
    db.commit()
    return True
