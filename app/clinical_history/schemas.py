from datetime import datetime

from pydantic import BaseModel, Field


class ClinicalEntryCreateIn(BaseModel):
    appointment_id: int
    antecedentes: str | None = None
    motivo_consulta: str = Field(min_length=3)
    examen: str = Field(min_length=3)
    diagnostico: str = Field(min_length=3)
    tratamiento: str = Field(min_length=3)


class ClinicalEntryOut(BaseModel):
    id: int
    patient_id: int
    patient_name: str
    appointment_id: int
    dentist_id: int
    dentist_name: str
    antecedentes: str | None
    motivo_consulta: str
    examen: str
    diagnostico: str
    tratamiento: str
    created_at: datetime
    created_by: int | None
    created_by_name: str | None