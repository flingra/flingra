import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from redis.exceptions import RedisError

logger = logging.getLogger("uvicorn.error")

ASGIMessage = dict[str, Any]
ASGIReceive = Callable[[], Awaitable[ASGIMessage]]
ASGISend = Callable[[ASGIMessage], Awaitable[None]]

SENSITIVE_ROUTE_LIMITS: dict[tuple[str, str], tuple[int, int]] = {
    ("POST", "/auth/signup"): (10, 60 * 60),
    ("POST", "/auth/login"): (30, 15 * 60),
    ("POST", "/auth/verify-contact"): (30, 15 * 60),
    ("POST", "/auth/resend-code"): (10, 60 * 60),
    ("POST", "/auth/password/forgot"): (10, 60 * 60),
    ("POST", "/auth/password/reset"): (20, 60 * 60),
}

_FIXED_WINDOW_SCRIPT = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current >= tonumber(ARGV[1]) then
    return 0
end
current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
end
return 1
"""

_SECURITY_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cache-control", b"no-store"),
)


class RequestTooLarge(Exception):
    pass


class ApiHardeningMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]], max_request_bytes: int) -> None:
        self.app = app
        self.max_request_bytes = max_request_bytes

    async def __call__(self, scope: dict[str, Any], receive: ASGIReceive, send: ASGISend) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_with_security_headers(message: ASGIMessage) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = list(message.get("headers", []))
                existing = {key.lower() for key, _ in headers}
                headers.extend((key, value) for key, value in _SECURITY_HEADERS if key not in existing)
                if scope["app"].state.settings.session_cookie_secure and b"strict-transport-security" not in existing:
                    headers.append((b"strict-transport-security", b"max-age=31536000"))
                message["headers"] = headers
            await send(message)

        content_length = next(
            (value for key, value in scope.get("headers", []) if key.lower() == b"content-length"),
            None,
        )
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                declared_length = self.max_request_bytes + 1
            if declared_length < 0 or declared_length > self.max_request_bytes:
                await self._send_error(send_with_security_headers, 413, "REQUEST_TOO_LARGE", "Request body is too large.")
                return

        received_bytes = 0

        async def receive_with_limit() -> ASGIMessage:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_request_bytes:
                    raise RequestTooLarge
            return message

        try:
            await self.app(scope, receive_with_limit, send_with_security_headers)
        except RequestTooLarge:
            if not response_started:
                await self._send_error(
                    send_with_security_headers,
                    413,
                    "REQUEST_TOO_LARGE",
                    "Request body is too large.",
                )

    @staticmethod
    async def _send_error(
        send: ASGISend,
        status_code: int,
        code: str,
        message: str,
    ) -> None:
        body = json.dumps({"error": {"code": code, "message": message}}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": body})


class RedisRateLimitMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: ASGIReceive, send: ASGISend) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = scope["app"].state.settings
        if not settings.rate_limiting_enabled:
            await self.app(scope, receive, send)
            return

        route = (scope.get("method", ""), scope.get("path", ""))
        limits = SENSITIVE_ROUTE_LIMITS.get(route)
        if limits is None:
            await self.app(scope, receive, send)
            return

        redis_client = scope["app"].state.rate_limit_redis
        if redis_client is None:
            await self._send_error(send, 503, "SERVICE_UNAVAILABLE", "Security controls are unavailable.")
            return

        limit, window_seconds = limits
        client = scope.get("client")
        remote_address = client[0] if client else "unknown"
        address_digest = hashlib.sha256(remote_address.encode("utf-8")).hexdigest()
        key = f"flingra:rate-limit:v1:{route[1]}:{address_digest}"
        try:
            allowed = await redis_client.eval(_FIXED_WINDOW_SCRIPT, 1, key, limit, window_seconds)
        except RedisError:
            logger.error("Rate-limit storage is unavailable; refusing sensitive request.")
            await self._send_error(send, 503, "SERVICE_UNAVAILABLE", "Security controls are unavailable.")
            return

        if not allowed:
            await self._send_error(send, 429, "RATE_LIMITED", "Too many requests. Try again later.")
            return

        await self.app(scope, receive, send)

    @staticmethod
    async def _send_error(send: ASGISend, status_code: int, code: str, message: str) -> None:
        body = json.dumps({"error": {"code": code, "message": message}}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": body})
