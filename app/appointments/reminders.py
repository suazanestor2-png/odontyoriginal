from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.appointments.models import Appointment
from app.email_service import send_appointment_reminder_email
from app.notifications.models import Notification

BOGOTA_TZ = ZoneInfo("America/Bogota")


def _now_bogota() -> datetime:
    return datetime.now(BOGOTA_TZ).replace(tzinfo=None)


def _appointment_datetime(appt: Appointment) -> datetime:
    return datetime.combine(appt.scheduled_date, appt.start_time)


def _enviar_ventana(
    db: Session,
    now: datetime,
    delta_min: timedelta,
    delta_max: timedelta,
    flag_attr: str,
    hours_before: int,
) -> int:
    candidatas = db.scalars(
        select(Appointment).where(
            Appointment.status != "cancelada",
            getattr(Appointment, flag_attr).is_(False),
        )
    ).all()

    enviados = 0
    for appt in candidatas:
        cita_dt = _appointment_datetime(appt)
        if now + delta_min <= cita_dt <= now + delta_max:
            patient = appt.patient
            dentist = appt.dentist

            if patient and patient.user and patient.user.email:
                send_appointment_reminder_email(
                    to_email=patient.user.email,
                    patient_name=patient.user.full_name,
                    dentist_name=dentist.full_name,
                    scheduled_date=appt.scheduled_date,
                    start_time=appt.start_time,
                    hours_before=hours_before,
                )
                db.add(Notification(
                    clinic_id=appt.clinic_id,
                    user_id=patient.user_id,
                    type="recordatorio_cita",
                    title="Recordatorio de cita",
                    message=(
                        f"Tienes una cita el {appt.scheduled_date.strftime('%d/%m/%Y')} "
                        f"a las {appt.start_time.strftime('%H:%M')}"
                    ),
                    appointment_id=appt.id,
                    patient_id=appt.patient_id,
                ))

            setattr(appt, flag_attr, True)
            enviados += 1

    db.commit()
    return enviados


def run_appointment_reminders(db: Session) -> dict:
    now = _now_bogota()

    enviados_24h = _enviar_ventana(
        db, now, timedelta(hours=23), timedelta(hours=25), "reminder_24h_sent", hours_before=24
    )
    enviados_1h = _enviar_ventana(
        db, now, timedelta(minutes=30), timedelta(minutes=90), "reminder_1h_sent", hours_before=1
    )

    return {"recordatorios_24h": enviados_24h, "recordatorios_1h": enviados_1h}