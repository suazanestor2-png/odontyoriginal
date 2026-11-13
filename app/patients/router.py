from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permission
from app.core.validators import _documento, _telefono
from app.identity.audit import log_event
from app.identity.models import User
from app.patients.models import Patient
from app.patients.schemas import (
    MENSAJE_RESPONSABLE,
    PatientCheckOut,
    PatientCreateIn,
    PatientOut,
    PatientUpdateIn,
    falta_responsable,
)

router = APIRouter(prefix="/patients", tags=["Pacientes"])

CAMPOS_OBLIGATORIOS = ("full_name", "document_type", "document_number", "email", "phone_number")


def _normalizar(values: dict) -> dict:
    try:
        if values.get("document_number") is not None:
            values["document_number"] = _documento(values["document_number"])
        if values.get("phone_number") is not None:
            values["phone_number"] = _telefono(values["phone_number"])
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    if values.get("email") is not None:
        values["email"] = values["email"].strip().lower()
    if values.get("full_name") is not None:
        values["full_name"] = values["full_name"].strip()
    return values


def _buscar_por_documento(db: Session, clinic_id: int, document_type: str, document_number: str) -> Patient | None:
    return db.scalar(
        select(Patient).where(
            Patient.clinic_id == clinic_id,
            Patient.document_type == document_type,
            Patient.document_number == document_number,
        )
    )


def _paciente_de_mi_clinica(db: Session, patient_id: int, actor: User) -> Patient:
    patient = db.get(Patient, patient_id)
    if not patient or (actor.role.name != "super_admin" and patient.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    return patient


@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
def register_patient(
    data: PatientCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("patients.create")),
):
    if not actor.clinic_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tu usuario no pertenece a ninguna clinica")

    values = _normalizar(data.model_dump())

    duplicado = _buscar_por_documento(db, actor.clinic_id, values["document_type"], values["document_number"])
    if duplicado:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Ya existe un paciente con ese documento en esta clinica (id={duplicado.id})",
        )

    patient = Patient(clinic_id=actor.clinic_id, **values)
    db.add(patient)
    db.commit()
    db.refresh(patient)
    log_event(db, "PATIENT_REGISTERED", actor.id, f"patient={patient.id}")
    return patient


@router.get("", response_model=list[PatientOut])
def list_patients(
    response: Response,
    search: str | None = Query(None, description="Busca por nombre, correo o documento"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("patients.view")),
):
    query = select(Patient)
    if actor.role.name != "super_admin":
        query = query.where(Patient.clinic_id == actor.clinic_id)
    if search:
        like = f"%{search.strip()}%"
        query = query.where(
            or_(Patient.full_name.ilike(like), Patient.email.ilike(like), Patient.document_number.ilike(like))
        )

    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    items = db.scalars(query.order_by(Patient.id).limit(limit).offset(offset)).all()

    response.headers["X-Total-Count"] = str(total)
    return items


@router.get("/check", response_model=PatientCheckOut)
def check_patient(
    document_number: str = Query(...),
    document_type: str = Query("CC", pattern=r"^(TI|CC|CE|PA)$"),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("patients.create")),
):
    patient = _buscar_por_documento(db, actor.clinic_id, document_type, document_number.strip())
    if not patient:
        return PatientCheckOut(exists=False, patient_id=None, full_name=None)
    return PatientCheckOut(exists=True, patient_id=patient.id, full_name=patient.full_name)


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("patients.view")),
):
    return _paciente_de_mi_clinica(db, patient_id, actor)


@router.patch("/{patient_id}", response_model=PatientOut)
def update_patient(
    patient_id: int,
    data: PatientUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("patients.edit")),
):
    patient = _paciente_de_mi_clinica(db, patient_id, actor)
    values = _normalizar(data.model_dump(exclude_unset=True))

    for campo in CAMPOS_OBLIGATORIOS:
        if campo in values and values[campo] is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El campo {campo} no puede quedar vacio")

    nuevo_tipo = values.get("document_type", patient.document_type)
    nuevo_numero = values.get("document_number", patient.document_number)
    if (nuevo_tipo, nuevo_numero) != (patient.document_type, patient.document_number):
        duplicado = _buscar_por_documento(db, patient.clinic_id, nuevo_tipo, nuevo_numero)
        if duplicado:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Ya existe un paciente con ese documento en esta clinica (id={duplicado.id})",
            )

    for field, value in values.items():
        setattr(patient, field, value)

    if falta_responsable(
        patient.birth_date, patient.guardian_full_name, patient.guardian_document_number, patient.guardian_phone
    ):
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, MENSAJE_RESPONSABLE)

    db.commit()
    db.refresh(patient)
    log_event(db, "PATIENT_PROFILE_UPDATED", actor.id, f"patient={patient.id}")
    return patient