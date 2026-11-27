import hashlib
import hmac
import logging
from typing import Any

import httpx

from app.config import Settings
from app.errors import ServiceUnavailable

PAYSTACK_API_URL = "https://api.paystack.co"
logger = logging.getLogger("uvicorn.error")


def _secret(settings: Settings) -> str:
    if settings.payment_provider != "paystack" or settings.paystack_secret_key is None:
        raise ServiceUnavailable("Paystack payments are not configured.")
    return settings.paystack_secret_key.get_secret_value()


def ensure_configured(settings: Settings) -> None:
    _secret(settings)


def initialize_transaction(
    settings: Settings,
    *,
    email: str,
    amount_kobo: int,
    reference: str,
    callback_url: str,
) -> str:
    secret = _secret(settings)
    try:
        with httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
            response = client.post(
                f"{PAYSTACK_API_URL}/transaction/initialize",
                headers={"Authorization": f"Bearer {secret}"},
                json={
                    "email": email,
                    "amount": amount_kobo,
                    "currency": "NGN",
                    "reference": reference,
                    "callback_url": callback_url,
                },
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Paystack transaction initialization returned HTTP %d.",
            exc.response.status_code,
        )
        raise ServiceUnavailable("Paystack is temporarily unavailable.") from exc
    except httpx.HTTPError as exc:
        logger.warning(
            "Paystack transaction initialization failed: %s.",
            type(exc).__name__,
        )
        raise ServiceUnavailable("Paystack is temporarily unavailable.") from exc
    except ValueError as exc:
        logger.warning("Paystack transaction initialization returned invalid JSON.")
        raise ServiceUnavailable("Paystack is temporarily unavailable.") from exc

    data = payload.get("data") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get("status") is not True
        or not isinstance(data, dict)
        or data.get("reference") != reference
        or not isinstance(data.get("authorization_url"), str)
        or not data["authorization_url"].startswith("https://")
    ):
        raise ServiceUnavailable("Paystack could not initialize this payment.")
    return data["authorization_url"]


def verify_transaction(settings: Settings, reference: str) -> dict[str, Any]:
    secret = _secret(settings)
    try:
        with httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
            response = client.get(
                f"{PAYSTACK_API_URL}/transaction/verify/{reference}",
                headers={"Authorization": f"Bearer {secret}"},
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Paystack transaction verification returned HTTP %d.",
            exc.response.status_code,
        )
        raise ServiceUnavailable("Paystack is temporarily unavailable.") from exc
    except httpx.HTTPError as exc:
        logger.warning(
            "Paystack transaction verification failed: %s.",
            type(exc).__name__,
        )
        raise ServiceUnavailable("Paystack is temporarily unavailable.") from exc
    except ValueError as exc:
        logger.warning("Paystack transaction verification returned invalid JSON.")
        raise ServiceUnavailable("Paystack is temporarily unavailable.") from exc

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(payload, dict) or payload.get("status") is not True or not isinstance(data, dict):
        raise ServiceUnavailable("Paystack could not verify this payment.")
    return data


def _request_data(
    settings: Settings,
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    payload: dict[str, object] | None = None,
) -> Any:
    secret = _secret(settings)
    try:
        with httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
            response = client.request(
                method,
                f"{PAYSTACK_API_URL}{path}",
                headers={"Authorization": f"Bearer {secret}"},
                params=params,
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("Paystack API request returned HTTP %d.", exc.response.status_code)
        raise ServiceUnavailable("Paystack is temporarily unavailable.") from exc
    except httpx.HTTPError as exc:
        logger.warning("Paystack API request failed: %s.", type(exc).__name__)
        raise ServiceUnavailable("Paystack is temporarily unavailable.") from exc
    except ValueError as exc:
        logger.warning("Paystack API request returned invalid JSON.")
        raise ServiceUnavailable("Paystack is temporarily unavailable.") from exc
    if not isinstance(body, dict) or body.get("status") is not True:
        raise ServiceUnavailable("Paystack could not complete this request.")
    if "data" not in body:
        raise ServiceUnavailable("Paystack returned an incomplete response.")
    return body["data"]


def list_nigerian_banks(settings: Settings) -> list[dict[str, Any]]:
    data = _request_data(
        settings,
        "GET",
        "/bank",
        params={"country": "nigeria", "currency": "NGN", "type": "nuban", "perPage": "100"},
    )
    if not isinstance(data, list):
        raise ServiceUnavailable("Paystack returned an incomplete bank list.")
    return [bank for bank in data if isinstance(bank, dict)]


def resolve_bank_account(
    settings: Settings,
    *,
    account_number: str,
    bank_code: str,
) -> dict[str, Any]:
    data = _request_data(
        settings,
        "GET",
        "/bank/resolve",
        params={"account_number": account_number, "bank_code": bank_code},
    )
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("account_name"), str)
        or not data["account_name"].strip()
    ):
        raise ServiceUnavailable("Paystack could not verify this bank account.")
    return data


def create_transfer_recipient(
    settings: Settings,
    *,
    account_name: str,
    account_number: str,
    bank_code: str,
) -> str:
    data = _request_data(
        settings,
        "POST",
        "/transferrecipient",
        payload={
            "type": "nuban",
            "name": account_name,
            "account_number": account_number,
            "bank_code": bank_code,
            "currency": "NGN",
        },
    )
    if not isinstance(data, dict) or not isinstance(data.get("recipient_code"), str):
        raise ServiceUnavailable("Paystack could not save this bank account.")
    return data["recipient_code"]


def initiate_transfer(
    settings: Settings,
    *,
    amount_kobo: int,
    recipient_code: str,
    reference: str,
) -> dict[str, Any]:
    data = _request_data(
        settings,
        "POST",
        "/transfer",
        payload={
            "source": "balance",
            "amount": amount_kobo,
            "recipient": recipient_code,
            "reference": reference,
            "reason": "Flingra wallet payout",
        },
    )
    if not isinstance(data, dict) or data.get("reference") != reference:
        raise ServiceUnavailable("Paystack returned an incomplete transfer response.")
    return data


def verify_webhook_signature(settings: Settings, body: bytes, signature: str | None) -> bool:
    if signature is None:
        return False
    secret = _secret(settings)
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)
