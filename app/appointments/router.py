from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.appointments.models import Appointment
from app.appointments.schemas import (
    AppointmentCancelIn, AppointmentCreateIn, AppointmentOut,
    AppointmentRescheduleIn, AppointmentStatusIn,
)
from app.clinics.models import Clinic
from app.core.database import get_db
from app.core.deps import require_permission
from app.identity.audit import log_event
from app.identity.models import User
from app.patients.models import Patient

router = APIRouter(prefix="/appointments", tags=["Citas"])

ESTADOS_ACTIVOS = ("programada", "confirmada")


def _to_out(a: Appointment) -> AppointmentOut:
    return AppointmentOut(
        id=a.id, patient_id=a.patient_id, patient_name=a.patient.full_name,
        dentist_id=a.dentist_id, dentist_name=a.dentist.full_name,
        scheduled_date=a.scheduled_date, start_time=a.start_time, end_time=a.end_time,
        reason=a.reason, origin=a.origin, status=a.status, cancellation_reason=a.cancellation_reason,
    )


def _validar_horario_clinica(db: Session, clinic_id: int, fecha: date, inicio, fin):
    clinic = db.get(Clinic, clinic_id)
    dia_semana = str(fecha.isoweekday())  # 1=lunes ... 7=domingo
    dias_atencion = clinic.working_days.split(",")
    if dia_semana not in dias_atencion:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La clinica no atiende ese dia")
    if inicio < clinic.opening_time or fin > clinic.closing_time:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"La clinica atiende de {clinic.opening_time} a {clinic.closing_time}",
        )


def _validar_cruce(db: Session, dentist_id: int, fecha: date, inicio, fin, excluir_id: int | None = None):
    query = select(Appointment).where(
        Appointment.dentist_id == dentist_id,
        Appointment.scheduled_date == fecha,
        Appointment.status.in_(ESTADOS_ACTIVOS),
        Appointment.start_time < fin,
        Appointment.end_time > inicio,
    )
    if excluir_id:
        query = query.where(Appointment.id != excluir_id)
    cruce = db.scalar(query)
    if cruce:
        raise HTTPException(status.HTTP_409_CONFLICT, "El odontologo ya tiene una cita en ese horario")


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    data: AppointmentCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("appointments.create")),
):
    patient = db.get(Patient, data.patient_id)
    if not patient or (actor.role.name != "super_admin" and patient.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")

    dentist = db.get(User, data.dentist_id)
    if not dentist or dentist.role.name != "odontologo" or dentist.clinic_id != patient.clinic_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El odontologo indicado no es valido para esta clinica")

    _validar_horario_clinica(db, patient.clinic_id, data.scheduled_date, data.start_time, data.end_time)
    _validar_cruce(db, data.dentist_id, data.scheduled_date, data.start_time, data.end_time)

    appt = Appointment(
        clinic_id=patient.clinic_id,
        patient_id=data.patient_id,
        dentist_id=data.dentist_id,
        scheduled_date=data.scheduled_date,
        start_time=data.start_time,
        end_time=data.end_time,
        reason=data.reason,
        origin=data.origin,
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    log_event(db, "APPOINTMENT_CREATED", actor.id, f"appointment={appt.id}")
    return _to_out(appt)


@router.get("", response_model=list[AppointmentOut])
def list_appointments(
    scheduled_date: date | None = Query(None),
    dentist_id: int | None = Query(None),
    patient_id: int | None = Query(None),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("appointments.view")),
):
    query = select(Appointment)
    if actor.role.name != "super_admin":
        query = query.where(Appointment.clinic_id == actor.clinic_id)
    if scheduled_date:
        query = query.where(Appointment.scheduled_date == scheduled_date)
    if dentist_id:
        query = query.where(Appointment.dentist_id == dentist_id)
    if patient_id:
        query = query.where(Appointment.patient_id == patient_id)

    items = db.scalars(query.order_by(Appointment.scheduled_date, Appointment.start_time)).all()
    return [_to_out(a) for a in items]


def _get_appt_or_404(db: Session, appointment_id: int, actor: User) -> Appointment:
    appt = db.get(Appointment, appointment_id)
    if not appt or (actor.role.name != "super_admin" and appt.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cita no encontrada")
    return appt


@router.patch("/{appointment_id}/reschedule", response_model=AppointmentOut)
def reschedule_appointment(
    appointment_id: int,
    data: AppointmentRescheduleIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("appointments.edit")),
):
    appt = _get_appt_or_404(db, appointment_id, actor)
    if appt.status not in ESTADOS_ACTIVOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo se pueden reprogramar citas programadas o confirmadas")

    _validar_horario_clinica(db, appt.clinic_id, data.scheduled_date, data.start_time, data.end_time)
    _validar_cruce(db, appt.dentist_id, data.scheduled_date, data.start_time, data.end_time, excluir_id=appt.id)

    appt.scheduled_date = data.scheduled_date
    appt.start_time = data.start_time
    appt.end_time = data.end_time
    appt.status = "programada"
    db.commit()
    db.refresh(appt)
    log_event(db, "APPOINTMENT_RESCHEDULED", actor.id, f"appointment={appt.id}")
    return _to_out(appt)


@router.patch("/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel_appointment(
    appointment_id: int,
    data: AppointmentCancelIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("appointments.edit")),
):
    appt = _get_appt_or_404(db, appointment_id, actor)
    if appt.status not in ESTADOS_ACTIVOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta cita ya no se puede cancelar")

    appt.status = "cancelada"
    appt.cancellation_reason = data.cancellation_reason
    db.commit()
    db.refresh(appt)
    log_event(db, "APPOINTMENT_CANCELLED", actor.id, f"appointment={appt.id}")
    return _to_out(appt)


@router.patch("/{appointment_id}/status", response_model=AppointmentOut)
def change_appointment_status(
    appointment_id: int,
    data: AppointmentStatusIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("appointments.edit")),
):
    appt = _get_appt_or_404(db, appointment_id, actor)
    if appt.status not in ESTADOS_ACTIVOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta cita ya no se puede actualizar")

    appt.status = data.status
    db.commit()
    db.refresh(appt)
    log_event(db, "APPOINTMENT_STATUS_CHANGED", actor.id, f"appointment={appt.id} status={data.status}")
    return _to_out(appt)