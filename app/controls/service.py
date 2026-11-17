from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.appointments.models import Appointment
from app.controls.models import PatientControl

BOGOTA_TZ = ZoneInfo("America/Bogota")

# Una cita "cubre" un control si cae desde 14 dias antes hasta 30 dias despues de su fecha.
# Antes de eso es otra consulta (por ejemplo, la misma cita en la que se dejo el control).
MARGEN_ANTES = timedelta(days=14)
MARGEN_DESPUES = timedelta(days=30)
ESTADOS_CITA_ACTIVOS = ("programada", "confirmada")


def today_bogota() -> date:
    return datetime.now(BOGOTA_TZ).date()


def find_covering_appointment(db: Session, control: PatientControl, desde: date | None = None) -> Appointment | None:
    """Primera cita activa del paciente cercana a la fecha del control (y no anterior a 'desde')."""
    inicio = control.due_date - MARGEN_ANTES
    if desde and desde > inicio:
        inicio = desde
    return db.scalar(
        select(Appointment)
        .where(
            Appointment.clinic_id == control.clinic_id,
            Appointment.patient_id == control.patient_id,
            Appointment.status.in_(ESTADOS_CITA_ACTIVOS),
            Appointment.scheduled_date >= inicio,
            Appointment.scheduled_date <= control.due_date + MARGEN_DESPUES,
        )
        .order_by(Appointment.scheduled_date, Appointment.start_time)
    )


def link_controls_to_appointment(db: Session, appt: Appointment) -> int:
    """Al crear una cita, marca como agendados los controles pendientes que esa cita cubre."""
    pendientes = db.scalars(
        select(PatientControl).where(
            PatientControl.clinic_id == appt.clinic_id,
            PatientControl.patient_id == appt.patient_id,
            PatientControl.status == "pendiente",
            PatientControl.due_date >= appt.scheduled_date - MARGEN_DESPUES,
            PatientControl.due_date <= appt.scheduled_date + MARGEN_ANTES,
        )
    ).all()
    for control in pendientes:
        control.status = "agendado"
        control.appointment_id = appt.id
    return len(pendientes)


def unlink_controls_from_appointment(db: Session, appt: Appointment) -> int:
    """Si se cancela la cita (o el paciente no asiste), sus controles vuelven a quedar pendientes."""
    controles = db.scalars(
        select(PatientControl).where(
            PatientControl.appointment_id == appt.id,
            PatientControl.status == "agendado",
        )
    ).all()
    for control in controles:
        control.status = "pendiente"
        control.appointment_id = None
    return len(controles)
