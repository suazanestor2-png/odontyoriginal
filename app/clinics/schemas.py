

class ClinicRegisterIn(BaseModel):
    clinic_name: str = Field(min_length=3, max_length=150)
    nit: str
    nit_dv: str = Field(pattern=r"^\d$")
    email: EmailStr
    document_number: str
    full_name: str = Field(min_length=3, max_length=150)
    phone_number: str
    password: str