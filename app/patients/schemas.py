from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

DOCUMENT_TYPE_PATTERN = r"^(TI|CC|CE|PA)$"
GENDER_PATTERN = r"^(Masculino|Femenino)$"
BLOOD_TYPE_PATTERN = r"^(O|A|B|AB)[+-]$"


def _calc_is_minor(birth_date: date | None) -> bool:
    if not birth_date:
        return False
    today = date.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return age < 18


def falta_responsable(birth_date, guardian_full_name, guardian_document_number, guardian_phone) -> bool:
    return _calc_is_minor(birth_date) and not (guardian_full_name and guardian_document_number and guardian_phone)


MENSAJE_RESPONSABLE = (
    "El paciente es menor de edad: guardian_full_name, guardian_document_number y guardian_phone son obligatorios"
)


class PatientCreateIn(BaseModel):
    # Obligatorios (registro rapido)
    full_name: str = Field(min_length=3, max_length=150)
    document_type: str = Field(default="CC", pattern=DOCUMENT_TYPE_PATTERN)
    document_number: str = Field(pattern=r"^[0-9]{6,10}$")
    email: str = Field(max_length=255)
    phone_number: str
    birth_date: date
    gender: str = Field(pattern=GENDER_PATTERN)

    # Opcionales
    blood_type: str | None = Field(default=None, pattern=BLOOD_TYPE_PATTERN)
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
        if falta_responsable(self.birth_date, self.guardian_full_name, self.guardian_document_number, self.guardian_phone):
            raise ValueError(MENSAJE_RESPONSABLE)
        return self


class PatientUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=3, max_length=150)
    document_type: str | None = Field(default=None, pattern=DOCUMENT_TYPE_PATTERN)
    document_number: str | None = Field(default=None, pattern=r"^[0-9]{6,10}$")
    email: str | None = Field(default=None, max_length=255)
    phone_number: str | None = None
    birth_date: date | None = None
    gender: str | None = Field(default=None, pattern=GENDER_PATTERN)
    blood_type: str | None = Field(default=None, pattern=BLOOD_TYPE_PATTERN)
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
    # La regla de "responsable obligatorio si es menor" se revisa en el router
    # contra el estado final del registro, porque esta es una edicion parcial.


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clinic_id: int
    full_name: str
    document_type: str
    document_number: str
    email: str
    phone_number: str
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
    # Solo informa sobre la clinica de quien consulta; nunca revela otras clinicas
    exists: bool
    patient_id: int | None
    full_name: str | None