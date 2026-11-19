import base64
import hashlib
import uuid
import secrets
import string

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status

from app.core.config import settings

import pyotp


def _prehash(password: str) -> bytes:
    # bcrypt solo lee los primeros 72 bytes de la clave; si alguien pone una
    # clave larguísima, se trunca en silencio. El prehash con SHA-256 evita
    # ese problema sin debilitar la seguridad.
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), hashed.encode())
    except ValueError:
        return False


def create_token(sub: int, token_type: str, expires: timedelta, jti: str | None = None) -> tuple[str, str, datetime]:
    now = datetime.now(timezone.utc)
    jti = jti or uuid.uuid4().hex
    exp = now + expires
    payload = {
        "sub": str(sub),
        "type": token_type,
        "jti": jti,
        "iat": now,
        "exp": exp,
        "iss": "Odonty",
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, jti, exp.replace(tzinfo=None)


def decode_token(token: str, expected_type: str) -> dict:
    error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "sub", "jti", "type"]},
        )
    except jwt.PyJWTError:
        raise error
    if payload.get("type") != expected_type:
        raise error
    return payload



def generate_mfa_secret() -> str:
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name="Odonty")


def verify_mfa_code(secret: str | None, code: str) -> bool:
    if not secret:
        return False
    return pyotp.totp.TOTP(secret).verify(code, valid_window=1)


# --- Cifrado del secreto MFA ---------------------------------------------
# El secreto TOTP no se puede guardar con hash: para verificar un codigo el
# servidor necesita el secreto original. Por eso se guarda con cifrado
# simetrico (Fernet: AES-128 + HMAC) y se descifra solo al verificar.
def _mfa_fernet() -> Fernet:
    key = settings.MFA_ENCRYPTION_KEY
    if not key:
        # Respaldo para no romper un despliegue sin la variable: se deriva del
        # SECRET_KEY. En produccion se debe configurar MFA_ENCRYPTION_KEY.
        key = base64.urlsafe_b64encode(hashlib.sha256(("mfa:" + settings.SECRET_KEY).encode()).digest()).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_mfa_secret(secret: str) -> str:
    return _mfa_fernet().encrypt(secret.encode()).decode()


def decrypt_mfa_secret(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _mfa_fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None

def generate_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()

def generate_temp_password(length: int = 12) -> str:
    symbols = "!@#$%&*?"
    alphabet = string.ascii_letters + string.digits + symbols
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pwd) and any(c.isupper() for c in pwd)
                and any(c.isdigit() for c in pwd) and any(c in symbols for c in pwd)):
            return pwd