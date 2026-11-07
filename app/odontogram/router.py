from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.appointments.models import Appointment
from app.core.database import get_db
from app.core.deps import require_permission
from app.identity.audit import log_event
from app.identity.models import User
from app.odontogram.models import DentalCondition, DentalProcedure, OdontogramEntry
from app.odontogram.schemas import OdontogramEntryCreateIn, OdontogramEntryOut
from app.patients.models import Patient

router = APIRouter(prefix="/odontogram", tags=["Odontograma"])


def _to_out(e: OdontogramEntry, db: Session) -> OdontogramEntryOut:
    creator_name = None
    if e.created_by:
        creator = db.get(User, e.created_by)
        creator_name = creator.full_name if creator else None

    return OdontogramEntryOut(
        id=e.id,
        patient_id=e.patient_id,
        patient_name=e.patient.user.full_name,
        appointment_id=e.appointment_id,
        dentist_id=e.dentist_id,
        dentist_name=e.dentist.full_name,
        tooth_fdi=e.tooth_fdi,
        surface=e.surface,
        condition_code=e.condition.code if e.condition else None,
        condition_name=e.condition.name if e.condition else None,
        procedure_code=e.procedure.code if e.procedure else None,
        procedure_name=e.procedure.name if e.procedure else None,
        notes=e.notes,
        created_at=e.created_at,
        created_by=e.created_by,
        created_by_name=creator_name,
    )


@router.post("", response_model=OdontogramEntryOut, status_code=status.HTTP_201_CREATED)
def create_odontogram_entry(
    data: OdontogramEntryCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("odontogram.create")),
):
    appt = db.get(Appointment, data.appointment_id)
    if not appt or (actor.role.name != "super_admin" and appt.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cita no encontrada")

    if actor.role.name == "odontologo" and appt.dentist_id != actor.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puedes registrar hallazgos de tus propias citas")

    if appt.status == "cancelada":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No se puede registrar en una cita cancelada")

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

    entry = OdontogramEntry(
        clinic_id=appt.clinic_id,
        patient_id=appt.patient_id,
        appointment_id=appt.id,
        dentist_id=appt.dentist_id,
        tooth_fdi=data.tooth_fdi,
        surface=data.surface,
        condition_id=condition.id if condition else None,
        procedure_id=procedure.id if procedure else None,
        notes=data.notes,
        created_by=actor.id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    log_event(db, "ODONTOGRAM_ENTRY_CREATED", actor.id, f"entry={entry.id} patient={entry.patient_id} tooth={entry.tooth_fdi}")
    return _to_out(entry, db)


@router.get("/{patient_id}", response_model=list[OdontogramEntryOut])
def get_current_odontogram(
    patient_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("odontogram.view")),
):
    patient = db.get(Patient, patient_id)
    if not patient or (actor.role.name != "super_admin" and patient.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")

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
    return [_to_out(e, db) for e in entries]

@router.get("/{patient_id}/history", response_model=list[OdontogramEntryOut])
def get_odontogram_history(
    patient_id: int,
    response: Response,
    tooth_fdi: int | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("odontogram.view")),
):
    patient = db.get(Patient, patient_id)
    if not patient or (actor.role.name != "super_admin" and patient.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")

    query = select(OdontogramEntry).where(OdontogramEntry.patient_id == patient_id)
    if tooth_fdi is not None:
        query = query.where(OdontogramEntry.tooth_fdi == tooth_fdi)

    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    items = db.scalars(
        query.order_by(OdontogramEntry.created_at.desc()).limit(limit).offset(offset)
    ).all()

    response.headers["X-Total-Count"] = str(total)
    return [_to_out(e, db) for e in items]