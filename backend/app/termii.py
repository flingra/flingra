import re

import httpx

from app.config import Settings
from app.errors import ServiceUnavailable

TERMII_SEND_SMS_URL = "https://api.ng.termii.com/api/sms/send"


def normalize_phone_number(phone: str) -> str:
    stripped = phone.strip()
    digits = re.sub(r"\D", "", stripped)
    if stripped.startswith("+"):
        normalized = digits
    elif digits.startswith("234"):
        normalized = digits
    elif digits.startswith("0") and len(digits) == 11:
        normalized = f"234{digits[1:]}"
    else:
        raise ValueError("Phone number must include an international country code.")
    if not 8 <= len(normalized) <= 15:
        raise ValueError("Phone number is not a valid international number.")
    return normalized


def send_sms(settings: Settings, phone: str, message: str) -> None:
    if not settings.termii_api_key or not settings.termii_sender_id:
        raise ServiceUnavailable("SMS delivery is not configured.")
    try:
        recipient = normalize_phone_number(phone)
    except ValueError as exc:
        raise ServiceUnavailable("SMS delivery requires a valid international phone number.") from exc

    try:
        with httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=False) as client:
            response = client.post(
                TERMII_SEND_SMS_URL,
                json={
                    "api_key": settings.termii_api_key.get_secret_value(),
                    "to": recipient,
                    "from": settings.termii_sender_id,
                    "sms": message,
                    "type": "plain",
                    "channel": "generic",
                },
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ServiceUnavailable("SMS delivery is temporarily unavailable.") from exc
    if not isinstance(payload, dict) or str(payload.get("code", "")).lower() != "ok":
        raise ServiceUnavailable("SMS delivery is temporarily unavailable.")
