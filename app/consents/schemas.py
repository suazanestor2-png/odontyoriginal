from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: str
    text: str
    is_current: bool
    created_at: datetime


class PolicyCreateIn(BaseModel):
    version: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=100, max_length=20000)


class ConsentCreateIn(BaseModel):
    patient_id: int
    method: str = Field(pattern=r"^(firma_fisica|firma_digital|verbal)$")
    # Si se omiten se toman del paciente. Si el paciente es menor, son obligatorios (acudiente).
    signer_name: str | None = Field(default=None, min_length=3, max_length=150)
    signer_document: str | None = Field(default=None, min_length=5, max_length=20)
    signer_relationship: str | None = Field(default=None, max_length=50)
    evidence_url: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)


class ConsentRevokeIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class ConsentOut(BaseModel):
    id: int
    patient_id: int
    patient_name: str
    policy_id: int
    policy_version: str
    method: str
    accepted_at: datetime
    signer_name: str
    signer_document: str
    signer_relationship: str | None
    evidence_url: str | None
    notes: str | None
    is_valid: bool
    revoked_at: datetime | None
    revoke_reason: str | None
    created_by: int | None


class ConsentStatusOut(BaseModel):
    patient_id: int
    patient_name: str
    has_valid_consent: bool
    # True si autorizo una version anterior de la politica (conviene pedirle la nueva)
    needs_update: bool
    current_policy_version: str
    consent: ConsentOut | None


class PendingPatientOut(BaseModel):
    patient_id: int
    patient_name: str
    document: str
    phone_number: str
    reason: str  # "sin_autorizacion" | "revocada" | "version_anterior"
