from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.appointments.models import Appointment
from app.clinical_history.models import ClinicalEntry
from app.clinical_history.schemas import ClinicalEntryCreateIn, ClinicalEntryOut
from app.core.database import get_db
from app.core.deps import get_active_user, require_permission
from app.identity.audit import log_event
from app.identity.models import User
from app.patients.models import Patient

router = APIRouter(prefix="/clinical-history", tags=["Historia clinica"])


# created_by apunta a users.id sin relacion declarada en el modelo (a proposito, para no
# repetir el patron de AmbiguousForeignKeysError que ya tuvimos con User/Role). Por eso
# el nombre de quien escribio la entrada se resuelve aqui con una consulta extra.
def _to_out(e: ClinicalEntry, db: Session) -> ClinicalEntryOut:
    creator_name = None
    if e.created_by:
        creator = db.get(User, e.created_by)
        creator_name = creator.full_name if creator else None

    return ClinicalEntryOut(
        id=e.id,
        patient_id=e.patient_id,
        patient_name=e.patient.user.full_name,
        appointment_id=e.appointment_id,
        dentist_id=e.dentist_id,
        dentist_name=e.dentist.full_name,
        antecedentes=e.antecedentes,
        motivo_consulta=e.motivo_consulta,
        examen=e.examen,
        diagnostico=e.diagnostico,
        tratamiento=e.tratamiento,
        created_at=e.created_at,
        created_by=e.created_by,
        created_by_name=creator_name,
    )


@router.post("", response_model=ClinicalEntryOut, status_code=status.HTTP_201_CREATED)
def create_clinical_entry(
    data: ClinicalEntryCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinical_history.create")),
):
    appt = db.get(Appointment, data.appointment_id)
    if not appt or (actor.role.name != "super_admin" and appt.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cita no encontrada")

    if actor.role.name == "odontologo" and appt.dentist_id != actor.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puedes registrar consultas de tus propias citas")

    if appt.status == "cancelada":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No se puede registrar una consulta para una cita cancelada")

    ya_existe = db.scalar(select(ClinicalEntry).where(ClinicalEntry.appointment_id == appt.id))
    if ya_existe:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta cita ya tiene una consulta registrada")

    entry = ClinicalEntry(
        clinic_id=appt.clinic_id,
        patient_id=appt.patient_id,
        appointment_id=appt.id,
        dentist_id=appt.dentist_id,
        antecedentes=data.antecedentes,
        motivo_consulta=data.motivo_consulta,
        examen=data.examen,
        diagnostico=data.diagnostico,
        tratamiento=data.tratamiento,
        created_by=actor.id,
    )
    db.add(entry)

    if appt.status != "atendida":
        appt.status = "atendida"

    db.commit()
    db.refresh(entry)
    log_event(db, "CLINICAL_ENTRY_CREATED", actor.id, f"entry={entry.id} appointment={appt.id}")
    return _to_out(entry, db)


@router.get("/me", response_model=list[ClinicalEntryOut])
def my_clinical_history(
    db: Session = Depends(get_db),
    actor: User = Depends(get_active_user),
):
    if actor.role.name != "usuario":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Este endpoint es solo para pacientes")

    patient = db.scalar(select(Patient).where(Patient.user_id == actor.id))
    if not patient:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aun no tienes un perfil de paciente")

    entries = db.scalars(
        select(ClinicalEntry).where(ClinicalEntry.patient_id == patient.id).order_by(ClinicalEntry.created_at.desc())
    ).all()
    return [_to_out(e, db) for e in entries]


@router.get("", response_model=list[ClinicalEntryOut])
def list_clinical_history(
    response: Response,
    patient_id: int = Query(...),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinical_history.view")),
):
    patient = db.get(Patient, patient_id)
    if not patient or (actor.role.name != "super_admin" and patient.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")

    query = select(ClinicalEntry).where(ClinicalEntry.patient_id == patient_id)
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    items = db.scalars(query.order_by(ClinicalEntry.created_at.desc()).limit(limit).offset(offset)).all()

    response.headers["X-Total-Count"] = str(total)
    return [_to_out(e, db) for e in items]


@router.get("/{entry_id}", response_model=ClinicalEntryOut)
def get_clinical_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinical_history.view")),
):
    entry = db.get(ClinicalEntry, entry_id)
    if not entry or (actor.role.name != "super_admin" and entry.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entrada no encontrada")
    return _to_out(entry, db)