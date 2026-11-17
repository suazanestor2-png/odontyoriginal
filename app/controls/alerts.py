from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clinics.models import Clinic
from app.controls.models import PatientControl
from app.controls.service import find_covering_appointment, today_bogota
from app.email_service import send_control_reminder_email
from app.identity.models import Role, User
from app.notifications.models import Notification

TIPO_NOTIFICACION = "proximo_control"

# (bandera, dias minimos, dias maximos) que faltan para el control
VENTANAS = (
    ("reminder_7d_sent", 4, 7),
    ("reminder_3d_sent", 0, 3),
)


def _destinatarios_personal(db: Session, clinic_id: int) -> list[User]:
    """Recepcionistas activas de la clinica; si no hay ninguna, los admins."""
    for rol in ("recepcionista", "admin"):
        usuarios = db.scalars(
            select(User).join(Role, User.role_id == Role.id).where(
                User.clinic_id == clinic_id,
                User.is_active.is_(True),
                Role.name == rol,
            )
        ).all()
        if usuarios:
            return list(usuarios)
    return []


def _avisar(db: Session, control: PatientControl, dias: int) -> None:
    patient = control.patient
    clinic = db.get(Clinic, control.clinic_id)
    fecha_str = control.due_date.strftime("%d/%m/%Y")

    if patient.email:
        send_control_reminder_email(
            to_email=patient.email,
            patient_name=patient.full_name,
            clinic_name=clinic.name if clinic else "la clinica",
            due_date=control.due_date,
            days_left=dias,
            reason=control.reason,
        )

    for user in _destinatarios_personal(db, control.clinic_id):
        db.add(Notification(
            clinic_id=control.clinic_id,
            user_id=user.id,
            type=TIPO_NOTIFICACION,
            title="Paciente proximo a control",
            message=(
                f"{patient.full_name} tiene un control el {fecha_str} (faltan {dias} dias) "
                f"y aun no tiene cita. Motivo: {control.reason}. Telefono: {patient.phone_number}"
            ),
            patient_id=patient.id,
        ))


def run_control_alerts(db: Session, hoy: date | None = None) -> dict:
    hoy = hoy or today_bogota()
    resultado = {"controles_7d": 0, "controles_3d": 0, "controles_agendados_auto": 0}

    candidatos = db.scalars(
        select(PatientControl).where(
            PatientControl.status == "pendiente",
            PatientControl.due_date >= hoy,
        )
    ).all()

    for control in candidatos:
        dias = (control.due_date - hoy).days
        ventana = next(
            (v for v in VENTANAS if v[1] <= dias <= v[2] and not getattr(control, v[0])),
            None,
        )
        if not ventana:
            continue

        # Si ya tiene una cita que lo cubre, no hay que avisar: queda agendado solo
        cita = find_covering_appointment(db, control, desde=hoy)
        if cita:
            control.status = "agendado"
            control.appointment_id = cita.id
            resultado["controles_agendados_auto"] += 1
            continue

        _avisar(db, control, dias)
        setattr(control, ventana[0], True)
        resultado["controles_7d" if ventana[0] == "reminder_7d_sent" else "controles_3d"] += 1

    db.commit()
    return resultado
