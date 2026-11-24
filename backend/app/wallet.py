import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.errors import ApiException


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def ensure_wallet_account(db: Session, account_id: str) -> None:
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        db.execute(
            text(
                """
                INSERT INTO wallet_accounts (account_id, balance_kobo)
                VALUES (:account_id, 0)
                ON CONFLICT(account_id) DO NOTHING
                """
            ),
            {"account_id": account_id},
        )
    else:
        db.execute(
            text(
                """
                INSERT INTO wallet_accounts (account_id, balance_kobo)
                VALUES (:account_id, 0)
                ON DUPLICATE KEY UPDATE account_id = VALUES(account_id)
                """
            ),
            {"account_id": account_id},
        )


def get_wallet_balance_kobo(db: Session, account_id: str) -> int:
    balance = db.execute(
        text("SELECT balance_kobo FROM wallet_accounts WHERE account_id = :account_id"),
        {"account_id": account_id},
    ).scalar_one_or_none()
    return int(balance or 0)


def debit_wallet(
    db: Session,
    account_id: str,
    amount_kobo: int,
    *,
    transaction_type: str,
    description: str,
    status: str = "completed",
) -> int:
    if amount_kobo <= 0:
        raise ValueError("Wallet debits must be positive kobo amounts.")
    ensure_wallet_account(db, account_id)
    result = db.execute(
        text(
            """
            UPDATE wallet_accounts
            SET balance_kobo = balance_kobo - :amount_kobo
            WHERE account_id = :account_id AND balance_kobo >= :amount_kobo
            """
        ),
        {"account_id": account_id, "amount_kobo": amount_kobo},
    )
    if result.rowcount != 1:
        raise ApiException("INSUFFICIENT_BALANCE", "Your wallet balance is too low.", 409)
    add_wallet_transaction(
        db,
        account_id,
        transaction_type=transaction_type,
        amount_kobo=-amount_kobo,
        description=description,
        status=status,
    )
    return get_wallet_balance_kobo(db, account_id)


def credit_wallet(
    db: Session,
    account_id: str,
    amount_kobo: int,
    *,
    transaction_type: str,
    description: str,
    status: str = "completed",
) -> int:
    if amount_kobo <= 0:
        raise ValueError("Wallet credits must be positive kobo amounts.")
    ensure_wallet_account(db, account_id)
    db.execute(
        text(
            """
            UPDATE wallet_accounts SET balance_kobo = balance_kobo + :amount_kobo
            WHERE account_id = :account_id
            """
        ),
        {"account_id": account_id, "amount_kobo": amount_kobo},
    )
    add_wallet_transaction(
        db,
        account_id,
        transaction_type=transaction_type,
        amount_kobo=amount_kobo,
        description=description,
        status=status,
    )
    return get_wallet_balance_kobo(db, account_id)


def add_wallet_transaction(
    db: Session,
    account_id: str,
    *,
    transaction_type: str,
    amount_kobo: int,
    description: str,
    status: str = "completed",
) -> str:
    transaction_id = uuid.uuid4().hex
    db.execute(
        text(
            """
            INSERT INTO wallet_transactions (
                id, account_id, transaction_type, amount_kobo, description, status, created_at
            )
            VALUES (
                :id, :account_id, :transaction_type, :amount_kobo, :description, :status, :created_at
            )
            """
        ),
        {
            "id": transaction_id,
            "account_id": account_id,
            "transaction_type": transaction_type,
            "amount_kobo": amount_kobo,
            "description": description[:500],
            "status": status,
            "created_at": _now(),
        },
    )
    return transaction_id
