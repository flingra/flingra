from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.audit import record_audit_event
from app.dependencies import db_session
from app.errors import ApiException
from app.feature_schemas import SubscriptionStatusResponse, VipPlanResponse, VipSubscriptionRequest
from app.routes.auth import CurrentAccount, IdentityVerifiedAccount, require_csrf
from app.wallet import debit_wallet

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])
DbSession = Annotated[Session, Depends(db_session)]


@router.get("/plans", response_model=list[VipPlanResponse])
def list_subscription_plans(db: DbSession) -> list[VipPlanResponse]:
    rows = db.execute(
        text(
            """
            SELECT id, name, duration_days, price_kobo
            FROM subscription_plans
            WHERE active = TRUE
            ORDER BY price_kobo, id
            """
        )
    ).mappings()
    return [
        VipPlanResponse(
            id=row["id"],
            name=row["name"],
            duration_days=int(row["duration_days"]),
            price_naira=int(row["price_kobo"]) // 100,
        )
        for row in rows
    ]


@router.get("/me", response_model=SubscriptionStatusResponse)
def get_subscription_status(
    request: Request,
    account: CurrentAccount,
    db: DbSession,
) -> SubscriptionStatusResponse:
    row = db.execute(
        text(
            """
            SELECT subscription_tier, vip_expires_at
            FROM profiles
            WHERE account_id = :account_id
            """
        ),
        {"account_id": account.account_id},
    ).mappings().first()
    if row is None:
        raise ApiException("NO_PROFILE", "Finish onboarding before viewing subscription status.", 404)
    expiry = row["vip_expires_at"]
    if isinstance(expiry, str):
        expiry = datetime.fromisoformat(expiry)
    if expiry is not None and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    tier = row["subscription_tier"]
    if expiry is not None and expiry <= datetime.now(UTC):
        tier = "free"
        expiry = None
    record_audit_event(
        db,
        request,
        event_type="subscription.status_viewed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
    )
    db.commit()
    return SubscriptionStatusResponse(tier=tier, expires_at=expiry)


@router.post(
    "",
    response_model=SubscriptionStatusResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def subscribe_to_vip(
    body: VipSubscriptionRequest,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> SubscriptionStatusResponse:
    plan_exists = db.execute(
        text(
            """
            SELECT name, duration_days, price_kobo
            FROM subscription_plans WHERE id = :plan_id AND active = TRUE
            """
        ),
        {"plan_id": body.plan_id},
    ).mappings().first()
    if plan_exists is None:
        raise ApiException("PLAN_NOT_FOUND", "That plan is not available.", 404)
    lock_clause = " FOR UPDATE" if db.get_bind().dialect.name == "mysql" else ""
    profile = db.execute(
        text(
            f"""
            SELECT vip_expires_at FROM profiles WHERE account_id = :account_id
            {lock_clause}
            """
        ),
        {"account_id": account.account_id},
    ).mappings().first()
    if profile is None:
        raise ApiException("NO_PROFILE", "Finish onboarding before subscribing.", 404)
    now = datetime.now(UTC)
    current_expiry = profile["vip_expires_at"]
    if isinstance(current_expiry, str):
        current_expiry = datetime.fromisoformat(current_expiry)
    if current_expiry is not None and current_expiry.tzinfo is None:
        current_expiry = current_expiry.replace(tzinfo=UTC)
    base = current_expiry if current_expiry is not None and current_expiry > now else now
    expires_at = base + timedelta(days=int(plan_exists["duration_days"]))
    price_kobo = int(plan_exists["price_kobo"])
    debit_wallet(
        db,
        account.account_id,
        price_kobo,
        transaction_type="vip-subscription",
        description=f"VIP subscription — {plan_exists['name']}",
    )
    db.execute(
        text(
            """
            UPDATE profiles
            SET subscription_tier = 'vip', vip_expires_at = :expires_at
            WHERE account_id = :account_id
            """
        ),
        {
            "account_id": account.account_id,
            "expires_at": expires_at.astimezone(UTC).replace(tzinfo=None),
        },
    )
    record_audit_event(
        db,
        request,
        event_type="subscription.vip_purchased",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
        metadata={"planId": body.plan_id, "priceKobo": price_kobo},
    )
    db.commit()
    return SubscriptionStatusResponse(tier="vip", expires_at=expires_at)
