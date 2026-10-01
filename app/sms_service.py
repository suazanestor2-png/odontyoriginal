from twilio.rest import Client

from app.config import settings


def send_sms(to: str, body: str) -> None:
    if not settings.TWILIO_ACCOUNT_SID:
        print(f"\n[DEV SMS] Para: {to}")
        print(f"[DEV SMS] {body}\n")
        return

    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    client.messages.create(
        to=to,
        from_=settings.TWILIO_FROM_NUMBER,
        body=body,
    )