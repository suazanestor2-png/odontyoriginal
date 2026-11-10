from datetime import datetime

from pydantic import BaseModel, Field


class NotificationCreateIn(BaseModel):
    user_id: int
    type: str = Field(min_length=2, max_length=40)
    title: str = Field(min_length=3, max_length=150)
    message: str = Field(min_length=3)
    appointment_id: int | None = None
    patient_id: int | None = None


class NotificationOut(BaseModel):
    id: int
    user_id: int
    type: str
    title: str
    message: str
    appointment_id: int | None
    patient_id: int | None
    is_read: bool
    read_at: datetime | None
    created_at: datetime