from datetime import date, datetime

from pydantic import BaseModel, Field


class ControlCreateIn(BaseModel):
    patient_id: int
    due_date: date
    reason: str = Field(default="Control", min_length=3, max_length=500)


class ControlUpdateIn(BaseModel):
    due_date: date | None = None
    reason: str | None = Field(default=None, min_length=3, max_length=500)
    status: str | None = Field(default=None, pattern=r"^(pendiente|agendado|cancelado)$")
    appointment_id: int | None = None


class ControlOut(BaseModel):
    id: int
    patient_id: int
    patient_name: str
    patient_phone: str
    due_date: date
    days_left: int
    reason: str
    status: str
    appointment_id: int | None
    clinical_entry_id: int | None
    created_at: datetime
    created_by: int | None
