from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.appointments.models import Appointment
from app.controls.models import PatientControl
from app.controls.schemas import ControlCreateIn, ControlOut, ControlUpdateIn
from app.controls.service import crear_control, today_bogota
from app.core.database import get_db
from app.core.deps import require_permission
from app.identity.audit import log_event
from app.identity.models import User
from app.patients.models import Patient

router = APIRouter(prefix="/controls", tags=["Controles"])


def _to_out(c: PatientControl) -> ControlOut:
    return ControlOut(
        id=c.id,
        patient_id=c.patient_id,
        patient_name=c.patient.full_name,
        patient_phone=c.patient.phone_number,
        due_date=c.due_date,
        days_left=(c.due_date - today_bogota()).days,
        reason=c.reason,
        status=c.status,
        appointment_id=c.appointment_id,
        clinical_entry_id=c.clinical_entry_id,
        created_at=c.created_at,
        created_by=c.created_by,
    )


def _get_control_or_404(db: Session, control_id: int, actor: User) -> PatientControl:
    control = db.get(PatientControl, control_id)
    if not control or (actor.role.name != "super_admin" and control.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Control no encontrado")
    return control


def _validar_fecha_futura(due_date: date) -> None:
    if due_date <= today_bogota():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La fecha del control debe ser posterior a hoy")


@router.post("", response_model=ControlOut, status_code=status.HTTP_201_CREATED)
def create_control(
    data: ControlCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("controls.create")),
):
    patient = db.get(Patient, data.patient_id)
    if not patient or (actor.role.name != "super_admin" and patient.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    _validar_fecha_futura(data.due_date)

    control = crear_control(db, patient, data.due_date, data.reason, actor)
    db.commit()
    db.refresh(control)
    log_event(db, "CONTROL_CREATED", actor.id, f"control={control.id} patient={patient.id}")
    return _to_out(control)


@router.get("", response_model=list[ControlOut])
def list_controls(
    response: Response,
    patient_id: int | None = Query(None),
    status_filter: str | None = Query(None, alias="status", pattern=r"^(pendiente|agendado|cancelado)$"),
    from_date: date | None = Query(None, description="Controles con fecha desde (incluida)"),
    to_date: date | None = Query(None, description="Controles con fecha hasta (incluida)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("controls.view")),
):
    query = select(PatientControl)
    if actor.role.name != "super_admin":
        query = query.where(PatientControl.clinic_id == actor.clinic_id)
    if patient_id:
        query = query.where(PatientControl.patient_id == patient_id)
    if status_filter:
        query = query.where(PatientControl.status == status_filter)
    if from_date:
        query = query.where(PatientControl.due_date >= from_date)
    if to_date:
        query = query.where(PatientControl.due_date <= to_date)

    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    items = db.scalars(query.order_by(PatientControl.due_date, PatientControl.id).limit(limit).offset(offset)).all()

    response.headers["X-Total-Count"] = str(total)
    return [_to_out(c) for c in items]


@router.get("/{control_id}", response_model=ControlOut)
def get_control(
    control_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("controls.view")),
):
    return _to_out(_get_control_or_404(db, control_id, actor))


@router.patch("/{control_id}", response_model=ControlOut)
def update_control(
    control_id: int,
    data: ControlUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("controls.edit")),
):
    control = _get_control_or_404(db, control_id, actor)
    values = data.model_dump(exclude_unset=True)

    if "due_date" in values and values["due_date"] is not None and values["due_date"] != control.due_date:
        _validar_fecha_futura(values["due_date"])
        control.due_date = values["due_date"]
        # Fecha nueva: los avisos vuelven a empezar
        control.reminder_7d_sent = False
        control.reminder_3d_sent = False

    if values.get("reason"):
        control.reason = values["reason"].strip()

    if values.get("appointment_id") is not None:
        appt = db.get(Appointment, values["appointment_id"])
        if not appt or appt.clinic_id != control.clinic_id or appt.patient_id != control.patient_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "La cita no corresponde a este paciente")
        if appt.status == "cancelada":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No se puede vincular una cita cancelada")
        control.appointment_id = appt.id
        control.status = "agendado"

    if values.get("status"):
        nuevo = values["status"]
        if nuevo == "agendado" and control.appointment_id is None and values.get("appointment_id") is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Para marcarlo como agendado envia appointment_id")
        if nuevo == "pendiente":
            control.appointment_id = None
        control.status = nuevo

    db.commit()
    db.refresh(control)
    log_event(db, "CONTROL_UPDATED", actor.id, f"control={control.id} status={control.status}")
    return _to_out(control)
