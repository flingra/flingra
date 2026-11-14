import httpx

from app.config import Settings
from app.errors import ServiceUnavailable

BREVO_SEND_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"
EMAIL_TIMEOUT = httpx.Timeout(10.0, connect=3.0)


def _send_email(settings: Settings, recipient: str, subject: str, text_content: str) -> None:
    if not settings.brevo_api_key or not settings.brevo_sender_email:
        raise ServiceUnavailable("Email delivery is not configured.")

    payload = {
        "sender": {
            "name": settings.brevo_sender_name,
            "email": settings.brevo_sender_email,
        },
        "to": [{"email": recipient}],
        "subject": subject,
        "textContent": text_content,
    }

    try:
        with httpx.Client(timeout=EMAIL_TIMEOUT, follow_redirects=False) as client:
            response = client.post(
                BREVO_SEND_EMAIL_URL,
                headers={
                    "api-key": settings.brevo_api_key.get_secret_value(),
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
    except (httpx.HTTPError, OSError) as exc:
        raise ServiceUnavailable("Email delivery is temporarily unavailable.") from exc


def send_verification_code(settings: Settings, recipient: str, code: str) -> None:
    _send_email(
        settings,
        recipient,
        "Your Flingra verification code",
        f"Your Flingra verification code is {code}. "
        "It expires in 10 minutes. If you did not request this, ignore this email.",
    )


def send_password_reset(settings: Settings, recipient: str, token: str) -> None:
    _send_email(
        settings,
        recipient,
        "Reset your Flingra password",
        (
            f"Use this link to reset your Flingra password:\n"
            f"{settings.frontend_url.rstrip('/')}/password/reset?token={token}\n\n"
            "If you did not request this, ignore this email."
        ),
    )
