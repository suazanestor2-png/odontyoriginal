from datetime import time

from pydantic import BaseModel, EmailStr, Field

from app.core.validators import Documento, PasswordSegura, Telefono

from pydantic import BaseModel, ConfigDict

class ClinicRegisterIn(BaseModel):
    clinic_name: str = Field(min_length=3, max_length=150)
    nit: str
    nit_dv: str = Field(pattern=r"^\d$")
    email: EmailStr
    document_number: Documento
    full_name: str = Field(min_length=3, max_length=150)
    phone_number: Telefono
    password: PasswordSegura

class ClinicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    nit: str | None
    status: str
    cedula_url: str | None
    rut_url: str | None
    camara_comercio_url: str | None


class ClinicReviewIn(BaseModel):
    approve: bool

class ClinicListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    nit: str | None
    status: str
    city: str | None
    phone: str | None
    email: str | None


class ClinicProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    nit: str | None
    nit_dv: str | None
    status: str
    phone: str | None
    email: str | None
    address: str | None
    city: str | None
    reps_code: str | None = None
    reps_site_number: str | None = None
    logo_url: str | None
    opening_time: time
    closing_time: time
    working_days: str
    default_appointment_minutes: int
    appointment_reminder_first_hours: int
    appointment_reminder_second_hours: int
    control_reminder_first_days: int
    control_reminder_second_days: int


class ClinicProfileUpdateIn(BaseModel):
    """El nombre y el NIT no se editan aqui: se revisaron al aprobar la clinica."""
    phone: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None
    address: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    reps_code: str | None = Field(default=None, pattern=r"^[0-9]{10,12}$", description="Codigo de habilitacion REPS")
    reps_site_number: str | None = Field(default=None, pattern=r"^[0-9]{2}$", description="Numero de sede en REPS, ej. 01")
    opening_time: time | None = None
    closing_time: time | None = None
    working_days: str | None = Field(default=None, pattern=r"^[1-7](,[1-7]){0,6}$")
    default_appointment_minutes: int | None = Field(default=None, ge=10, le=240)
    # Recordatorios: 0 desactiva. El primero debe ser con mas anticipacion que el segundo.
    appointment_reminder_first_hours: int | None = Field(default=None, ge=0, le=168)
    appointment_reminder_second_hours: int | None = Field(default=None, ge=0, le=72)
    control_reminder_first_days: int | None = Field(default=None, ge=0, le=60)
    control_reminder_second_days: int | None = Field(default=None, ge=0, le=30)
