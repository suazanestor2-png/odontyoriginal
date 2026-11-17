from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator


class ClinicalEntryCreateIn(BaseModel):
    appointment_id: int
    antecedentes: str | None = None
    motivo_consulta: str = Field(min_length=3)
    examen: str = Field(min_length=3)
    diagnostico: str = Field(min_length=3)
    tratamiento: str = Field(min_length=3)
    # Opcional: el odontologo deja indicado cuando debe volver el paciente
    next_control_date: date | None = None
    next_control_reason: str | None = Field(default=None, min_length=3, max_length=500)

    @model_validator(mode="after")
    def _motivo_requiere_fecha(self):
        if self.next_control_reason and not self.next_control_date:
            raise ValueError("next_control_reason requiere next_control_date")
        return self


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
    next_control_id: int | None = None
    next_control_date: date | None = None
