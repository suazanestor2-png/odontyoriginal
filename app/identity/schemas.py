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
    phone_number: str | None = None            # NUEVO
    must_change_password: bool = False         # NUEVO
    # Permisos efectivos (solo los llena /auth/me, para que el frontend muestre u oculte opciones)
    permissions: list[str] = []


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


def validate_document(v: str) -> str:
    if not re.fullmatch(r"[0-9]+", v):
        raise ValueError("El documento solo debe contener numeros")
    if not (5 <= len(v) <= 10):
        raise ValueError("El documento debe tener entre 5 y 10 digitos")
    return v


def validate_phone(v: str) -> str:
    if v.startswith("+57"):
        v = v[3:]
    if not re.fullmatch(r"[0-9]{10}", v):
        raise ValueError("El telefono debe tener 10 digitos numericos")
    return "+57" + v


class RegisterIn(BaseModel):
    email: EmailStr
    document_number: str
    full_name: str = Field(min_length=3, max_length=150)
    phone_number: str
    password: str

    _doc = field_validator("document_number")(validate_document)
    _phone = field_validator("phone_number")(validate_phone)
    _pw = field_validator("password")(validate_password_strength)


class UserCreateIn(BaseModel):                 # NUEVO
    email: EmailStr
    document_number: str
    full_name: str = Field(min_length=3, max_length=150)
    phone_number: str
    role: str = Field(pattern=r"^(admin|odontologo|recepcionista)$")

    _doc = field_validator("document_number")(validate_document)
    _phone = field_validator("phone_number")(validate_phone)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class TokenOut(BaseModel):
    # Vacios cuando AUTH_TOKENS_IN_BODY=false: en ese caso la sesion va solo en cookies httpOnly
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    must_change_password: bool = False         # NUEVO


class ChangePasswordIn(BaseModel):             # NUEVO
    current_password: str = Field(max_length=128)
    new_password: str

    _pw = field_validator("new_password")(validate_password_strength)


class RoleChangeIn(BaseModel):
    role: str = Field(pattern=r"^(admin|odontologo|recepcionista)$")


class RefreshIn(BaseModel):
    # Opcional: si no se envia, se usa la cookie odonty_refresh
    refresh_token: str | None = None


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


class ActiveChangeIn(BaseModel):
    is_active: bool

class SelfUpdateIn(BaseModel):
    """Lo que cada usuario puede cambiar de su propio perfil (el correo no: es su usuario de acceso)."""
    full_name: str | None = Field(default=None, min_length=3, max_length=150)
    phone_number: str | None = None


class UserUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=3, max_length=150)
    phone_number: str | None = None
    email: EmailStr | None = None


class PermissionCatalogOut(BaseModel):
    code: str
    description: str | None
    delegable: bool  # si un admin se lo puede dar o quitar a su personal


class UserPermissionsOut(BaseModel):
    user_id: int
    full_name: str
    role_name: str
    role_permissions: list[str]   # los que trae por su rol
    granted: list[str]            # otorgados ademas del rol
    revoked: list[str]            # quitados del rol
    effective: list[str]          # los que realmente tiene
    editable: list[str]           # los que quien consulta puede dar o quitar


class UserPermissionsUpdateIn(BaseModel):
    """Reemplaza las excepciones del usuario. Enviar listas vacias lo deja igual a su rol."""
    granted: list[str] = Field(default_factory=list, max_length=50)
    revoked: list[str] = Field(default_factory=list, max_length=50)
