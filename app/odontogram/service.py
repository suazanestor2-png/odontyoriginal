"""Logica de negocio del odontograma: registrar hallazgos/procedimientos y armar el estado actual."""
from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.appointments.models import Appointment
from app.appointments.service import validar_ventana_de_atencion
from app.catalogs.models import CupsCode
from app.clinical_history.access import log_access
from app.clinical_history.schemas import ClarificationIn
from app.clinical_history.service import aclaraciones, crear_aclaracion
from app.identity.audit import log_event
from app.identity.models import User
from app.odontogram.models import DentalCondition, DentalProcedure, OdontogramEntry
from app.odontogram.schemas import OdontogramEntryCreateIn, OdontogramEntryOut
from app.patients.models import Patient


def to_out(e: OdontogramEntry, db: Session) -> OdontogramEntryOut:
    creator_name = None
    if e.created_by:
        creator = db.get(User, e.created_by)
        creator_name = creator.full_name if creator else None

    return OdontogramEntryOut(
        id=e.id,
        patient_id=e.patient_id,
        patient_name=e.patient.full_name,
        appointment_id=e.appointment_id,
        dentist_id=e.dentist_id,
        dentist_name=e.dentist.full_name,
        tooth_fdi=e.tooth_fdi,
        surface=e.surface,
        condition_code=e.condition.code if e.condition else None,
        condition_name=e.condition.name if e.condition else None,
        procedure_code=e.procedure.code if e.procedure else None,
        procedure_name=e.procedure.name if e.procedure else None,
        cups_code=e.cups_code,
        cups_name=e.cups.name if e.cups else None,
        notes=e.notes,
        created_at=e.created_at,
        created_by=e.created_by,
        created_by_name=creator_name,
        clarifications=aclaraciones(db, odontogram_entry_id=e.id),
    )


def paciente_de_mi_clinica(db: Session, patient_id: int, actor: User) -> Patient:
    patient = db.get(Patient, patient_id)
    if not patient or (actor.role.name != "super_admin" and patient.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    return patient


def registrar_entrada(db: Session, actor: User, data: OdontogramEntryCreateIn) -> OdontogramEntryOut:
    appt = db.get(Appointment, data.appointment_id)
    if not appt or (actor.role.name != "super_admin" and appt.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cita no encontrada")

    if actor.role.name == "odontologo" and appt.dentist_id != actor.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puedes registrar hallazgos de tus propias citas")

    if appt.status == "cancelada":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No se puede registrar en una cita cancelada")

    validar_ventana_de_atencion(appt)

    condition = None
    if data.condition_code:
        condition = db.scalar(select(DentalCondition).where(DentalCondition.code == data.condition_code))
        if not condition:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"condition_code invalido: {data.condition_code}")

    procedure = None
    if data.procedure_code:
        procedure = db.scalar(select(DentalProcedure).where(DentalProcedure.code == data.procedure_code))
        if not procedure:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"procedure_code invalido: {data.procedure_code}")

    cups = None
    if data.cups_code:
        cups = db.get(CupsCode, data.cups_code)
        if not cups or not cups.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"cups_code invalido o no vigente: {data.cups_code}")

    entry = OdontogramEntry(
        clinic_id=appt.clinic_id,
        patient_id=appt.patient_id,
        appointment_id=appt.id,
        dentist_id=appt.dentist_id,
        tooth_fdi=data.tooth_fdi,
        surface=data.surface,
        condition_id=condition.id if condition else None,
        procedure_id=procedure.id if procedure else None,
        cups_code=cups.code if cups else None,
        notes=data.notes,
        created_by=actor.id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    log_event(db, "ODONTOGRAM_ENTRY_CREATED", actor.id, f"entry={entry.id} patient={entry.patient_id} tooth={entry.tooth_fdi}")
    return to_out(entry, db)


def catalogos_dentales(db: Session) -> dict:
    """Hallazgos y procedimientos dentales validos para el formulario del odontograma."""
    def _items(model):
        return [{"code": r.code, "name": r.name} for r in db.scalars(select(model).order_by(model.name))]
    return {"conditions": _items(DentalCondition), "procedures": _items(DentalProcedure)}


def odontograma_actual(db: Session, request: Request, actor: User, patient_id: int) -> list[OdontogramEntryOut]:
    patient = paciente_de_mi_clinica(db, patient_id, actor)

    # Estado actual = la entrada mas reciente por cada combinacion (tooth_fdi, surface).
    # isnot_distinct_from en vez de == porque surface puede ser NULL (diente completo),
    # y NULL = NULL no hace match en SQL.
    latest_subq = (
        select(
            OdontogramEntry.tooth_fdi,
            OdontogramEntry.surface,
            func.max(OdontogramEntry.created_at).label("max_created_at"),
        )
        .where(OdontogramEntry.patient_id == patient_id)
        .group_by(OdontogramEntry.tooth_fdi, OdontogramEntry.surface)
        .subquery()
    )

    query = (
        select(OdontogramEntry)
        .join(
            latest_subq,
            (OdontogramEntry.tooth_fdi == latest_subq.c.tooth_fdi)
            & OdontogramEntry.surface.isnot_distinct_from(latest_subq.c.surface)
            & (OdontogramEntry.created_at == latest_subq.c.max_created_at),
        )
        .where(OdontogramEntry.patient_id == patient_id)
        .order_by(OdontogramEntry.tooth_fdi)
    )

    entries = db.scalars(query).all()
    log_access(db, request, actor, patient.clinic_id, patient.id, "odontograma.ver")
    return [to_out(e, db) for e in entries]


def historial(db: Session, request: Request, actor: User, patient_id: int, tooth_fdi: int | None,
              limit: int, offset: int) -> tuple[list[OdontogramEntryOut], int]:
    patient = paciente_de_mi_clinica(db, patient_id, actor)

    query = select(OdontogramEntry).where(OdontogramEntry.patient_id == patient_id)
    if tooth_fdi is not None:
        query = query.where(OdontogramEntry.tooth_fdi == tooth_fdi)

    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    items = db.scalars(
        query.order_by(OdontogramEntry.created_at.desc()).limit(limit).offset(offset)
    ).all()

    log_access(db, request, actor, patient.clinic_id, patient.id, "odontograma.historial")
    return [to_out(e, db) for e in items], total


def aclarar_entrada(db: Session, actor: User, entry_id: int, data: ClarificationIn) -> OdontogramEntryOut:
    entry = db.get(OdontogramEntry, entry_id)
    if not entry or (actor.role.name != "super_admin" and entry.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registro del odontograma no encontrado")
    crear_aclaracion(db, actor, entry, data, "odontograma")
    db.refresh(entry)
    return to_out(entry, db)
