from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.consents.models import PatientConsent, PrivacyPolicy
from app.consents.schemas import (
    ConsentCreateIn, ConsentOut, ConsentRevokeIn, ConsentStatusOut, PendingPatientOut, PolicyCreateIn, PolicyOut,
)
from app.consents.service import consent_out, get_current_policy, latest_consent
from app.core.database import get_db
from app.core.deps import require_permission
from app.identity.audit import log_event
from app.identity.models import User
from app.patients.models import Patient

router = APIRouter(prefix="/consents", tags=["Consentimiento de datos"])


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _clinica(actor: User) -> int:
    if not actor.clinic_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tu usuario no pertenece a ninguna clinica")
    return actor.clinic_id


def _paciente(db: Session, patient_id: int, actor: User) -> Patient:
    patient = db.get(Patient, patient_id)
    if not patient or (actor.role.name != "super_admin" and patient.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    return patient


# ---------- Politica de tratamiento ----------

@router.get("/policies/current", response_model=PolicyOut)
def current_policy(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("patients.view")),
):
    """Texto vigente que se le muestra al paciente para que lo autorice."""
    policy = get_current_policy(db, _clinica(actor))
    db.commit()
    return policy


@router.get("/policies", response_model=list[PolicyOut])
def list_policies(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinic.settings")),
):
    clinic_id = _clinica(actor)
    get_current_policy(db, clinic_id)
    db.commit()
    return db.scalars(
        select(PrivacyPolicy).where(PrivacyPolicy.clinic_id == clinic_id).order_by(PrivacyPolicy.id.desc())
    ).all()


@router.post("/policies", response_model=PolicyOut, status_code=status.HTTP_201_CREATED)
def publish_policy(
    data: PolicyCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinic.settings")),
):
    """Publica una version nueva de la politica. Las anteriores se conservan (son prueba de lo que se acepto)."""
    clinic_id = _clinica(actor)
    get_current_policy(db, clinic_id)
    repetida = db.scalar(select(PrivacyPolicy).where(
        PrivacyPolicy.clinic_id == clinic_id, PrivacyPolicy.version == data.version.strip()
    ))
    if repetida:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una politica con esa version")

    db.execute(update(PrivacyPolicy).where(PrivacyPolicy.clinic_id == clinic_id).values(is_current=False))
    policy = PrivacyPolicy(clinic_id=clinic_id, version=data.version.strip(), text=data.text.strip(),
                           is_current=True, created_by=actor.id)
    db.add(policy)
    db.commit()
    db.refresh(policy)
    log_event(db, "PRIVACY_POLICY_PUBLISHED", actor.id, f"clinic={clinic_id} version={policy.version}")
    return policy


# ---------- Autorizaciones de los pacientes ----------

@router.post("", response_model=ConsentOut, status_code=status.HTTP_201_CREATED)
def register_consent(
    data: ConsentCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("consents.manage")),
):
    """Registra que el paciente (o su acudiente) autorizo la politica vigente."""
    patient = _paciente(db, data.patient_id, actor)

    if patient.is_minor:
        if not (data.signer_name and data.signer_document and data.signer_relationship):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "El paciente es menor de edad: la autorizacion la firma su acudiente "
                "(signer_name, signer_document y signer_relationship son obligatorios)",
            )
        nombre, documento, parentesco = data.signer_name, data.signer_document, data.signer_relationship
    else:
        nombre = data.signer_name or patient.full_name
        documento = data.signer_document or patient.document_number
        parentesco = data.signer_relationship

    actual = latest_consent(db, patient.id)
    policy = get_current_policy(db, patient.clinic_id)
    if actual and actual.revoked_at is None and actual.policy_id == policy.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "El paciente ya autorizo la version vigente de la politica")

    consent = PatientConsent(
        clinic_id=patient.clinic_id, patient_id=patient.id, policy_id=policy.id, method=data.method,
        accepted_at=_ahora(), signer_name=nombre.strip(), signer_document=documento.strip(),
        signer_relationship=parentesco, evidence_url=data.evidence_url, notes=data.notes, created_by=actor.id,
    )
    db.add(consent)
    db.commit()
    db.refresh(consent)
    log_event(db, "CONSENT_REGISTERED", actor.id, f"patient={patient.id} consent={consent.id} version={policy.version}")
    return consent_out(consent)


