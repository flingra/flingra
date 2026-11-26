import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_engine
from app.security import hash_token

logger = logging.getLogger("uvicorn.error")
router = APIRouter(tags=["realtime"])
EVENT_RETENTION = timedelta(days=7)


def is_origin_allowed(
    origin: str | None,
    allowed_origins: list[str],
    *,
    request_scheme: str,
    request_netloc: str,
) -> bool:
    expected_scheme = "https" if request_scheme in {"https", "wss"} else "http"
    same_origin = origin == f"{expected_scheme}://{request_netloc}"
    return same_origin or origin in allowed_origins


def enqueue_realtime_event(
    db: Session,
    recipient_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    db.execute(
        text(
            """
            INSERT INTO realtime_events (recipient_id, event_type, payload_json, created_at)
            VALUES (:recipient_id, :event_type, :payload_json, :created_at)
            """
        ),
        {
            "recipient_id": recipient_id,
            "event_type": event_type,
            "payload_json": json.dumps(payload, separators=(",", ":"), default=str),
            "created_at": datetime.now(UTC).replace(tzinfo=None),
        },
    )


def _authenticated_account_id(websocket: WebSocket, db: Session) -> str | None:
    settings = websocket.app.state.settings
    raw_token = websocket.cookies.get(settings.session_cookie_name)
    if not raw_token:
        return None
    row = db.execute(
        text(
            """
            SELECT a.id, a.date_of_birth
            FROM sessions s
            JOIN accounts a ON a.id = s.account_id
            WHERE s.session_token_hash = :token_hash
              AND s.revoked_at IS NULL AND s.expires_at > :now
              AND a.email_verified = TRUE AND a.account_state = 'active'
            """
        ),
        {
            "token_hash": hash_token(raw_token),
            "now": datetime.now(UTC).replace(tzinfo=None),
        },
    ).mappings().first()
    if row is None:
        return None
    birth_date = row["date_of_birth"]
    if isinstance(birth_date, str):
        birth_date = datetime.fromisoformat(birth_date).date()
    today = datetime.now(UTC).date()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return str(row["id"]) if age >= 21 else None


@router.websocket("/realtime/ws")
async def realtime_events(websocket: WebSocket) -> None:
    settings = websocket.app.state.settings
    origin = websocket.headers.get("origin")
    if not is_origin_allowed(
        origin,
        settings.allowed_origins,
        request_scheme=websocket.url.scheme,
        request_netloc=websocket.url.netloc,
    ):
        await websocket.close(code=4403)
        return
    cursor_text = websocket.query_params.get("after")
    try:
        cursor = max(0, int(cursor_text)) if cursor_text is not None else None
    except ValueError:
        await websocket.close(code=4400)
        return

    with Session(get_engine(settings), expire_on_commit=False) as db:
        account_id = _authenticated_account_id(websocket, db)
        if account_id is None:
            await websocket.close(code=4401)
            return
        if cursor is None:
            cursor = int(
                db.execute(
                    text("SELECT COALESCE(MAX(id), 0) FROM realtime_events WHERE recipient_id = :account_id"),
                    {"account_id": account_id},
                ).scalar_one()
            )

    await websocket.accept()
    try:
        while True:
            with Session(get_engine(settings), expire_on_commit=False) as db:
                if _authenticated_account_id(websocket, db) is None:
                    await websocket.close(code=4401)
                    return
                rows = db.execute(
                    text(
                        """
                        SELECT id, event_type, payload_json
                        FROM realtime_events
                        WHERE recipient_id = :account_id AND id > :cursor
                        ORDER BY id
                        LIMIT 100
                        """
                    ),
                    {"account_id": account_id, "cursor": cursor},
                ).mappings().all()
            for row in rows:
                cursor = int(row["id"])
                payload = row["payload_json"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                await websocket.send_json(
                    {
                        "id": cursor,
                        "type": row["event_type"],
                        "data": payload,
                    }
                )
            if not rows:
                await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return
    except (SQLAlchemyError, json.JSONDecodeError):
        logger.exception("Realtime websocket failed for account %s.", account_id)
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            return
