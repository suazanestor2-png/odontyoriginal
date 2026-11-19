"""Logica de negocio de las citas: validaciones de horario, cruces y cambios de estado."""
from datetime import date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.appointments.models import Appointment
from app.appointments.schemas import (
    AppointmentCancelIn, AppointmentCreateIn, AppointmentOut,
    AppointmentRescheduleIn, AppointmentStatusIn,
)
from app.clinics.models import Clinic
from app.controls.service import link_controls_to_appointment, unlink_controls_from_appointment
from app.core.dates import now_bogota
from app.identity.audit import log_event
from app.identity.models import User
from app.patients.models import Patient

ESTADOS_ACTIVOS = ("programada", "confirmada")

# Resolucion 1995 de 1999: la historia clinica se registra de forma "simultanea o inmediatamente
# despues" de la atencion. Se permite desde que empieza la cita hasta 2 horas despues de terminar.
MARGEN_REGISTRO_CLINICO = timedelta(hours=2)

def to_out(a: Appointment) -> AppointmentOut:
    return AppointmentOut(
        id=a.id, patient_id=a.patient_id, patient_name=a.patient.full_name,
        dentist_id=a.dentist_id, dentist_name=a.dentist.full_name,
        scheduled_date=a.scheduled_date, start_time=a.start_time, end_time=a.end_time,
        reason=a.reason, origin=a.origin, status=a.status, cancellation_reason=a.cancellation_reason,
    )


def validar_horario_clinica(db: Session, clinic_id: int, fecha: date, inicio, fin):
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


def validar_cruce(db: Session, dentist_id: int, fecha: date, inicio, fin, excluir_id: int | None = None):
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


def validar_ventana_de_atencion(appt: Appointment) -> None:
    """Historia clinica y odontograma solo se registran durante la cita o hasta 2 horas despues."""
    if appt.status == "no_asistio":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El paciente no asistio a esta cita")
    inicio = datetime.combine(appt.scheduled_date, appt.start_time)
    limite = datetime.combine(appt.scheduled_date, appt.end_time) + MARGEN_REGISTRO_CLINICO
    ahora = now_bogota()
    if ahora < inicio:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"La cita aun no ha empezado: podras registrar desde el {inicio:%Y-%m-%d} a las {inicio:%H:%M}",
        )
    if ahora > limite:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Ya paso el tiempo para registrar en esta cita (hasta 2 horas despues de terminar). "
            "Si necesitas corregir algo, agrega una nota aclaratoria.",
        )


def get_appt_or_404(db: Session, appointment_id: int, actor: User) -> Appointment:
    appt = db.get(Appointment, appointment_id)
    if not appt or (actor.role.name != "super_admin" and appt.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cita no encontrada")
    return appt


def crear_cita(db: Session, actor: User, data: AppointmentCreateIn) -> AppointmentOut:
    patient = db.get(Patient, data.patient_id)
    if not patient or (actor.role.name != "super_admin" and patient.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")

    dentist = db.get(User, data.dentist_id)
    if not dentist or dentist.role.name != "odontologo" or dentist.clinic_id != patient.clinic_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El odontologo indicado no es valido para esta clinica")

    end_time = data.end_time
    if end_time is None:
        minutos = db.get(Clinic, patient.clinic_id).default_appointment_minutes or 30
        fin = datetime.combine(data.scheduled_date, data.start_time) + timedelta(minutes=minutos)
        if fin.date() != data.scheduled_date:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "La cita no puede pasar de medianoche")
        end_time = fin.time()

    validar_horario_clinica(db, patient.clinic_id, data.scheduled_date, data.start_time, end_time)
    validar_cruce(db, data.dentist_id, data.scheduled_date, data.start_time, end_time)

    appt = Appointment(
        clinic_id=patient.clinic_id,
        patient_id=data.patient_id,
        dentist_id=data.dentist_id,
        scheduled_date=data.scheduled_date,
        start_time=data.start_time,
        end_time=end_time,
        reason=data.reason,
        origin=data.origin,
    )
    db.add(appt)
    db.flush()
    # Si el paciente tenia un control pendiente cerca de esta fecha, queda agendado con esta cita
    link_controls_to_appointment(db, appt)
    db.commit()
    db.refresh(appt)
    log_event(db, "APPOINTMENT_CREATED", actor.id, f"appointment={appt.id}")
    return to_out(appt)


def listar_citas(db: Session, actor: User, scheduled_date: date | None, dentist_id: int | None,
                 patient_id: int | None) -> list[AppointmentOut]:
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
    return [to_out(a) for a in items]


def reprogramar_cita(db: Session, actor: User, appointment_id: int, data: AppointmentRescheduleIn) -> AppointmentOut:
    appt = get_appt_or_404(db, appointment_id, actor)
    if appt.status not in ESTADOS_ACTIVOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo se pueden reprogramar citas programadas o confirmadas")

    validar_horario_clinica(db, appt.clinic_id, data.scheduled_date, data.start_time, data.end_time)
    validar_cruce(db, appt.dentist_id, data.scheduled_date, data.start_time, data.end_time, excluir_id=appt.id)

    appt.scheduled_date = data.scheduled_date
    appt.start_time = data.start_time
    appt.end_time = data.end_time
    appt.status = "programada"
    db.commit()
    db.refresh(appt)
    log_event(db, "APPOINTMENT_RESCHEDULED", actor.id, f"appointment={appt.id}")
    return to_out(appt)


def cancelar_cita(db: Session, actor: User, appointment_id: int, data: AppointmentCancelIn) -> AppointmentOut:
    appt = get_appt_or_404(db, appointment_id, actor)
    if appt.status not in ESTADOS_ACTIVOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta cita ya no se puede cancelar")

    appt.status = "cancelada"
    appt.cancellation_reason = data.cancellation_reason
    # Los controles que dependian de esta cita vuelven a quedar pendientes
    unlink_controls_from_appointment(db, appt)
    db.commit()
    db.refresh(appt)
    log_event(db, "APPOINTMENT_CANCELLED", actor.id, f"appointment={appt.id}")
    return to_out(appt)


def cambiar_estado(db: Session, actor: User, appointment_id: int, data: AppointmentStatusIn) -> AppointmentOut:
    appt = get_appt_or_404(db, appointment_id, actor)
    if appt.status not in ESTADOS_ACTIVOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta cita ya no se puede actualizar")

    appt.status = data.status
    if data.status == "no_asistio":
        # No vino: el control que cubria esta cita vuelve a quedar pendiente
        unlink_controls_from_appointment(db, appt)
    db.commit()
    db.refresh(appt)
    log_event(db, "APPOINTMENT_STATUS_CHANGED", actor.id, f"appointment={appt.id} status={data.status}")
    return to_out(appt)