@router.get("/pending", response_model=list[PendingPatientOut])
def pending_consents(
    response: Response,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("consents.manage")),
):
    """Pacientes sin autorizacion valida o que autorizaron una version anterior de la politica."""
    clinic_id = _clinica(actor)
    policy = get_current_policy(db, clinic_id)
    db.commit()

    ultima = (
        select(PatientConsent.patient_id, func.max(PatientConsent.id).label("consent_id"))
        .where(PatientConsent.clinic_id == clinic_id)
        .group_by(PatientConsent.patient_id)
        .subquery()
    )
    filas = db.execute(
        select(Patient, PatientConsent)
        .outerjoin(ultima, ultima.c.patient_id == Patient.id)
        .outerjoin(PatientConsent, PatientConsent.id == ultima.c.consent_id)
        .where(Patient.clinic_id == clinic_id)
        .order_by(Patient.full_name)
    ).all()

    pendientes = []
    for patient, consent in filas:
        if consent is None:
            motivo = "sin_autorizacion"
        elif consent.revoked_at is not None:
            motivo = "revocada"
        elif consent.policy_id != policy.id:
            motivo = "version_anterior"
        else:
            continue
        pendientes.append(PendingPatientOut(
            patient_id=patient.id, patient_name=patient.full_name,
            document=f"{patient.document_type} {patient.document_number}",
            phone_number=patient.phone_number, reason=motivo,
        ))
    response.headers["X-Total-Count"] = str(len(pendientes))
    return pendientes[offset:offset + limit]


@router.get("/patients/{patient_id}", response_model=ConsentStatusOut)
def consent_status(
    patient_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("patients.view")),
):
    """Si el paciente tiene autorizacion vigente (el frontend lo usa para mostrar un aviso)."""
    patient = _paciente(db, patient_id, actor)
    policy = get_current_policy(db, patient.clinic_id)
    db.commit()
    consent = latest_consent(db, patient.id)
    valida = consent is not None and consent.revoked_at is None
    return ConsentStatusOut(
        patient_id=patient.id,
        patient_name=patient.full_name,
        has_valid_consent=valida,
        needs_update=valida and consent.policy_id != policy.id,
        current_policy_version=policy.version,
        consent=consent_out(consent) if consent else None,
    )


@router.get("/patients/{patient_id}/history", response_model=list[ConsentOut])
def consent_history(
    patient_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("consents.manage")),
):
    patient = _paciente(db, patient_id, actor)
    consents = db.scalars(
        select(PatientConsent).where(PatientConsent.patient_id == patient.id).order_by(PatientConsent.id.desc())
    ).all()
    return [consent_out(c) for c in consents]


@router.post("/{consent_id}/revoke", response_model=ConsentOut)
def revoke_consent(
    consent_id: int,
    data: ConsentRevokeIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("consents.manage")),
):
    """
    El paciente retira su autorizacion (derecho del titular, Ley 1581). La historia clinica NO se
    borra: la clinica tiene el deber legal de conservarla.
    """
    consent = db.get(PatientConsent, consent_id)
    if not consent or (actor.role.name != "super_admin" and consent.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Autorizacion no encontrada")
    if consent.revoked_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La autorizacion ya estaba revocada")

    consent.revoked_at = _ahora()
    consent.revoke_reason = data.reason.strip()
    consent.revoked_by = actor.id
    db.commit()
    db.refresh(consent)
    log_event(db, "CONSENT_REVOKED", actor.id, f"patient={consent.patient_id} consent={consent.id}")
    return consent_out(consent)
