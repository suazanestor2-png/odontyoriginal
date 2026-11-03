from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _calc_is_minor(birth_date: date | None) -> bool:
    if not birth_date:
        return False
    today = date.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return age < 18


class PatientBase(BaseModel):
    document_type: str = Field(default="CC", pattern=r"^(TI|CC|CE|PA)$")
    birth_date: date | None = None
    gender: str | None = Field(default=None, max_length=20)
    blood_type: str | None = Field(default=None, pattern=r"^(O|A|B|AB)[+-]$")
    address: str | None = Field(default=None, max_length=255)
    eps: str | None = Field(default=None, max_length=100)
    guardian_full_name: str | None = Field(default=None, max_length=150)
    guardian_document_number: str | None = None
    guardian_phone: str | None = None
    guardian_relationship: str | None = Field(default=None, max_length=50)
    emergency_contact_name: str | None = Field(default=None, max_length=150)
    emergency_contact_phone: str | None = None
    allergies: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _responsable_si_es_menor(self):
        if _calc_is_minor(self.birth_date):
            if not self.guardian_full_name or not self.guardian_document_number or not self.guardian_phone:
                raise ValueError(
                    "El paciente es menor de edad: guardian_full_name, guardian_document_number y guardian_phone son obligatorios"
                )
        return self


class PatientCreateIn(PatientBase):
    pass


class PatientUpdateIn(BaseModel):
    document_type: str | None = Field(default=None, pattern=r"^(TI|CC|CE|PA)$")
    birth_date: date | None = None
    gender: str | None = Field(default=None, max_length=20)
    blood_type: str | None = Field(default=None, pattern=r"^(O|A|B|AB)[+-]$")
    address: str | None = Field(default=None, max_length=255)
    eps: str | None = Field(default=None, max_length=100)
    guardian_full_name: str | None = Field(default=None, max_length=150)
    guardian_document_number: str | None = None
    guardian_phone: str | None = None
    guardian_relationship: str | None = Field(default=None, max_length=50)
    emergency_contact_name: str | None = Field(default=None, max_length=150)
    emergency_contact_phone: str | None = None
    allergies: str | None = None
    notes: str | None = None
    # Nota: la validacion de "responsable obligatorio si es menor" no aplica aqui porque
    # es una edicion parcial; se revisa en el router contra el estado final del registro.


class PatientRegisterIn(PatientBase):
    # Usado por el personal de la clinica para registrar un paciente nuevo (crea su User + Patient)
    email: str
    document_number: str = Field(pattern=r"^[0-9]{6,10}$")
    full_name: str = Field(min_length=3, max_length=150)
    phone_number: str


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    full_name: str
    email: str
    document_number: str
    document_type: str
    birth_date: date | None
    is_minor: bool
    gender: str | None
    blood_type: str | None
    address: str | None
    eps: str | None
    guardian_full_name: str | None
    guardian_document_number: str | None
    guardian_phone: str | None
    guardian_relationship: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    allergies: str | None
    notes: str | None

class PatientCheckOut(BaseModel):
    user_exists: bool
    user_id: int | None
    full_name: str | None
    email: str | None
    document_number: str | None
    has_patient_profile: bool
    same_clinic: bool