"""Logica de negocio de pacientes.

El router solo recibe la peticion, valida el permiso y llama a estas funciones.
"""
from fastapi import HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.clinical_history.access import log_access
from app.core.validators import _documento, _telefono
from app.identity.audit import log_event
from app.identity.models import User
from app.patients.models import Patient
from app.patients.schemas import (
    MENSAJE_RESPONSABLE,
    PatientAlertsOut,
    PatientCheckOut,
    PatientCreateIn,
    PatientUpdateIn,
    falta_responsable,
)

CAMPOS_OBLIGATORIOS = ("full_name", "document_type", "document_number", "email", "phone_number")


def normalizar(values: dict) -> dict:
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


def buscar_por_documento(db: Session, clinic_id: int, document_type: str, document_number: str) -> Patient | None:
    return db.scalar(
        select(Patient).where(
            Patient.clinic_id == clinic_id,
            Patient.document_type == document_type,
            Patient.document_number == document_number,
        )
    )


def paciente_de_mi_clinica(db: Session, patient_id: int, actor: User) -> Patient:
    patient = db.get(Patient, patient_id)
    if not patient or (actor.role.name != "super_admin" and patient.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    return patient


def _error_duplicado(duplicado: Patient) -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        f"Ya existe un paciente con ese documento en esta clinica (id={duplicado.id})",
    )


def registrar_paciente(db: Session, actor: User, data: PatientCreateIn) -> Patient:
    if not actor.clinic_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tu usuario no pertenece a ninguna clinica")

    values = normalizar(data.model_dump())
    duplicado = buscar_por_documento(db, actor.clinic_id, values["document_type"], values["document_number"])
    if duplicado:
        raise _error_duplicado(duplicado)

    patient = Patient(clinic_id=actor.clinic_id, **values)
    db.add(patient)
    db.commit()
    db.refresh(patient)
    log_event(db, "PATIENT_REGISTERED", actor.id, f"patient={patient.id}")
    return patient


def listar_pacientes(db: Session, actor: User, search: str | None, limit: int, offset: int) -> tuple[list[Patient], int]:
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
    return items, total


def verificar_documento(db: Session, actor: User, document_type: str, document_number: str) -> PatientCheckOut:
    patient = buscar_por_documento(db, actor.clinic_id, document_type, document_number.strip())
    if not patient:
        return PatientCheckOut(exists=False, patient_id=None, full_name=None)
    return PatientCheckOut(exists=True, patient_id=patient.id, full_name=patient.full_name)


def alertas_del_paciente(db: Session, request: Request, actor: User, patient_id: int) -> PatientAlertsOut:
    patient = paciente_de_mi_clinica(db, patient_id, actor)

    def _limpio(texto: str | None) -> str | None:
        return texto.strip() if texto and texto.strip() else None

    alergias = _limpio(patient.allergies)
    medicamentos = _limpio(patient.current_medications)
    condiciones = _limpio(patient.medical_conditions)
    log_access(db, request, actor, patient.clinic_id, patient.id, "alertas.ver")
    return PatientAlertsOut(
        patient_id=patient.id,
        full_name=patient.full_name,
        allergies=alergias,
        current_medications=medicamentos,
        medical_conditions=condiciones,
        has_alerts=any((alergias, medicamentos, condiciones)),
    )


def actualizar_paciente(db: Session, actor: User, patient_id: int, data: PatientUpdateIn) -> Patient:
    patient = paciente_de_mi_clinica(db, patient_id, actor)
    values = normalizar(data.model_dump(exclude_unset=True))

    for campo in CAMPOS_OBLIGATORIOS:
        if campo in values and values[campo] is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El campo {campo} no puede quedar vacio")

    nuevo_tipo = values.get("document_type", patient.document_type)
    nuevo_numero = values.get("document_number", patient.document_number)
    if (nuevo_tipo, nuevo_numero) != (patient.document_type, patient.document_number):
        duplicado = buscar_por_documento(db, patient.clinic_id, nuevo_tipo, nuevo_numero)
        if duplicado:
            raise _error_duplicado(duplicado)

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
