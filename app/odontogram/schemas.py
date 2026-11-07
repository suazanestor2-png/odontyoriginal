from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.odontogram.models import VALID_FDI_CODES, ToothSurface


class OdontogramEntryCreateIn(BaseModel):
    appointment_id: int
    tooth_fdi: int
    surface: ToothSurface | None = None
    condition_code: str | None = None
    procedure_code: str | None = None
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validar_datos(self):
        if self.tooth_fdi not in VALID_FDI_CODES:
            raise ValueError(f"tooth_fdi invalido: {self.tooth_fdi} no es un codigo FDI valido")
        if not self.condition_code and not self.procedure_code:
            raise ValueError("Debes indicar al menos un condition_code o un procedure_code")
        return self


class OdontogramEntryOut(BaseModel):
    id: int
    patient_id: int
    patient_name: str
    appointment_id: int
    dentist_id: int
    dentist_name: str
    tooth_fdi: int
    surface: ToothSurface | None
    condition_code: str | None
    condition_name: str | None
    procedure_code: str | None
    procedure_name: str | None
    notes: str | None
    created_at: datetime
    created_by: int | None
    created_by_name: str | None