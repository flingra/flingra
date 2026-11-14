import json

import httpx
import pytest

from app.config import Settings
from app.errors import ServiceUnavailable
from app import notifications


def brevo_settings(**overrides) -> Settings:
    return Settings(
        brevo_api_key="test-brevo-key",
        brevo_sender_email="verified@example.test",
        **overrides,
    )


def use_mock_brevo(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    original_client = httpx.Client
    monkeypatch.setattr(
        notifications.httpx,
        "Client",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )


def test_verification_email_uses_brevo_transactional_api(monkeypatch) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"messageId": "provider-id"})

    use_mock_brevo(monkeypatch, handle)

    notifications.send_verification_code(brevo_settings(), "user@example.test", "123456")

    assert len(requests) == 1
    sent = requests[0]
    assert str(sent.url) == notifications.BREVO_SEND_EMAIL_URL
    assert sent.headers["api-key"] == "test-brevo-key"
    payload = json.loads(sent.content)
    assert payload["sender"] == {
        "name": "Flingra",
        "email": "verified@example.test",
    }
    assert payload["to"] == [{"email": "user@example.test"}]
    assert "123456" in payload["textContent"]


def test_password_reset_email_uses_frontend_url_and_token(monkeypatch) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"messageId": "provider-id"})

    use_mock_brevo(monkeypatch, handle)
    settings = brevo_settings(frontend_url="https://app.example.test/")

    notifications.send_password_reset(settings, "user@example.test", "opaque-reset-token")

    payload = json.loads(requests[0].content)
    assert "https://app.example.test/password/reset?token=opaque-reset-token" in payload["textContent"]


def test_brevo_failure_is_reported_without_provider_response_details(monkeypatch) -> None:
    use_mock_brevo(
        monkeypatch,
        lambda _: httpx.Response(401, json={"message": "invalid api key"}),
    )

    with pytest.raises(ServiceUnavailable, match="Email delivery is temporarily unavailable") as error:
        notifications.send_verification_code(brevo_settings(), "user@example.test", "123456")

    assert "invalid api key" not in str(error.value)
    assert "test-brevo-key" not in str(error.value)


def test_email_delivery_requires_brevo_key_and_verified_sender() -> None:
    settings = Settings(brevo_api_key=None, brevo_sender_email=None)

    with pytest.raises(ServiceUnavailable, match="Email delivery is not configured"):
        notifications.send_verification_code(settings, "user@example.test", "123456")
