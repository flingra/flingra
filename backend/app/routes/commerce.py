import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.config import Settings
from app.dependencies import db_session
from app.errors import ApiException, ServiceUnavailable
from app.feature_schemas import (
    GiftPurchaseRequest,
    GiftSendRequest,
    GiftTypeResponse,
    OwnedGiftResponse,
    ReceivedGiftResponse,
    WalletTopUpRequest,
    WalletTopUpVerificationRequest,
    WalletTransactionResponse,
)
from app.paystack import initialize_transaction, verify_transaction, verify_webhook_signature
from app.routes.auth import IdentityVerifiedAccount, get_app_settings, require_csrf
from app.routes.profiles import (
    _effective_subscription_tier,
    _require_discovery_ready,
    _visible_profile_rows,
)
from app.routes.payouts import settle_paystack_transfer
from app.wallet import credit_wallet, debit_wallet, get_wallet_balance_kobo, require_wallet_ready

router = APIRouter(tags=["wallet"])
DbSession = Annotated[Session, Depends(db_session)]
SettingsDependency = Annotated[Settings, Depends(get_app_settings)]
KoboPerNaira = 100


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _require_ready(account: dict[str, Any]) -> None:
    require_wallet_ready(account)


@router.get("/wallet/balance")
def get_wallet_balance(
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> dict[str, int]:
    _require_ready(account)
    balance = get_wallet_balance_kobo(db, account.account_id) // KoboPerNaira
    record_audit_event(
        db,
        request,
        event_type="wallet.balance_viewed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
    )
    db.commit()
    return {"balanceNaira": balance}


@router.get("/wallet/transactions", response_model=list[WalletTransactionResponse])
def list_wallet_transactions(
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> list[WalletTransactionResponse]:
    _require_ready(account)
    rows = db.execute(
        text(
            """
            SELECT id, transaction_type, amount_kobo, description, status, created_at
            FROM wallet_transactions
            WHERE account_id = :account_id
            ORDER BY created_at DESC, id DESC
            LIMIT 200
            """
        ),
        {"account_id": account.account_id},
    ).mappings()
    transactions = [
        WalletTransactionResponse(
            id=str(row["id"]),
            type=row["transaction_type"],
            amount_naira=int(row["amount_kobo"]) // KoboPerNaira,
            description=row["description"],
            status=row["status"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
    record_audit_event(
        db,
        request,
        event_type="wallet.transactions_viewed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
    )
    db.commit()
    return transactions


@router.post(
    "/wallet/top-ups",
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_wallet_top_up(
    body: WalletTopUpRequest,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> dict[str, str | int]:
    _require_ready(account)
    contact = db.execute(
        text("SELECT email FROM accounts WHERE id = :account_id"),
        {"account_id": account.account_id},
    ).scalar_one_or_none()
    if not contact:
        raise ApiException(
            "PAYMENT_CONTACT_REQUIRED",
            "Add a verified email address before funding your wallet.",
            400,
        )

    amount_kobo = body.amount_naira * KoboPerNaira
    reference = f"flingra_{uuid.uuid4().hex}"
    intent_id = uuid.uuid4().hex
    db.execute(
        text(
            """
            INSERT INTO wallet_payment_intents (
                id, account_id, reference, amount_kobo, currency, status, created_at, updated_at
            )
            VALUES (
                :id, :account_id, :reference, :amount_kobo, 'NGN', 'initializing', :now, :now
            )
            """
        ),
        {
            "id": intent_id,
            "account_id": account.account_id,
            "reference": reference,
            "amount_kobo": amount_kobo,
            "now": _now(),
        },
    )
    db.commit()
    try:
        authorization_url = initialize_transaction(
            settings,
            email=str(contact),
            amount_kobo=amount_kobo,
            reference=reference,
            callback_url=f"{settings.frontend_url.rstrip('/')}/wallet",
        )
    except ServiceUnavailable:
        db.execute(
            text(
                """
                UPDATE wallet_payment_intents
                SET status = 'failed', updated_at = :now
                WHERE id = :id AND status = 'initializing'
                """
            ),
            {"id": intent_id, "now": _now()},
        )
        db.commit()
        raise

    db.execute(
        text(
            """
            UPDATE wallet_payment_intents
            SET status = 'pending', authorization_url = :authorization_url,
                updated_at = :now
            WHERE id = :id AND status = 'initializing'
            """
        ),
        {
            "id": intent_id,
            "authorization_url": authorization_url,
            "now": _now(),
        },
    )
    record_audit_event(
        db,
        request,
        event_type="wallet.top_up_initialized",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
        metadata={"reference": reference, "amount_kobo": amount_kobo},
    )
    db.commit()
    return {
        "reference": reference,
        "authorizationUrl": authorization_url,
        "amountNaira": body.amount_naira,
    }


def _settle_wallet_payment(
    db: Session,
    request: Request | None,
    *,
    reference: str,
    verified_payment: dict[str, Any],
) -> bool:
    suffix = " FOR UPDATE" if db.get_bind().dialect.name != "sqlite" else ""
    intent = db.execute(
        text(
            """
            SELECT id, account_id, amount_kobo, currency, status
            FROM wallet_payment_intents
            WHERE reference = :reference
            """
            + suffix
        ),
        {"reference": reference},
    ).mappings().first()
    if intent is None or intent["status"] == "settled":
        return False
    if intent["status"] not in {"pending", "initializing"}:
        return False
    if (
        verified_payment.get("status") != "success"
        or verified_payment.get("reference") != reference
        or verified_payment.get("currency") != intent["currency"]
        or verified_payment.get("amount") != int(intent["amount_kobo"])
    ):
        raise ApiException(
            "PAYMENT_VERIFICATION_FAILED",
            "The payment could not be verified against this wallet top-up.",
            409,
        )

    credit_wallet(
        db,
        str(intent["account_id"]),
        int(intent["amount_kobo"]),
        transaction_type="wallet-top-up",
        description="Wallet funded via Paystack",
    )
    now = _now()
    db.execute(
        text(
            """
            UPDATE wallet_payment_intents
            SET status = 'settled', settled_at = :now, updated_at = :now
            WHERE id = :id AND status IN ('pending', 'initializing')
            """
        ),
        {"id": intent["id"], "now": now},
    )
    record_audit_event(
        db,
        request,
        event_type="wallet.top_up_settled",
        actor_type="system",
        actor_id=None,
        subject_account_id=str(intent["account_id"]),
        outcome="success",
        metadata={"reference": reference, "amount_kobo": int(intent["amount_kobo"])},
    )
    db.commit()
    return True


@router.post("/wallet/top-ups/verify", dependencies=[Depends(require_csrf)])
def verify_wallet_top_up(
    body: WalletTopUpVerificationRequest,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> dict[str, str | int]:
    _require_ready(account)
    intent = db.execute(
        text(
            """
            SELECT amount_kobo, status
            FROM wallet_payment_intents
            WHERE reference = :reference AND account_id = :account_id
            """
        ),
        {"reference": body.reference, "account_id": account.account_id},
    ).mappings().first()
    if intent is None:
        raise ApiException("PAYMENT_NOT_FOUND", "That wallet payment was not found.", 404)
    if intent["status"] == "settled":
        return {
            "status": "success",
            "balanceNaira": get_wallet_balance_kobo(db, account.account_id) // KoboPerNaira,
        }
    if intent["status"] not in {"pending", "initializing"}:
        raise ApiException("PAYMENT_NOT_PENDING", "This wallet payment is no longer pending.", 409)

    verified = verify_transaction(settings, body.reference)
    if verified.get("status") != "success":
        return {"status": "pending", "reference": body.reference}
    _settle_wallet_payment(db, request, reference=body.reference, verified_payment=verified)
    return {
        "status": "success",
        "balanceNaira": get_wallet_balance_kobo(db, account.account_id) // KoboPerNaira,
    }


@router.post("/webhooks/paystack")
async def paystack_webhook(request: Request, db: DbSession, settings: SettingsDependency) -> dict[str, str]:
    raw_body = await request.body()
    signature = request.headers.get("x-paystack-signature")
    if not verify_webhook_signature(settings, raw_body, signature):
        raise ApiException("INVALID_WEBHOOK_SIGNATURE", "Webhook signature is invalid.", 401)
    try:
        event = await request.json()
    except ValueError as exc:
        raise ApiException("INVALID_WEBHOOK", "Webhook payload is invalid.", 400) from exc
    if not isinstance(event, dict):
        return {"status": "ignored"}
    event_type = event.get("event")
    data = event.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("reference"), str):
        return {"status": "ignored"}
    reference = data["reference"]
    if event_type in {"transfer.success", "transfer.failed", "transfer.reversed"}:
        settled = settle_paystack_transfer(db, request, str(event_type), data)
        return {"status": "processed" if settled else "ignored"}
    if event_type != "charge.success":
        return {"status": "ignored"}
    intent = db.execute(
        text("SELECT status FROM wallet_payment_intents WHERE reference = :reference"),
        {"reference": reference},
    ).scalar_one_or_none()
    if intent is None or intent == "settled":
        return {"status": "ignored"}

    verified = verify_transaction(settings, reference)
    if verified.get("status") != "success":
        return {"status": "ignored"}
    settled = _settle_wallet_payment(
        db,
        request,
        reference=reference,
        verified_payment=verified,
    )
    return {"status": "processed" if settled else "ignored"}


@router.get("/wallet/gifts/catalog", response_model=list[GiftTypeResponse])
def list_gift_catalog(db: DbSession) -> list[GiftTypeResponse]:
    rows = db.execute(
        text(
            """
            SELECT id, name, emoji, price_kobo
            FROM gift_catalog
            WHERE active = TRUE
            ORDER BY price_kobo, id
            """
        )
    ).mappings()
    return [
        GiftTypeResponse(
            id=row["id"],
            name=row["name"],
            emoji=row["emoji"],
            price_naira=int(row["price_kobo"]) // KoboPerNaira,
        )
        for row in rows
    ]


@router.get("/wallet/gifts/owned")
def list_owned_gifts(
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> list[dict[str, object]]:
    _require_ready(account)
    rows = db.execute(
        text(
            """
            SELECT g.id, g.name, g.emoji, g.price_kobo, i.quantity
            FROM gift_inventory i
            JOIN gift_catalog g ON g.id = i.gift_type_id
            WHERE i.account_id = :account_id AND i.quantity > 0 AND g.active = TRUE
            ORDER BY g.price_kobo, g.id
            """
        ),
        {"account_id": account.account_id},
    ).mappings()
    gifts = [
        {
            "gift": {
                "id": row["id"],
                "name": row["name"],
                "emoji": row["emoji"],
                "priceNaira": int(row["price_kobo"]) // KoboPerNaira,
            },
            "quantity": int(row["quantity"]),
        }
        for row in rows
    ]
    record_audit_event(
        db,
        request,
        event_type="wallet.gift_inventory_viewed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
    )
    db.commit()
    return gifts


@router.post(
    "/wallet/gifts/buy",
    dependencies=[Depends(require_csrf)],
)
def buy_gift(
    body: GiftPurchaseRequest,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> dict[str, int]:
    _require_ready(account)
    gift = db.execute(
        text("SELECT name, emoji, price_kobo FROM gift_catalog WHERE id = :id AND active = TRUE"),
        {"id": body.gift_type_id},
    ).mappings().first()
    if gift is None:
        raise ApiException("GIFT_NOT_FOUND", "That gift is not available.", 404)
    cost = int(gift["price_kobo"]) * body.quantity
    balance = debit_wallet(
        db,
        account.account_id,
        cost,
        transaction_type="gift-purchase",
        description=f"Bought {body.quantity}× {gift['name']}",
    )
    db.execute(
        text(
            """
            INSERT INTO gift_inventory (account_id, gift_type_id, quantity)
            VALUES (:account_id, :gift_type_id, :quantity)
            ON DUPLICATE KEY UPDATE quantity = quantity + VALUES(quantity)
            """
            if db.get_bind().dialect.name != "sqlite"
            else """
            INSERT INTO gift_inventory (account_id, gift_type_id, quantity)
            VALUES (:account_id, :gift_type_id, :quantity)
            ON CONFLICT(account_id, gift_type_id)
            DO UPDATE SET quantity = gift_inventory.quantity + excluded.quantity
            """
        ),
        {
            "account_id": account.account_id,
            "gift_type_id": body.gift_type_id,
            "quantity": body.quantity,
        },
    )
    record_audit_event(
        db,
        request,
        event_type="wallet.gift_purchased",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
        metadata={"giftTypeId": body.gift_type_id, "quantity": body.quantity},
    )
    db.commit()
    return {"balanceNaira": balance // KoboPerNaira}


@router.post(
    "/wallet/gifts/{gift_type_id}/spend",
    dependencies=[Depends(require_csrf)],
)
def send_gift(
    gift_type_id: str,
    body: GiftSendRequest,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> dict[str, str]:
    _require_ready(account)
    profile = db.execute(
        text(
            """
            SELECT identity, subscription_tier, vip_expires_at
            FROM profiles WHERE account_id = :account_id
            """
        ),
        {"account_id": account.account_id},
    ).mappings().first()
    if profile is None:
        raise ApiException("NO_PROFILE", "Finish onboarding before sending gifts.", 404)
    targets = _visible_profile_rows(
        db,
        account.account_id,
        profile["identity"],
        settings.demo_profiles_enabled,
        profile_id=body.recipient_id,
    )
    if not targets:
        raise ApiException("PROFILE_NOT_FOUND", "This member is unavailable.", 404)
    target = targets[0]
    viewer_tier = _effective_subscription_tier(
        profile["subscription_tier"],
        profile["vip_expires_at"],
    )
    target_tier = _effective_subscription_tier(
        target["subscription_tier"],
        target["vip_expires_at"],
    )
    if target_tier == "vip" and viewer_tier != "vip":
        raise ApiException("VIP_REQUIRED", "Upgrade to VIP to interact with this member.", 403)
    gift = db.execute(
        text("SELECT name, price_kobo FROM gift_catalog WHERE id = :id AND active = TRUE"),
        {"id": gift_type_id},
    ).mappings().first()
    if gift is None:
        raise ApiException("GIFT_NOT_FOUND", "That gift is not available.", 404)
    inventory = db.execute(
        text(
            """
            UPDATE gift_inventory SET quantity = quantity - 1
            WHERE account_id = :account_id AND gift_type_id = :gift_type_id AND quantity > 0
            """
        ),
        {"account_id": account.account_id, "gift_type_id": gift_type_id},
    )
    if inventory.rowcount != 1:
        raise ApiException("GIFT_NOT_OWNED", f"You don't have a {gift['name']} to send.", 409)
    received_id = uuid.uuid4().hex
    db.execute(
        text(
            """
            INSERT INTO received_gifts (
                id, recipient_id, sender_id, gift_type_id, value_kobo, redeemed, created_at
            )
            VALUES (
                :id, :recipient_id, :sender_id, :gift_type_id, :value_kobo, FALSE, :created_at
            )
            """
        ),
        {
            "id": received_id,
            "recipient_id": body.recipient_id,
            "sender_id": account.account_id,
            "gift_type_id": gift_type_id,
            "value_kobo": gift["price_kobo"],
            "created_at": _now(),
        },
    )
    record_audit_event(
        db,
        request,
        event_type="wallet.gift_sent",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=body.recipient_id,
        outcome="success",
        metadata={"giftTypeId": gift_type_id, "giftId": received_id},
    )
    db.commit()
    return {"giftId": received_id, "name": gift["name"], "emoji": gift["emoji"]}


@router.get("/wallet/gifts/received", response_model=list[ReceivedGiftResponse])
def list_received_gifts(
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> list[ReceivedGiftResponse]:
    _require_ready(account)
    rows = db.execute(
        text(
            """
            SELECT g.id, g.gift_type_id, g.sender_id, p.display_name AS sender_name,
                   g.value_kobo, g.redeemed, g.created_at
            FROM received_gifts g
            JOIN profiles p ON p.account_id = g.sender_id
            WHERE g.recipient_id = :account_id
            ORDER BY g.created_at DESC, g.id
            """
        ),
        {"account_id": account.account_id},
    ).mappings()
    gifts = [
        ReceivedGiftResponse(
            id=str(row["id"]),
            gift_type_id=row["gift_type_id"],
            from_id=str(row["sender_id"]),
            from_name=row["sender_name"],
            value_naira=int(row["value_kobo"]) // KoboPerNaira,
            redeemed=bool(row["redeemed"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]
    record_audit_event(
        db,
        request,
        event_type="wallet.received_gifts_viewed",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
    )
    db.commit()
    return gifts


def _redeem_gifts(
    request: Request,
    account_id: str,
    db: Session,
    gift_ids: list[str] | None = None,
) -> int:
    where_ids = ""
    parameters: dict[str, object] = {"account_id": account_id}
    if gift_ids is not None:
        if not gift_ids:
            return 0
        where_ids = "AND id IN :gift_ids"
        parameters["gift_ids"] = gift_ids
    statement = text(
            f"""
            SELECT id, value_kobo FROM received_gifts
            WHERE recipient_id = :account_id AND redeemed = FALSE {where_ids}
            """
        )
    if gift_ids is not None:
        statement = statement.bindparams(bindparam("gift_ids", expanding=True))
    rows = db.execute(statement, parameters).mappings().all()
    if not rows:
        return 0
    redeemed_rows = []
    for row in rows:
        result = db.execute(
            text(
                """
                UPDATE received_gifts SET redeemed = TRUE
                WHERE id = :gift_id AND recipient_id = :account_id AND redeemed = FALSE
                """
            ),
            {"gift_id": row["id"], "account_id": account_id},
        )
        if result.rowcount == 1:
            redeemed_rows.append(row)
    if not redeemed_rows:
        return 0
    total_kobo = sum(int(row["value_kobo"]) for row in redeemed_rows)
    credit_wallet(
        db,
        account_id,
        total_kobo,
        transaction_type="redemption",
        description=f"Redeemed {len(redeemed_rows)} gift{'s' if len(redeemed_rows) != 1 else ''}",
    )
    record_audit_event(
        db,
        request,
        event_type="wallet.gifts_redeemed",
        actor_type="user",
        actor_id=account_id,
        subject_account_id=account_id,
        outcome="success",
        metadata={"giftCount": len(redeemed_rows)},
    )
    return total_kobo


@router.post(
    "/wallet/gifts/{gift_id}/redeem",
    status_code=204,
    dependencies=[Depends(require_csrf)],
)
def redeem_gift(
    gift_id: str,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> None:
    _require_ready(account)
    total = _redeem_gifts(request, account.account_id, db, [gift_id])
    if total == 0:
        exists = db.execute(
            text("SELECT 1 FROM received_gifts WHERE id = :id AND recipient_id = :account_id"),
            {"id": gift_id, "account_id": account.account_id},
        ).first()
        if exists is None:
            raise ApiException("GIFT_NOT_FOUND", "This gift is unavailable.", 404)
        raise ApiException("GIFT_ALREADY_REDEEMED", "This gift has already been redeemed.", 409)
    db.commit()


@router.post(
    "/wallet/gifts/redeem-all",
    dependencies=[Depends(require_csrf)],
)
def redeem_all_gifts(
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> dict[str, int]:
    _require_ready(account)
    total = _redeem_gifts(request, account.account_id, db)
    db.commit()
    return {"amountNaira": total // KoboPerNaira}
