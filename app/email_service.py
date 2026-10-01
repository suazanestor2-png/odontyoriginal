import smtplib
from email.message import EmailMessage

from app.config import settings


def send_email(to: str, subject: str, body: str, html_body: str | None = None) -> None:
    if not settings.SMTP_HOST:
        print(f"\n[DEV EMAIL] Para: {to}")
        print(f"[DEV EMAIL] Asunto: {subject}")
        print(f"[DEV EMAIL] {body}\n")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg.set_content(body)  # version en texto plano, como respaldo

    if html_body:
        msg.add_alternative(html_body, subtype="html")  # version bonita

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)