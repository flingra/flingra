from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def normalize_referral_code(code: str | None) -> str | None:
    normalized = code.strip().upper() if code else ""
    return normalized or None


def ensure_referral_code(db: Session, account_id: str) -> str:
    existing = db.execute(
        text("SELECT code FROM referral_codes WHERE account_id = :account_id"),
        {"account_id": account_id},
    ).scalar_one_or_none()
    if existing is not None:
        return str(existing)
    code = account_id.replace("-", "")[-16:].upper()
    db.execute(
        text(
            """
            INSERT INTO referral_codes (account_id, code, created_at)
            VALUES (:account_id, :code, :created_at)
            """
        ),
        {"account_id": account_id, "code": code, "created_at": _now()},
    )
    return code
