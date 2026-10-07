import base64
import hashlib
import uuid
import secrets

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
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


def verify_mfa_code(secret: str, code: str) -> bool:
    return pyotp.totp.TOTP(secret).verify(code, valid_window=1)

def generate_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()
