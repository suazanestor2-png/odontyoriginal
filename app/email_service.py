import html
import json
import logging
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from app.core.config import settings

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


def send_welcome_email(to_email: str, full_name: str, temp_password: str) -> None:
    safe_name = html.escape(full_name)
    safe_pwd = html.escape(temp_password)  # la clave puede traer "&", hay que escaparla en HTML

    text_body = (
        f"Hola {full_name},\n\n"
        "Se creo tu cuenta en Odonty.\n"
        f"Tu contrasena temporal es: {temp_password}\n\n"
        "Por seguridad, el sistema te pedira cambiarla la primera vez que ingreses.\n"
        "Si no esperabas este mensaje, ignoralo."
    )
    html_body = f"""\
<html>
  <body style="font-family: Arial, sans-serif; background-color: #f4f4f7; padding: 24px;">
    <div style="max-width: 480px; margin: 0 auto; background: #ffffff; border-radius: 8px; padding: 32px;">
      <h2 style="color: #1a1a2e; margin-top: 0;">Bienvenido a Odonty</h2>
      <p style="color: #333; font-size: 15px;">Hola <strong>{safe_name}</strong>, se creo tu cuenta.</p>
      <p style="color: #333; font-size: 15px;">Tu contrasena temporal es:</p>
      <div style="text-align: center; margin: 24px 0;">
        <span style="display: inline-block; font-size: 22px; font-family: monospace; font-weight: bold; color: #4f46e5; background: #eef2ff; padding: 14px 20px; border-radius: 8px;">{safe_pwd}</span>
      </div>
      <p style="color: #666; font-size: 13px;">Por seguridad, deberas cambiarla la primera vez que ingreses.</p>
    </div>
  </body>
</html>
"""
    send_email(to=to_email, subject="Tu cuenta en Odonty", body=text_body, html_body=html_body)