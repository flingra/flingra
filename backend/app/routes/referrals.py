from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dependencies import db_session
from app.errors import ApiException
from app.referrals import ensure_referral_code
from app.routes.auth import CurrentAccount

router = APIRouter(prefix="/referrals", tags=["referrals"])
DbSession = Annotated[Session, Depends(db_session)]


def _require_verified_contact(account: dict[str, Any]) -> None:
    if not account["email_verified"]:
        raise ApiException("CONTACT_NOT_VERIFIED", "Verify your contact to use referrals.", 403)


@router.get("/code")
def get_referral_code(
    account: CurrentAccount,
    db: DbSession,
) -> dict[str, str]:
    _require_verified_contact(account)
    code = ensure_referral_code(db, account.account_id)
    db.commit()
    return {"code": code}


@router.get("")
def list_referral_rewards(
    account: CurrentAccount,
    db: DbSession,
) -> list[dict[str, str | int]]:
    _require_verified_contact(account)
    rows = db.execute(
        text(
            """
            SELECT referral_code, bonus_kobo, created_at
            FROM referral_rewards
            WHERE referred_account_id = :account_id
            ORDER BY created_at DESC
            """
        ),
        {"account_id": account.account_id},
    ).mappings()
    return [
        {
            "id": f"referral-{account.account_id}",
            "referredName": f"Signup bonus (code {row['referral_code']})",
            "bonusNaira": int(row["bonus_kobo"]) // 100,
            "joinedAt": row["created_at"].isoformat()
            if hasattr(row["created_at"], "isoformat")
            else str(row["created_at"]),
        }
        for row in rows
    ]
