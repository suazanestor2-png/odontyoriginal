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

# Cada clinica configura cuantos dias antes sale cada aviso (0 = desactivado). Las columnas
# conservan el nombre de cuando era fijo: reminder_7d_sent = primer aviso, reminder_3d_sent = segundo.


def ventanas(clinic: Clinic) -> list[tuple[str, int, int, str]]:
    """(bandera, dias minimos, dias maximos, clave del resultado) segun la configuracion de la clinica."""
    primero, segundo = clinic.control_reminder_first_days, clinic.control_reminder_second_days
    salida = []
    if segundo:
        salida.append(("reminder_3d_sent", 0, segundo, "controles_aviso_2"))
    if primero:
        salida.append(("reminder_7d_sent", (segundo + 1) if segundo else 0, primero, "controles_aviso_1"))
    return salida


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
    resultado = {"controles_aviso_1": 0, "controles_aviso_2": 0, "controles_agendados_auto": 0}
    clinicas: dict[int, Clinic] = {}

    candidatos = db.scalars(
        select(PatientControl).where(
            PatientControl.status == "pendiente",
            PatientControl.due_date >= hoy,
        )
    ).all()

    for control in candidatos:
        clinic = clinicas.get(control.clinic_id) or clinicas.setdefault(control.clinic_id, db.get(Clinic, control.clinic_id))
        dias = (control.due_date - hoy).days
        ventana = next(
            (v for v in ventanas(clinic) if v[1] <= dias <= v[2] and not getattr(control, v[0])),
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
        if ventana[0] == "reminder_3d_sent":
            control.reminder_7d_sent = True  # si ya toca el segundo, el primero ya no tiene sentido
        resultado[ventana[3]] += 1

    db.commit()
    return resultado
