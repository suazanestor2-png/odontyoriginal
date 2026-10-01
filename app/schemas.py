import re

from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic import ConfigDict
from datetime import datetime



class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    document_number: str
    full_name: str
    role_name: str
    is_active: bool


def validate_password_strength(v: str) -> str:
    if len(v) < 8:
        raise ValueError("La contrasena debe tener al menos 8 caracteres")
    if len(v) > 128:
        raise ValueError("La contrasena es demasiado larga")
    checks = [
        (r"[a-z]", "una minuscula"),
        (r"[A-Z]", "una mayuscula"),
        (r"\d", "un numero"),
        (r"[^\w\s]", "un simbolo"),
    ]
    missing = [name for pattern, name in checks if not re.search(pattern, v)]
    if missing:
        raise ValueError("Falta: " + ", ".join(missing))
    return v


class RegisterIn(BaseModel):
    email: EmailStr
    document_number: str = Field(pattern=r"^[0-9A-Za-z]{5,20}$")
    full_name: str = Field(min_length=3, max_length=150)
    phone_number: str = Field(pattern=r"^\+[1-9]\d{7,14}$")
    password: str

    _pw = field_validator("password")(validate_password_strength)

class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RoleChangeIn(BaseModel):
    role: str = Field(pattern=r"^(admin|odontologo|recepcionista|usuario)$")

class RefreshIn(BaseModel):
    refresh_token: str

class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")
    new_password: str

    _pw = field_validator("new_password")(validate_password_strength)


class MFASetupOut(BaseModel):
    secret: str
    otpauth_uri: str


class MFACodeIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class MFALoginRequiredOut(BaseModel):
    mfa_required: bool = True
    mfa_token: str


class MFAVerifyIn(BaseModel):
    mfa_token: str
    code: str = Field(pattern=r"^\d{6}$")

class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    action: str
    detail: str | None
    created_at: datetime
