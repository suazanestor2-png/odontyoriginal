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


class ClinicReviewIn(BaseModel):
    approve: bool