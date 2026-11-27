import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.audit import record_audit_event
from app.config import Settings
from app.dependencies import db_session
from app.errors import ApiException, ServiceUnavailable
from app.feature_schemas import (
    CallCreditPurchaseRequest,
    CallSessionResponse,
    CallStartRequest,
    LiveKitConnectionResponse,
)
from app.livekit import create_room_token, delete_room
from app.realtime import enqueue_realtime_event
from app.routes.auth import IdentityVerifiedAccount, get_app_settings, require_csrf
from app.routes.profiles import _effective_subscription_tier, _require_discovery_ready, _visible_profile_rows
from app.wallet import (
    debit_wallet,
    ensure_wallet_account,
    get_wallet_balance_kobo,
    require_wallet_ready,
)

router = APIRouter(prefix="/calls", tags=["calls"])
DbSession = Annotated[Session, Depends(db_session)]
SettingsDependency = Annotated[Settings, Depends(get_app_settings)]
CALL_TICK_SECONDS = 60
CALL_TICK_CREDITS = 1
CALL_PACKAGES = (10, 15, 30)
RING_TIMEOUT = timedelta(seconds=30)
ACTIVITY_TIMEOUT = timedelta(seconds=30)
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _as_datetime(value: datetime | str) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def _ensure_credit_account(db: Session, account_id: str) -> None:
    if db.get_bind().dialect.name == "sqlite":
        db.execute(
            text(
                """
                INSERT INTO call_credit_accounts (account_id, balance)
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
                INSERT INTO call_credit_accounts (account_id, balance)
                VALUES (:account_id, 0)
                ON DUPLICATE KEY UPDATE account_id = VALUES(account_id)
                """
            ),
            {"account_id": account_id},
        )


def _credit_balance(db: Session, account_id: str) -> int:
    _ensure_credit_account(db, account_id)
    return int(
        db.execute(
            text("SELECT balance FROM call_credit_accounts WHERE account_id = :account_id"),
            {"account_id": account_id},
        ).scalar_one()
    )


def _lock_call_accounts(db: Session, account_ids: tuple[str, ...]) -> None:
    if db.get_bind().dialect.name == "sqlite":
        return
    db.execute(
        text("SELECT id FROM accounts WHERE id IN :account_ids ORDER BY id FOR UPDATE")
        .bindparams(bindparam("account_ids", expanding=True)),
        {"account_ids": tuple(sorted(set(account_ids)))},
    ).all()


def _ensure_no_active_call(
    db: Session,
    account_ids: tuple[str, ...],
    *,
    exclude_call_id: str | None = None,
) -> None:
    _lock_call_accounts(db, account_ids)
    row = db.execute(
        text(
            """
            SELECT id FROM call_sessions
            WHERE status IN ('ringing', 'connecting', 'active')
              AND (caller_id IN :account_ids OR callee_id IN :account_ids)
              AND (:exclude_call_id IS NULL OR id != :exclude_call_id)
            LIMIT 1
            """
        ).bindparams(bindparam("account_ids", expanding=True)),
        {"account_ids": account_ids, "exclude_call_id": exclude_call_id},
    ).first()
    if row is not None:
        raise ApiException("CALL_ALREADY_ACTIVE", "One of these members is already in a call.", 409)


def _validate_idempotency_key(key: str | None) -> str:
    if not key or not IDEMPOTENCY_PATTERN.fullmatch(key):
        raise ApiException("IDEMPOTENCY_KEY_REQUIRED", "Provide a valid Idempotency-Key header.", 400)
    return key


def _price_naira(db: Session) -> int:
    price = db.execute(text("SELECT price_naira FROM call_credit_pricing WHERE id = 1")).scalar_one_or_none()
    if price is None:
        raise ServiceUnavailable("Call-credit pricing is not configured.")
    return int(price)


