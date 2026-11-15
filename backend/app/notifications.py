from html import escape
from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.errors import ServiceUnavailable

BREVO_SEND_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"
EMAIL_TIMEOUT = httpx.Timeout(10.0, connect=3.0)


def _html_email(preheader: str, content: str) -> str:
    return f"""\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Flingra</title>
  </head>
  <body style="margin:0;background:#f4f6f5;color:#202923;font-family:Arial,Helvetica,sans-serif;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">{escape(preheader)}</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f6f5;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border-radius:16px;">
            <tr>
              <td style="padding:32px 28px;">
                <p style="margin:0 0 24px;color:#176b4d;font-size:20px;font-weight:700;">Flingra</p>
                {content}
                <p style="margin:28px 0 0;color:#69736d;font-size:13px;line-height:1.6;">
                  If you did not request this, you can safely ignore this email.
                </p>
              </td>
            </tr>
          </table>
          <p style="margin:16px 0 0;color:#69736d;font-size:12px;">This is an automated message. Please do not reply.</p>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _send_email(
    settings: Settings,
    recipient: str,
    subject: str,
    text_content: str,
    html_content: str,
) -> None:
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
        "htmlContent": html_content,
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
    text_content = (
        f"Your Flingra verification code is {code}.\n\n"
        "It expires in 10 minutes. If you did not request this, ignore this email."
    )
    html_content = _html_email(
        "Your 6-digit email verification code.",
        f"""\
<h1 style="margin:0 0 16px;font-size:24px;line-height:1.3;">Verify your email</h1>
<p style="margin:0 0 20px;font-size:16px;line-height:1.6;">Enter this code in Flingra to verify your email address:</p>
<p style="margin:0 0 16px;padding:16px;border-radius:10px;background:#f0f7f3;color:#176b4d;font-size:30px;font-weight:700;letter-spacing:8px;text-align:center;">{escape(code)}</p>
<p style="margin:0;color:#69736d;font-size:14px;line-height:1.6;">This code expires in 10 minutes.</p>"""
    )
    _send_email(
        settings,
        recipient,
        "Your Flingra verification code",
        text_content,
        html_content,
    )


def send_two_factor_code(settings: Settings, recipient: str, code: str) -> None:
    text_content = (
        f"Your Flingra two-factor authentication code is {code}.\n\n"
        "It expires in 10 minutes. If you did not request this, secure your account immediately."
    )
    html_content = _html_email(
        "Your Flingra two-factor authentication code.",
        f"""\
<h1 style="margin:0 0 16px;font-size:24px;line-height:1.3;">Confirm two-factor authentication</h1>
<p style="margin:0 0 20px;font-size:16px;line-height:1.6;">Enter this code in Flingra to enable two-factor authentication:</p>
<p style="margin:0 0 16px;padding:16px;border-radius:10px;background:#f0f7f3;color:#176b4d;font-size:30px;font-weight:700;letter-spacing:8px;text-align:center;">{escape(code)}</p>
<p style="margin:0;color:#69736d;font-size:14px;line-height:1.6;">This code expires in 10 minutes.</p>""",
    )
    _send_email(
        settings,
        recipient,
        "Your Flingra two-factor authentication code",
        text_content,
        html_content,
    )


def send_password_reset(settings: Settings, recipient: str, token: str) -> None:
    reset_url = (
        f"{settings.frontend_url.rstrip('/')}/password/reset?"
        f"{urlencode({'token': token})}"
    )
    safe_reset_url = escape(reset_url, quote=True)
    text_content = (
        f"Use this link to reset your Flingra password:\n{reset_url}\n\n"
        "This link expires in 30 minutes. If you did not request this, ignore this email."
    )
    html_content = _html_email(
        "Reset your Flingra password. The link expires in 30 minutes.",
        f"""\
<h1 style="margin:0 0 16px;font-size:24px;line-height:1.3;">Reset your password</h1>
<p style="margin:0 0 24px;font-size:16px;line-height:1.6;">Use the button below to choose a new password. This link expires in 30 minutes.</p>
<p style="margin:0 0 24px;">
  <a href="{safe_reset_url}" style="display:inline-block;padding:13px 22px;border-radius:8px;background:#176b4d;color:#ffffff;font-size:16px;font-weight:700;text-decoration:none;">Reset password</a>
</p>
<p style="margin:0 0 8px;color:#69736d;font-size:13px;line-height:1.6;">If the button does not work, copy and paste this link into your browser:</p>
<p style="margin:0;overflow-wrap:anywhere;font-size:13px;line-height:1.6;"><a href="{safe_reset_url}" style="color:#176b4d;">{safe_reset_url}</a></p>""",
    )
    _send_email(
        settings,
        recipient,
        "Reset your Flingra password",
        text_content,
        html_content,
    )
