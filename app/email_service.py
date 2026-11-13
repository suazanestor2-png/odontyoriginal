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

def send_clinic_pending_notification(
    to_emails: list[str], clinic_name: str, nit: str, cedula_url: str, rut_url: str, camara_comercio_url: str
) -> None:
    text_body = (
        f"Nueva clinica registrada: {clinic_name} (NIT {nit}).\n"
        "Esta pendiente de revision. Ingresa al panel de administracion para aprobarla o rechazarla.\n\n"
        f"Cedula: {cedula_url}\n"
        f"RUT: {rut_url}\n"
        f"Camara de Comercio: {camara_comercio_url}"
    )
    html_body = f"""\
<html>
  <body style="font-family: Arial, sans-serif; background-color: #f4f4f7; padding: 24px;">
    <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 8px; padding: 32px;">
      <h2 style="color: #1a1a2e; margin-top: 0;">Nueva clinica pendiente</h2>
      <p style="color: #333; font-size: 15px;">
        <strong>{clinic_name}</strong> (NIT {nit}) se acaba de registrar y espera revision.
      </p>
      <p style="color: #666; font-size: 13px; margin-bottom: 24px;">
        Ingresa al panel de administracion para aprobarla o rechazarla.
      </p>
      <p style="color: #333; font-size: 14px; font-weight: bold; margin-bottom: 8px;">Documentos (PDF):</p>
      <ul style="color: #333; font-size: 14px; line-height: 1.8; padding-left: 20px;">
        <li><a href="{cedula_url}" style="color: #2563eb;">Cedula del representante legal</a></li>
        <li><a href="{rut_url}" style="color: #2563eb;">RUT</a></li>
        <li><a href="{camara_comercio_url}" style="color: #2563eb;">Certificado de Camara de Comercio</a></li>
      </ul>
    </div>
  </body>
</html>
"""
    for email in to_emails:
        send_email(to=email, subject="Odonty: nueva clinica pendiente de revision", body=text_body, html_body=html_body)

def send_clinic_registration_received(to_email: str, full_name: str, clinic_name: str) -> None:
    text_body = (
        f"Hola {full_name},\n\n"
        f"Tu registro para {clinic_name} fue recibido correctamente.\n"
        "Nuestro equipo va a revisar tus documentos. Te avisaremos por correo en cuanto se apruebe o rechace."
    )
    html_body = f"""\
<html>
  <body style="font-family: Arial, sans-serif; background-color: #f4f4f7; padding: 24px;">
    <div style="max-width: 480px; margin: 0 auto; background: #ffffff; border-radius: 8px; padding: 32px;">
      <h2 style="color: #1a1a2e; margin-top: 0;">Registro recibido</h2>
      <p style="color: #333; font-size: 15px;">Hola <strong>{full_name}</strong>,</p>
      <p style="color: #333; font-size: 15px;">
        Tu registro para <strong>{clinic_name}</strong> fue recibido correctamente.
      </p>
      <p style="color: #666; font-size: 13px;">
        Nuestro equipo va a revisar tus documentos. Te avisaremos por correo en cuanto se apruebe o rechace tu clinica.
      </p>
    </div>
  </body>
</html>
"""
    send_email(to=to_email, subject="Odonty: tu registro esta en revision", body=text_body, html_body=html_body)

def send_clinic_review_result(to_email: str, clinic_name: str, approved: bool) -> None:
    if approved:
        subject = "Tu clinica fue aprobada - Odonty"
        text_body = f"Buenas noticias: {clinic_name} fue aprobada. Ya puedes iniciar sesion."
        mensaje_html = f"Tu clinica <strong>{clinic_name}</strong> fue aprobada. Ya puedes iniciar sesion."
    else:
        subject = "Tu clinica no fue aprobada - Odonty"
        text_body = f"{clinic_name} no fue aprobada en este momento. Contacta a soporte si tienes preguntas."
        mensaje_html = f"Tu clinica <strong>{clinic_name}</strong> no fue aprobada en este momento. Contacta a soporte si tienes preguntas."

    html_body = f"""\
<html>
  <body style="font-family: Arial, sans-serif; background-color: #f4f4f7; padding: 24px;">
    <div style="max-width: 480px; margin: 0 auto; background: #ffffff; border-radius: 8px; padding: 32px;">
      <h2 style="color: #1a1a2e; margin-top: 0;">Resultado de tu registro</h2>
      <p style="color: #333; font-size: 15px;">{mensaje_html}</p>
    </div>
  </body>
</html>
"""
    send_email(to=to_email, subject=subject, body=text_body, html_body=html_body)


def send_appointment_reminder_email(
    to_email: str,
    patient_name: str,
    dentist_name: str,
    scheduled_date,
    start_time,
    hours_before: int,
) -> None:
    fecha_str = scheduled_date.strftime("%d/%m/%Y")
    hora_str = start_time.strftime("%H:%M")
    cuando = "manana" if hours_before >= 24 else "en 1 hora"

    safe_patient = html.escape(patient_name)
    safe_dentist = html.escape(dentist_name)

    text_body = (
        f"Hola {patient_name},\n\n"
        f"Te recordamos que tienes una cita {cuando} con {dentist_name}.\n"
        f"Fecha: {fecha_str}\n"
        f"Hora: {hora_str}\n\n"
        "Si necesitas reprogramar o cancelar, contacta a la clinica."
    )
    html_body = f"""\
<html>
  <body style="font-family: Arial, sans-serif; background-color: #f4f4f7; padding: 24px;">
    <div style="max-width: 480px; margin: 0 auto; background: #ffffff; border-radius: 8px; padding: 32px;">
      <h2 style="color: #1a1a2e; margin-top: 0;">Recordatorio de cita</h2>
      <p style="color: #333; font-size: 15px;">Hola <strong>{safe_patient}</strong>,</p>
      <p style="color: #333; font-size: 15px;">
        Te recordamos que tienes una cita <strong>{cuando}</strong> con <strong>{safe_dentist}</strong>.
      </p>
      <div style="text-align: center; margin: 24px 0;">
        <span style="display: inline-block; font-size: 18px; font-weight: bold; color: #4f46e5; background: #eef2ff; padding: 14px 20px; border-radius: 8px;">
          {fecha_str} - {hora_str}
        </span>
      </div>
      <p style="color: #666; font-size: 13px;">Si necesitas reprogramar o cancelar, contacta a la clinica.</p>
    </div>
  </body>
</html>
"""
    send_email(to=to_email, subject="Recordatorio de tu cita - Odonty", body=text_body, html_body=html_body)