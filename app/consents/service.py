from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clinics.models import Clinic
from app.consents.models import PatientConsent, PrivacyPolicy
from app.consents.schemas import ConsentOut

# Texto base para que la clinica no arranque en blanco. Cada clinica debe revisarlo
# (idealmente con un abogado) y publicar su propia version con POST /consents/policies.
PLANTILLA = """AUTORIZACION PARA EL TRATAMIENTO DE DATOS PERSONALES

En cumplimiento de la Ley 1581 de 2012 y el Decreto 1377 de 2013 (compilado en el Decreto 1074 de 2015), autorizo de manera previa, expresa e informada a {clinica}{nit}, como responsable del tratamiento, para recolectar, almacenar, usar y circular mis datos personales, incluidos los datos sensibles relacionados con mi salud, con las siguientes finalidades: prestar los servicios odontologicos, elaborar y custodiar la historia clinica, agendar y recordar citas y controles, facturar los servicios prestados y cumplir las obligaciones legales del sector salud.

Declaro que se me informo que: (i) no estoy obligado a autorizar el tratamiento de datos sensibles; (ii) como titular tengo derecho a conocer, actualizar, rectificar y suprimir mis datos y a revocar esta autorizacion, salvo cuando exista un deber legal o contractual de conservarlos, como ocurre con la historia clinica; y (iii) puedo ejercer estos derechos ante la clinica por los canales de contacto que esta disponga.

Cuando el titular es menor de edad, esta autorizacion la otorga su representante legal, respetando el interes superior del menor."""


def get_current_policy(db: Session, clinic_id: int) -> PrivacyPolicy:
    """Version vigente de la politica de la clinica. Si no tiene ninguna, se crea la 1.0 con la plantilla."""
    policy = db.scalar(
        select(PrivacyPolicy).where(PrivacyPolicy.clinic_id == clinic_id, PrivacyPolicy.is_current.is_(True))
    )
    if policy:
        return policy
    clinic = db.get(Clinic, clinic_id)
    nit = f" (NIT {clinic.nit}-{clinic.nit_dv})" if clinic.nit else ""
    policy = PrivacyPolicy(clinic_id=clinic_id, version="1.0", text=PLANTILLA.format(clinica=clinic.name, nit=nit),
                           is_current=True)
    db.add(policy)
    db.flush()
    return policy


def latest_consent(db: Session, patient_id: int) -> PatientConsent | None:
    return db.scalar(
        select(PatientConsent).where(PatientConsent.patient_id == patient_id)
        .order_by(PatientConsent.accepted_at.desc(), PatientConsent.id.desc())
    )


def consent_out(c: PatientConsent) -> ConsentOut:
    return ConsentOut(
        id=c.id,
        patient_id=c.patient_id,
        patient_name=c.patient.full_name,
        policy_id=c.policy_id,
        policy_version=c.policy.version,
        method=c.method,
        accepted_at=c.accepted_at,
        signer_name=c.signer_name,
        signer_document=c.signer_document,
        signer_relationship=c.signer_relationship,
        evidence_url=c.evidence_url,
        notes=c.notes,
        is_valid=c.revoked_at is None,
        revoked_at=c.revoked_at,
        revoke_reason=c.revoke_reason,
        created_by=c.created_by,
    )