def _account_profile(db: Session, account_id: str) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT identity, display_name, photos, subscription_tier, vip_expires_at
            FROM profiles WHERE account_id = :account_id
            """
        ),
        {"account_id": account_id},
    ).mappings().first()
    if row is None:
        raise ApiException("NO_PROFILE", "Finish your profile before making a call.", 404)
    return dict(row)


def _first_photo(value: Any) -> str:
    photos = json.loads(value) if isinstance(value, str) else value
    return str(photos[0]) if isinstance(photos, list) and photos and isinstance(photos[0], str) else ""


def _call_row(db: Session, call_id: str, account_id: str, *, lock: bool = False) -> dict[str, Any]:
    suffix = " FOR UPDATE" if lock and db.get_bind().dialect.name != "sqlite" else ""
    row = db.execute(
        text(
            """
            SELECT id, caller_id, callee_id, payer_id, room_name, call_type, status,
                   started_at, last_billed_at, last_activity_at, ended_at, billed_ticks,
                   caller_connected_at, callee_connected_at, room_closed_at, created_at
            FROM call_sessions
            WHERE id = :call_id
              AND (caller_id = :account_id OR callee_id = :account_id)
            """
            + suffix
        ),
        {"call_id": call_id, "account_id": account_id},
    ).mappings().first()
    if row is None:
        raise ApiException("CALL_NOT_FOUND", "This call is unavailable.", 404)
    return dict(row)


def _response(
    row: dict[str, Any],
    *,
    settings: Settings | None = None,
    account_id: str | None = None,
    credit_balance: int | None = None,
) -> CallSessionResponse:
    token_url = token = None
    if settings is not None and account_id is not None and row["status"] in {"ringing", "connecting", "active"}:
        token_url, token = create_room_token(
            settings,
            room_name=str(row["room_name"]),
            identity=account_id,
            can_publish=True,
        )
    return CallSessionResponse(
        call_id=str(row["id"]),
        caller_id=str(row["caller_id"]),
        callee_id=str(row["callee_id"]),
        call_type=row["call_type"],
        status=row["status"],
        livekit_url=token_url,
        token=token,
        credit_balance=credit_balance,
    )


def _queue_call_event(db: Session, row: dict[str, Any], event_type: str, *, reason: str | None = None) -> None:
    payload: dict[str, Any] = {
        "callId": str(row["id"]),
        "callerId": str(row["caller_id"]),
        "calleeId": str(row["callee_id"]),
        "status": row["status"],
    }
    if reason:
        payload["reason"] = reason
    enqueue_realtime_event(db, str(row["caller_id"]), event_type, payload)
    enqueue_realtime_event(db, str(row["callee_id"]), event_type, payload)


def _spend_ticks(db: Session, row: dict[str, Any], ticks: int) -> tuple[int, int]:
    payer_id = row["payer_id"]
    if not payer_id or ticks <= 0:
        return 0, _credit_balance(db, str(payer_id)) if payer_id else 0
    payer_id = str(payer_id)
    _ensure_credit_account(db, payer_id)
    balance = _credit_balance(db, payer_id)
    remaining = min(balance, ticks)
    charged = 0
    while remaining > 0:
        result = db.execute(
            text(
                """
                UPDATE call_credit_accounts
                SET balance = balance - :ticks
                WHERE account_id = :account_id AND balance >= :ticks
                """
            ),
            {"account_id": payer_id, "ticks": remaining},
        )
        if result.rowcount == 1:
            charged = remaining
            break
        balance = _credit_balance(db, payer_id)
        remaining = min(balance, remaining - 1)
    if charged <= 0:
        return 0, _credit_balance(db, payer_id)

    start_tick = int(row["billed_ticks"])
    now = _now()
    for offset in range(1, remaining + 1):
        db.execute(
            text(
                """
                INSERT INTO call_credit_transactions (
                    id, account_id, call_id, tick_number, transaction_type,
                    amount, description, created_at
                )
                VALUES (
                    :id, :account_id, :call_id, :tick_number, 'call-credit-spend',
                        -:credit_amount, 'Call credit used for an active call', :created_at
                )
                """
            ),
            {
                "id": uuid.uuid4().hex,
                "account_id": payer_id,
                "call_id": row["id"],
                "tick_number": start_tick + offset,
                "credit_amount": CALL_TICK_CREDITS,
                "created_at": now,
            },
        )
    return charged, balance - charged


def _settle_due_ticks(db: Session, row: dict[str, Any], cutoff: datetime) -> tuple[bool, int | None]:
    if row["status"] != "active" or row["last_billed_at"] is None:
        return False, None
    last_billed = _as_datetime(row["last_billed_at"])
    elapsed_seconds = (cutoff - last_billed).total_seconds()
    due = max(0, int((elapsed_seconds - 1) // CALL_TICK_SECONDS))
    stale = (
        row["last_activity_at"] is not None
        and _as_datetime(row["last_activity_at"]) < _now() - ACTIVITY_TIMEOUT
    )
    balance: int | None = _credit_balance(db, str(row["payer_id"])) if row["payer_id"] else None
    if due and row["payer_id"]:
        new_ticks, balance = _spend_ticks(db, row, due)
        billed_at = last_billed + timedelta(seconds=new_ticks * CALL_TICK_SECONDS)
        ended = new_ticks < due or stale
        db.execute(
            text(
                """
                UPDATE call_sessions
                SET billed_ticks = :billed_ticks, last_billed_at = :last_billed_at,
                    last_activity_at = :last_activity_at, status = :status, ended_at = :ended_at
                WHERE id = :call_id AND status = 'active'
                """
            ),
            {
                "call_id": row["id"],
                "billed_ticks": int(row["billed_ticks"]) + new_ticks,
                "last_billed_at": billed_at,
                "last_activity_at": row["last_activity_at"],
                "status": "ended" if ended else "active",
                "ended_at": cutoff if ended else None,
            },
        )
        row["billed_ticks"] = int(row["billed_ticks"]) + new_ticks
        row["last_billed_at"] = billed_at
        row["status"] = "ended" if ended else "active"
        row["ended_at"] = cutoff if ended else None
        if ended:
            _queue_call_event(
                db,
                row,
                "call.ended",
                reason="connection_timeout" if stale else "insufficient_credits",
            )
        return ended, balance

    if due:
        row["last_billed_at"] = last_billed + timedelta(seconds=due * CALL_TICK_SECONDS)
        db.execute(
            text(
                """
                UPDATE call_sessions
                SET last_billed_at = :last_billed_at
                WHERE id = :call_id AND status = 'active'
                """
            ),
            {"call_id": row["id"], "last_billed_at": row["last_billed_at"]},
        )

    if stale:
        db.execute(
            text(
                """
                UPDATE call_sessions SET status = 'ended', ended_at = :now
                WHERE id = :call_id AND status = 'active'
                """
            ),
            {"call_id": row["id"], "now": _now()},
        )
        row["status"] = "ended"
        row["ended_at"] = _now()
        _queue_call_event(db, row, "call.ended", reason="connection_timeout")
    return stale, balance


def process_call_lifecycle(db: Session, settings: Settings, *, limit: int = 100) -> int:
    now = _now()
    rows = db.execute(
        text(
            """
            SELECT id, caller_id, callee_id, payer_id, room_name, call_type, status,
                   started_at, last_billed_at, last_activity_at, ended_at, billed_ticks,
                   caller_connected_at, callee_connected_at, room_closed_at, created_at
            FROM call_sessions
            WHERE (status = 'ringing' AND created_at < :ring_cutoff)
               OR (status = 'connecting' AND created_at < :ring_cutoff)
               OR (status = 'active' AND last_billed_at <= :billing_cutoff)
               OR (status = 'active' AND last_activity_at < :activity_cutoff)
               OR (status IN ('ended', 'declined') AND room_closed_at IS NULL)
            ORDER BY created_at, id
            LIMIT :limit
            """
            + (" FOR UPDATE SKIP LOCKED" if db.get_bind().dialect.name != "sqlite" else "")
        ),
        {
            "ring_cutoff": now - RING_TIMEOUT,
            "billing_cutoff": now - timedelta(seconds=CALL_TICK_SECONDS),
            "activity_cutoff": now - ACTIVITY_TIMEOUT,
            "limit": limit,
        },
    ).mappings().all()
    processed = 0
    rooms_to_close: list[tuple[str, str]] = []
    for value in rows:
        row = dict(value)
        if row["status"] in {"ringing", "connecting"}:
            previous_status = row["status"]
            db.execute(
                text("UPDATE call_sessions SET status = 'ended', ended_at = :now WHERE id = :id AND status = :status"),
                {"now": now, "id": row["id"], "status": previous_status},
            )
            row["status"] = "ended"
            row["ended_at"] = now
            reason = "no_answer" if previous_status == "ringing" else "connection_timeout"
            _queue_call_event(db, row, "call.ended", reason=reason)
        elif row["status"] == "active":
            cutoff = now
            if row["last_activity_at"] is not None:
                activity = _as_datetime(row["last_activity_at"])
                if activity < now - ACTIVITY_TIMEOUT:
                    cutoff = activity
            _settle_due_ticks(db, row, cutoff)
        if row["status"] in {"ended", "declined"} and row["room_closed_at"] is None:
            rooms_to_close.append((str(row["id"]), str(row["room_name"])))
        processed += 1
    db.commit()
    cleanup_failures: list[ServiceUnavailable] = []
    for call_id, room_name in rooms_to_close:
        try:
            delete_room(settings, room_name)
        except ServiceUnavailable as exc:
            cleanup_failures.append(exc)
            continue
        db.execute(
            text("UPDATE call_sessions SET room_closed_at = :now WHERE id = :id"),
            {"now": _now(), "id": call_id},
        )
    db.commit()
    if cleanup_failures:
        raise ServiceUnavailable(
            f"LiveKit cleanup failed for {len(cleanup_failures)} call room(s); they will be retried."
        )
    return processed


@router.get("/coin-price")
def get_call_credit_price(
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> dict[str, int]:
    return {"priceNaira": _price_naira(db)}


@router.get("/coin-packages")
def list_call_credit_packages(
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> list[dict[str, int]]:
    price = _price_naira(db)
    return [{"coins": coins, "priceNaira": coins * price} for coins in CALL_PACKAGES]


@router.get("/credits")
def get_call_credit_balance(
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> dict[str, int]:
    require_wallet_ready(account)
    return {"coins": _credit_balance(db, account.account_id)}


@router.post(
    "/credits/purchase",
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def purchase_call_credits(
    body: CallCreditPurchaseRequest,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, int]:
    require_wallet_ready(account)
    key = _validate_idempotency_key(idempotency_key)
    ensure_wallet_account(db, account.account_id)
    if db.get_bind().dialect.name != "sqlite":
        db.execute(
            text("SELECT account_id FROM wallet_accounts WHERE account_id = :id FOR UPDATE"),
            {"id": account.account_id},
        ).first()
    profile = _account_profile(db, account.account_id)
    if profile["identity"] != "man":
        raise ApiException("BUYER_RESTRICTED", "Only male accounts can buy call credits.", 403)
    if body.coins not in CALL_PACKAGES:
        raise ApiException("INVALID_AMOUNT", "Choose one of the available call-credit packages.", 400)
    existing = db.execute(
        text(
            """
            SELECT id, amount, transaction_type FROM call_credit_transactions
            WHERE account_id = :account_id AND idempotency_key = :idempotency_key
            """
        ),
        {"account_id": account.account_id, "idempotency_key": key},
    ).mappings().first()
    if existing is not None:
        if existing["transaction_type"] != "purchase" or int(existing["amount"]) != body.coins:
            raise ApiException("IDEMPOTENCY_KEY_REUSED", "Use a new key for a different purchase.", 409)
        return {
            "coins": _credit_balance(db, account.account_id),
            "balanceNaira": get_wallet_balance_kobo(db, account.account_id) // 100,
        }
    cost_kobo = body.coins * _price_naira(db) * 100
    wallet_balance = debit_wallet(
        db,
        account.account_id,
        cost_kobo,
        transaction_type="coin-purchase",
        description=f"Bought {body.coins} call credit coins",
    )
    _ensure_credit_account(db, account.account_id)
    db.execute(
        text("UPDATE call_credit_accounts SET balance = balance + :coins WHERE account_id = :account_id"),
        {"coins": body.coins, "account_id": account.account_id},
    )
    db.execute(
        text(
            """
            INSERT INTO call_credit_transactions (
                id, account_id, transaction_type, amount, description, idempotency_key, created_at
            )
            VALUES (
                :id, :account_id, 'purchase', :amount, :description, :idempotency_key, :created_at
            )
            """
        ),
        {
            "id": uuid.uuid4().hex,
            "account_id": account.account_id,
            "amount": body.coins,
            "description": f"Bought {body.coins} call credit coins",
            "idempotency_key": key,
            "created_at": _now(),
        },
    )
    record_audit_event(
        db,
        request,
        event_type="call_credits.purchased",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=account.account_id,
        outcome="success",
        metadata={"coins": body.coins, "amountKobo": cost_kobo},
    )
    db.commit()
    return {
        "coins": _credit_balance(db, account.account_id),
        "balanceNaira": wallet_balance // 100,
    }


@router.post("", response_model=CallSessionResponse, status_code=201, dependencies=[Depends(require_csrf)])
def start_call(
    body: CallStartRequest,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> CallSessionResponse:
    require_wallet_ready(account)
    _require_discovery_ready(account)
    key = _validate_idempotency_key(idempotency_key)
    _lock_call_accounts(db, (account.account_id, body.target_id))
    existing = db.execute(
        text(
            """
            SELECT id, caller_id, callee_id, payer_id, room_name, call_type, status,
                   started_at, last_billed_at, last_activity_at, ended_at, billed_ticks,
                   caller_connected_at, callee_connected_at, room_closed_at, created_at
            FROM call_sessions
            WHERE caller_id = :caller_id AND idempotency_key = :idempotency_key
            """
        ),
        {"caller_id": account.account_id, "idempotency_key": key},
    ).mappings().first()
    if existing is not None:
        row = dict(existing)
        if str(row["callee_id"]) != body.target_id or row["call_type"] != body.call_type:
            raise ApiException("IDEMPOTENCY_KEY_REUSED", "Use a new key for a different call.", 409)
        return _response(
            row,
            settings=settings,
            account_id=account.account_id,
            credit_balance=_credit_balance(db, str(row["payer_id"])) if row["payer_id"] else None,
        )

    _account_profile(db, account.account_id)
    viewer = db.execute(
        text("SELECT identity, subscription_tier, vip_expires_at FROM profiles WHERE account_id = :id"),
        {"id": account.account_id},
    ).mappings().one()
    targets = _visible_profile_rows(
        db,
        account.account_id,
        viewer["identity"],
        settings.demo_profiles_enabled,
        profile_id=body.target_id,
    )
    if not targets:
        raise ApiException("PROFILE_NOT_FOUND", "This member is unavailable.", 404)
    target = targets[0]
    target_tier = _effective_subscription_tier(target["subscription_tier"], target["vip_expires_at"])
    viewer_tier = _effective_subscription_tier(viewer["subscription_tier"], viewer["vip_expires_at"])
    if target_tier == "vip" and viewer_tier != "vip":
        raise ApiException("VIP_REQUIRED", "Upgrade to VIP to call this member.", 403)
    blocked = db.execute(
        text(
            """
            SELECT 1 FROM safety_blocks
            WHERE (blocker_id = :caller AND blocked_id = :callee)
               OR (blocker_id = :callee AND blocked_id = :caller)
            LIMIT 1
            """
        ),
        {"caller": account.account_id, "callee": body.target_id},
    ).first()
    if blocked is not None:
        raise ApiException("MEMBER_BLOCKED", "Calling is unavailable for this member.", 403)

    payer_id = (
        account.account_id
        if viewer["identity"] == "man"
        else body.target_id if target["identity"] == "man" else None
    )
    if payer_id and _credit_balance(db, str(payer_id)) < 1:
        raise ApiException("CALL_CREDIT_REQUIRED", "Buy at least one call credit before starting a call.", 409)
    _ensure_no_active_call(db, (account.account_id, body.target_id))

    call_id = uuid.uuid4().hex
    room_name = f"flingra_call_{call_id}"
    now = _now()
    # Fail before persisting a call if LiveKit is unavailable.
    livekit_url, token = create_room_token(
        settings,
        room_name=room_name,
        identity=account.account_id,
        can_publish=True,
    )
    db.execute(
        text(
            """
            INSERT INTO call_sessions (
                id, caller_id, callee_id, payer_id, room_name, call_type,
                status, idempotency_key, created_at
            )
            VALUES (
                :id, :caller_id, :callee_id, :payer_id, :room_name, :call_type,
                'ringing', :idempotency_key, :created_at
            )
            """
        ),
        {
            "id": call_id,
            "caller_id": account.account_id,
            "callee_id": body.target_id,
            "payer_id": payer_id,
            "room_name": room_name,
            "call_type": body.call_type,
            "idempotency_key": key,
            "created_at": now,
        },
    )
    event = {
        "callId": call_id,
        "callerId": account.account_id,
        "callType": body.call_type,
        "status": "ringing",
    }
    enqueue_realtime_event(db, body.target_id, "call.incoming", event)
    record_audit_event(
        db,
        request,
        event_type="call.started",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=body.target_id,
        outcome="success",
        metadata={"callId": call_id, "callType": body.call_type},
    )
    db.commit()
    return CallSessionResponse(
        call_id=call_id,
        caller_id=account.account_id,
        callee_id=body.target_id,
        call_type=body.call_type,
        status="ringing",
        livekit_url=livekit_url,
        token=token,
        credit_balance=_credit_balance(db, str(payer_id)) if payer_id else None,
    )


@router.get("/incoming")
def list_incoming_calls(account: IdentityVerifiedAccount, db: DbSession) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT c.id, c.caller_id, c.call_type, c.created_at, p.display_name, p.photos
            FROM call_sessions c JOIN profiles p ON p.account_id = c.caller_id
            WHERE c.callee_id = :account_id AND c.status = 'ringing'
            ORDER BY c.created_at DESC LIMIT 20
            """
        ),
        {"account_id": account.account_id},
    ).mappings()
    return [
        {
            "callId": str(row["id"]),
            "callerId": str(row["caller_id"]),
            "callerName": row["display_name"],
            "callerPhoto": _first_photo(row["photos"]),
            "callType": row["call_type"],
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


@router.post("/{call_id}/accept", response_model=CallSessionResponse, dependencies=[Depends(require_csrf)])
def accept_call(
    call_id: str,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> CallSessionResponse:
    row = _call_row(db, call_id, account.account_id, lock=True)
    if row["callee_id"] != account.account_id:
        raise ApiException("CALL_ACTION_FORBIDDEN", "Only the invited member can accept this call.", 403)
    if row["status"] != "ringing" or _as_datetime(row["created_at"]) < _now() - RING_TIMEOUT:
        raise ApiException("CALL_NOT_AVAILABLE", "This call is no longer available.", 409)
    _ensure_no_active_call(
        db,
        (str(row["caller_id"]), str(row["callee_id"])),
        exclude_call_id=call_id,
    )
    db.execute(
        text("UPDATE call_sessions SET status = 'connecting' WHERE id = :id AND status = 'ringing'"),
        {"id": call_id},
    )
    row["status"] = "connecting"
    url, token = create_room_token(
        settings,
        room_name=str(row["room_name"]),
        identity=account.account_id,
        can_publish=True,
    )
    _queue_call_event(db, row, "call.accepted")
    record_audit_event(
        db,
        request,
        event_type="call.accepted",
        actor_type="user",
        actor_id=account.account_id,
        subject_account_id=str(row["caller_id"]),
        outcome="success",
        metadata={"callId": call_id},
    )
    db.commit()
    return CallSessionResponse(
        call_id=call_id,
        caller_id=str(row["caller_id"]),
        callee_id=account.account_id,
        call_type=row["call_type"],
        status="connecting",
        livekit_url=url,
        token=token,
        credit_balance=_credit_balance(db, str(row["payer_id"])) if row["payer_id"] else None,
    )


@router.post("/{call_id}/decline", status_code=204, dependencies=[Depends(require_csrf)])
def decline_call(
    call_id: str,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> None:
    row = _call_row(db, call_id, account.account_id, lock=True)
    if row["callee_id"] != account.account_id:
        raise ApiException("CALL_ACTION_FORBIDDEN", "Only the invited member can decline this call.", 403)
    if row["status"] != "ringing":
        raise ApiException("CALL_NOT_AVAILABLE", "This call is no longer available.", 409)
    now = _now()
    db.execute(
        text("UPDATE call_sessions SET status = 'declined', ended_at = :now WHERE id = :id"),
        {"id": call_id, "now": now},
    )
    row["status"] = "declined"
    row["ended_at"] = now
    _queue_call_event(db, row, "call.declined")
    record_audit_event(
        db, request, event_type="call.declined", actor_type="user",
        actor_id=account.account_id, subject_account_id=str(row["caller_id"]),
        outcome="success", metadata={"callId": call_id},
    )
    db.commit()
    delete_room(settings, str(row["room_name"]))
    db.execute(
        text("UPDATE call_sessions SET room_closed_at = :now WHERE id = :id"),
        {"id": call_id, "now": _now()},
    )
    db.commit()


@router.post("/{call_id}/connected", response_model=CallSessionResponse, dependencies=[Depends(require_csrf)])
def confirm_call_connection(
    call_id: str,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> CallSessionResponse:
    row = _call_row(db, call_id, account.account_id, lock=True)
    if row["status"] not in {"connecting", "active"}:
        raise ApiException("CALL_NOT_AVAILABLE", "This call is not connecting.", 409)
    now = _now()
    column = "caller_connected_at" if row["caller_id"] == account.account_id else "callee_connected_at"
    db.execute(
        text(f"UPDATE call_sessions SET {column} = COALESCE({column}, :now) WHERE id = :id"),
        {"id": call_id, "now": now},
    )
    row[column] = row[column] or now
    if row["caller_connected_at"] and row["callee_connected_at"] and row["status"] == "connecting":
        if row["payer_id"]:
            if _credit_balance(db, str(row["payer_id"])) < CALL_TICK_CREDITS:
                row["status"] = "ended"
                row["ended_at"] = now
                db.execute(
                    text("UPDATE call_sessions SET status = 'ended', ended_at = :now WHERE id = :id"),
                    {"id": call_id, "now": now},
                )
                _queue_call_event(db, row, "call.ended", reason="insufficient_credits")
                db.commit()
                raise ApiException("CALL_CREDIT_REQUIRED", "Buy call credits to continue this call.", 409)
            charged, _ = _spend_ticks(db, row, CALL_TICK_CREDITS)
            if charged != CALL_TICK_CREDITS:
                raise ServiceUnavailable("Could not reserve call credits.")
            row["billed_ticks"] = 1
        row.update(status="active", started_at=now, last_billed_at=now, last_activity_at=now)
        db.execute(
            text(
                """
                UPDATE call_sessions
                SET status = 'active', started_at = :now, last_billed_at = :now,
                    last_activity_at = :now, billed_ticks = :billed_ticks
                WHERE id = :id AND status = 'connecting'
                """
            ),
            {"id": call_id, "now": now, "billed_ticks": row["billed_ticks"]},
        )
        _queue_call_event(db, row, "call.connected")
    else:
        db.execute(
            text(f"UPDATE call_sessions SET {column} = :now WHERE id = :id"),
            {"id": call_id, "now": row[column],},
        )
    db.commit()
    return _response(
        row,
        account_id=account.account_id,
        credit_balance=_credit_balance(db, str(row["payer_id"])) if row["payer_id"] else None,
    )


@router.post(
    "/{call_id}/heartbeat",
    response_model=CallSessionResponse,
    dependencies=[Depends(require_csrf)],
)
def call_heartbeat(
    call_id: str,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> CallSessionResponse:
    row = _call_row(db, call_id, account.account_id, lock=True)
    if row["status"] != "active":
        raise ApiException("CALL_NOT_ACTIVE", "This call is no longer active.", 409)
    now = _now()
    cutoff = now
    if row["last_activity_at"] is not None:
        activity = _as_datetime(row["last_activity_at"])
        if activity < now - ACTIVITY_TIMEOUT:
            cutoff = activity
    ended, balance = _settle_due_ticks(db, row, cutoff)
    if not ended:
        row["last_activity_at"] = now
        db.execute(
            text("UPDATE call_sessions SET last_activity_at = :now WHERE id = :id AND status = 'active'"),
            {"now": now, "id": call_id},
        )
    db.commit()
    if ended:
        delete_room(settings, str(row["room_name"]))
        db.execute(
            text("UPDATE call_sessions SET room_closed_at = :now WHERE id = :id"),
            {"now": _now(), "id": call_id},
        )
        db.commit()
    return _response(row, credit_balance=balance)


@router.get("/{call_id}", response_model=CallSessionResponse)
def get_call(
    call_id: str,
    account: IdentityVerifiedAccount,
    db: DbSession,
) -> CallSessionResponse:
    row = _call_row(db, call_id, account.account_id)
    balance = _credit_balance(db, str(row["payer_id"])) if row["payer_id"] else None
    return _response(row, credit_balance=balance)


@router.post(
    "/{call_id}/token",
    response_model=LiveKitConnectionResponse,
    dependencies=[Depends(require_csrf)],
)
def get_call_token(
    call_id: str,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> LiveKitConnectionResponse:
    row = _call_row(db, call_id, account.account_id)
    if row["status"] not in {"connecting", "active"}:
        raise ApiException("CALL_NOT_ACTIVE", "This call is not ready to connect.", 409)
    url, token = create_room_token(
        settings,
        room_name=str(row["room_name"]),
        identity=account.account_id,
        can_publish=True,
    )
    return LiveKitConnectionResponse(url=url, token=token)


@router.delete("/{call_id}", status_code=204, dependencies=[Depends(require_csrf)])
def end_call(
    call_id: str,
    request: Request,
    account: IdentityVerifiedAccount,
    db: DbSession,
    settings: SettingsDependency,
) -> None:
    row = _call_row(db, call_id, account.account_id, lock=True)
    if row["status"] in {"ended", "declined"}:
        return
    if row["status"] == "active":
        cutoff = _now()
        if row["last_activity_at"] is not None:
            activity = _as_datetime(row["last_activity_at"])
            if activity < cutoff - ACTIVITY_TIMEOUT:
                cutoff = activity
        _settle_due_ticks(db, row, cutoff)
    now = _now()
    db.execute(
        text("UPDATE call_sessions SET status = 'ended', ended_at = :now WHERE id = :id"),
        {"id": call_id, "now": now},
    )
    row["status"] = "ended"
    row["ended_at"] = now
    _queue_call_event(db, row, "call.ended", reason="hangup")
    record_audit_event(
        db, request, event_type="call.ended", actor_type="user",
        actor_id=account.account_id,
        subject_account_id=str(row["callee_id"] if row["caller_id"] == account.account_id else row["caller_id"]),
        outcome="success", metadata={"callId": call_id},
    )
    db.commit()
    delete_room(settings, str(row["room_name"]))
    db.execute(
        text("UPDATE call_sessions SET room_closed_at = :now WHERE id = :id"),
        {"now": _now(), "id": call_id},
    )
    db.commit()
