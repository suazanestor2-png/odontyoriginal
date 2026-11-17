from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.appointments.models import Appointment
from app.clinics.models import Clinic
from app.email_service import send_appointment_reminder_email

BOGOTA_TZ = ZoneInfo("America/Bogota")

# Cada clinica configura cuantas horas antes sale cada recordatorio (0 = desactivado).
# Las columnas de la cita conservan el nombre de cuando era fijo (24 h y 1 h):
# reminder_24h_sent = primer recordatorio, reminder_1h_sent = segundo recordatorio.
RECORDATORIOS = (
    ("reminder_24h_sent", "appointment_reminder_first_hours", "recordatorios_primero"),
    ("reminder_1h_sent", "appointment_reminder_second_hours", "recordatorios_segundo"),
)
MAX_HORAS = 168


def _now_bogota() -> datetime:
    return datetime.now(BOGOTA_TZ).replace(tzinfo=None)


def _appointment_datetime(appt: Appointment) -> datetime:
    return datetime.combine(appt.scheduled_date, appt.start_time)


def ventana(horas: int) -> tuple[timedelta, timedelta]:
    """
    Rango de tiempo restante en el que se envia el recordatorio. El cron corre cada 15 minutos,
    asi que el margen garantiza que ninguna cita se quede sin aviso (24 h -> entre 23 y 25 h; 1 h -> entre 30 y 90 min).
    """
    margen = timedelta(minutes=30) if horas <= 2 else timedelta(hours=1)
    objetivo = timedelta(hours=horas)
    return objetivo - margen, objetivo + margen


def run_appointment_reminders(db: Session) -> dict:
    now = _now_bogota()
    resultado = {clave: 0 for _, _, clave in RECORDATORIOS}

    candidatas = db.scalars(
        select(Appointment).where(
            Appointment.status != "cancelada",
            Appointment.scheduled_date >= now.date(),
            Appointment.scheduled_date <= (now + timedelta(hours=MAX_HORAS + 1)).date(),
            Appointment.reminder_24h_sent.is_(False) | Appointment.reminder_1h_sent.is_(False),
        )
    ).all()

    clinicas: dict[int, Clinic] = {}
    for appt in candidatas:
        clinic = clinicas.get(appt.clinic_id) or clinicas.setdefault(appt.clinic_id, db.get(Clinic, appt.clinic_id))
        restante = _appointment_datetime(appt) - now
        if restante <= timedelta(0):
            continue

        # Recordatorios que tocan ahora (activos, sin enviar y dentro de su ventana)
        vencidos = []
        for flag, campo, clave in RECORDATORIOS:
            horas = getattr(clinic, campo)
            if not horas or getattr(appt, flag):
                continue
            inicio, fin = ventana(horas)
            if inicio <= restante <= fin:
                vencidos.append((flag, horas, clave))
        if not vencidos:
            continue

        # Si coinciden los dos (ej. la cita se agendo con poca anticipacion), se envia solo el
        # mas cercano a la cita y los dos quedan marcados, para no mandar dos correos seguidos.
        _, horas, clave = min(vencidos, key=lambda v: v[1])
        patient = appt.patient
        if patient and patient.email:
            send_appointment_reminder_email(
                to_email=patient.email,
                patient_name=patient.full_name,
                dentist_name=appt.dentist.full_name,
                scheduled_date=appt.scheduled_date,
                start_time=appt.start_time,
                hours_before=horas,
            )
            resultado[clave] += 1
        for flag, _, _ in vencidos:
            setattr(appt, flag, True)

    db.commit()
    return resultado
