from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.appointments import service
from app.appointments.schemas import (
    AppointmentCancelIn, AppointmentCreateIn, AppointmentOut,
    AppointmentRescheduleIn, AppointmentStatusIn,
)
from app.core.database import get_db
from app.core.deps import require_permission
from app.identity.models import User

router = APIRouter(prefix="/appointments", tags=["Citas"])


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    data: AppointmentCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("appointments.create")),
):
    return service.crear_cita(db, actor, data)


@router.get("", response_model=list[AppointmentOut])
def list_appointments(
    scheduled_date: date | None = Query(None),
    dentist_id: int | None = Query(None),
    patient_id: int | None = Query(None),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("appointments.view")),
):
    return service.listar_citas(db, actor, scheduled_date, dentist_id, patient_id)


@router.patch("/{appointment_id}/reschedule", response_model=AppointmentOut)
def reschedule_appointment(
    appointment_id: int,
    data: AppointmentRescheduleIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("appointments.edit")),
):
    return service.reprogramar_cita(db, actor, appointment_id, data)


@router.patch("/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel_appointment(
    appointment_id: int,
    data: AppointmentCancelIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("appointments.edit")),
):
    return service.cancelar_cita(db, actor, appointment_id, data)


@router.patch("/{appointment_id}/status", response_model=AppointmentOut)
def change_appointment_status(
    appointment_id: int,
    data: AppointmentStatusIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("appointments.edit")),
):
    return service.cambiar_estado(db, actor, appointment_id, data)
