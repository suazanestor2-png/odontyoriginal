from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AppointmentCreateIn(BaseModel):
    patient_id: int
    dentist_id: int
    scheduled_date: date
    start_time: time
    end_time: time
    reason: str = Field(min_length=3)
    origin: str = Field(default="presencial", pattern=r"^(presencial|llamada|whatsapp)$")

    @model_validator(mode="after")
    def _horas_validas(self):
        if self.end_time <= self.start_time:
            raise ValueError("La hora de fin debe ser posterior a la hora de inicio")
        return self


class AppointmentRescheduleIn(BaseModel):
    scheduled_date: date
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def _horas_validas(self):
        if self.end_time <= self.start_time:
            raise ValueError("La hora de fin debe ser posterior a la hora de inicio")
        return self


class AppointmentCancelIn(BaseModel):
    cancellation_reason: str = Field(min_length=3)


class AppointmentStatusIn(BaseModel):
    status: str = Field(pattern=r"^(confirmada|atendida|no_asistio)$")


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    patient_name: str
    dentist_id: int
    dentist_name: str
    scheduled_date: date
    start_time: time
    end_time: time
    reason: str
    origin: str
    status: str
    cancellation_reason: str | None