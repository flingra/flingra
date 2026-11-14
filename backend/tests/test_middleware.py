from collections import defaultdict

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class FakeRedis:
    def __init__(self) -> None:
        self.counts: defaultdict[str, int] = defaultdict(int)

    async def ping(self) -> bool:
        return True

    async def eval(self, _script: str, _key_count: int, key: str, limit: int, _window: int) -> int:
        self.counts[key] += 1
        return int(self.counts[key] <= int(limit))

    async def aclose(self) -> None:
        return None


def test_sensitive_routes_are_rate_limited_before_body_validation(monkeypatch) -> None:
    redis_client = FakeRedis()
    monkeypatch.setattr("app.main.Redis.from_url", lambda *_args, **_kwargs: redis_client)
    application = create_app(
        Settings(
            database_url="sqlite://",
            rate_limit_redis_url="redis://localhost",
        )
    )

    with TestClient(application) as client:
        responses = [client.post("/auth/signup", json={}) for _ in range(11)]

    assert [response.status_code for response in responses[:10]] == [422] * 10
    assert responses[10].status_code == 429
    assert responses[10].json()["error"]["code"] == "RATE_LIMITED"
    assert responses[10].headers["x-content-type-options"] == "nosniff"


def test_sensitive_routes_fail_closed_without_redis() -> None:
    client = TestClient(
        create_app(
            Settings(
                database_url="sqlite://",
                rate_limit_redis_url=None,
            )
        )
    )

    response = client.post(
        "/auth/login",
        json={"identifier": "person@example.com", "password": "password123"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_api_responses_have_security_headers() -> None:
    client = TestClient(
        create_app(Settings(database_url="sqlite://", rate_limiting_enabled=False))
    )

    response = client.get("/health/live")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_oversized_request_body_is_rejected() -> None:
    client = TestClient(
        create_app(
            Settings(
                database_url="sqlite://",
                rate_limiting_enabled=False,
                max_request_bytes=32,
            )
        )
    )

    response = client.post("/auth/signup", content=b'{"payload":"' + b"x" * 64 + b'"}')

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"
    assert response.headers["x-content-type-options"] == "nosniff"
