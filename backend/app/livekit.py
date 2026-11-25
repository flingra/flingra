import base64
import hashlib
import hmac
import json
import time
from typing import Any

import httpx

from app.config import Settings
from app.errors import ServiceUnavailable


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _credentials(settings: Settings) -> tuple[str, str, str]:
    if not settings.livekit_url or not settings.livekit_api_key or not settings.livekit_api_secret:
        raise ServiceUnavailable("LiveKit is not configured.")
    if not settings.livekit_url.startswith("wss://"):
        raise ServiceUnavailable("LiveKit must use a secure WebSocket URL.")
    return (
        settings.livekit_url.rstrip("/"),
        settings.livekit_api_key,
        settings.livekit_api_secret.get_secret_value(),
    )


def create_room_token(
    settings: Settings,
    *,
    room_name: str,
    identity: str,
    can_publish: bool,
    ttl_seconds: int = 3600,
) -> tuple[str, str]:
    url, api_key, secret = _credentials(settings)
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims: dict[str, Any] = {
        "iss": api_key,
        "sub": identity,
        "nbf": now,
        "exp": now + ttl_seconds,
        "video": {
            "room": room_name,
            "roomJoin": True,
            "canPublish": can_publish,
            "canPublishData": can_publish,
            "canSubscribe": True,
        },
    }
    payload = _b64url(json.dumps(claims, separators=(",", ":")).encode())
    unsigned = f"{header}.{payload}"
    signature = hmac.new(secret.encode(), unsigned.encode("ascii"), hashlib.sha256).digest()
    return url, f"{unsigned}.{_b64url(signature)}"


def delete_room(settings: Settings, room_name: str) -> None:
    url, api_key, secret = _credentials(settings)
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = {
        "iss": api_key,
        "sub": api_key,
        "nbf": now,
        "exp": now + 60,
        "video": {"roomAdmin": True, "room": room_name},
    }
    payload = _b64url(json.dumps(claims, separators=(",", ":")).encode())
    unsigned = f"{header}.{payload}"
    signature = hmac.new(secret.encode(), unsigned.encode("ascii"), hashlib.sha256).digest()
    token = f"{unsigned}.{_b64url(signature)}"
    try:
        with httpx.Client(timeout=httpx.Timeout(10.0, connect=3.0), follow_redirects=False) as client:
            response = client.post(
                f"{url.replace('wss://', 'https://')}/twirp/livekit.RoomService/DeleteRoom",
                headers={"Authorization": f"Bearer {token}"},
                json={"room": room_name},
            )
            if response.status_code != 404:
                response.raise_for_status()
    except (httpx.HTTPError, OSError) as exc:
        raise ServiceUnavailable("LiveKit could not close this room.") from exc
