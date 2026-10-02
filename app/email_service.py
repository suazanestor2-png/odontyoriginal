import json
import logging
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def _send_with_brevo(to: str, subject: str, body: str, html_body: str | None) -> None:
    payload = {
        "sender": {"email": settings.SMTP_FROM, "name": "Odonty"},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": body,
    }
    if html_body:
        payload["htmlContent"] = html_body

    req = urllib.request.Request(
        BREVO_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "api-key": settings.BREVO_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "odonty-api/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10):
        pass


def _send_with_smtp(to: str, subject: str, body: str, html_body: str | None) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg.set_content(body)  # version en texto plano, como respaldo

    if html_body:
        msg.add_alternative(html_body, subtype="html")  # version bonita

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)


def send_email(to: str, subject: str, body: str, html_body: str | None = None) -> None:
    try:
        if settings.BREVO_API_KEY:
            _send_with_brevo(to, subject, body, html_body)
        elif settings.SMTP_HOST:
            _send_with_smtp(to, subject, body, html_body)
        else:
            print(f"\n[DEV EMAIL] Para: {to}")
            print(f"[DEV EMAIL] Asunto: {subject}")
            print(f"[DEV EMAIL] {body}\n")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        logger.error("Brevo rechazo el correo (%s): %s", e.code, detail)
    except Exception:
        logger.exception("No se pudo enviar el correo")