from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from datetime import datetime, timezone

from app.models import PasswordResetToken
from app.schemas import ForgotPasswordIn, ResetPasswordIn
from app.security import generate_reset_token, hash_reset_token

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import RefreshToken, Role, User
from app.schemas import LoginIn, RefreshIn, RegisterIn, TokenOut, UserOut
from app.security import create_token, decode_token, hash_password, verify_password
from app.schemas import MFACodeIn, MFALoginRequiredOut, MFASetupOut, MFAVerifyIn
from app.security import generate_mfa_secret, get_totp_uri, verify_mfa_code
from app.audit import log_event

router = APIRouter(prefix="/auth", tags=["Autenticacion"])

INVALID = HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales invalidas")


def find_user(db: Session, identifier: str) -> User | None:
    identifier = identifier.strip()
    if "@" in identifier:
        return db.scalar(select(User).where(User.email == identifier.lower()))
    return db.scalar(select(User).where(User.document_number == identifier))


def to_user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        document_number=user.document_number,
        full_name=user.full_name,
        role_name=user.role.name,
        is_active=user.is_active,
    )


def issue_tokens(db: Session, user: User) -> TokenOut:
    access, _, _ = create_token(user.id, "access", timedelta(minutes=settings.ACCESS_TOKEN_MINUTES))
    refresh, jti, exp = create_token(user.id, "refresh", timedelta(days=settings.REFRESH_TOKEN_DAYS))
    db.add(RefreshToken(jti=jti, user_id=user.id, expires_at=exp))
    db.commit()
    return TokenOut(access_token=access, refresh_token=refresh)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    email = data.email.lower()

    exists = db.scalar(
        select(User).where((User.email == email) | (User.document_number == data.document_number))
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "El correo o el documento ya estan registrados")

    usuario_role = db.scalar(select(Role).where(Role.name == "usuario"))
    if not usuario_role:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "El rol 'usuario' no existe, revisa el seed")

    user = User(
        email=email,
        document_number=data.document_number,
        full_name=data.full_name.strip(),
        hashed_password=hash_password(data.password),
        role_id=usuario_role.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return to_user_out(user)


@router.post("/login", response_model=TokenOut | MFALoginRequiredOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = find_user(db, data.identifier)

    if not user:
        log_event(db, "LOGIN_FAILED", detail=f"identifier={data.identifier} (no existe)")
        raise INVALID

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if user.locked_until and user.locked_until > now:
        log_event(db, "LOGIN_BLOCKED", user.id)
        raise HTTPException(status.HTTP_423_LOCKED, "Cuenta bloqueada temporalmente, intenta mas tarde")

    if not verify_password(data.password, user.hashed_password):
        user.failed_attempts += 1
        if user.failed_attempts >= settings.MAX_FAILED_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=settings.LOCK_MINUTES)
            user.failed_attempts = 0
            log_event(db, "ACCOUNT_LOCKED", user.id)
        db.commit()
        log_event(db, "LOGIN_FAILED", user.id, "clave incorrecta")
        raise INVALID

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cuenta desactivada")

    # Login correcto: reiniciamos el contador de fallos
    user.failed_attempts = 0
    db.commit()

    if user.mfa_enabled:
        mfa_token, _, _ = create_token(user.id, "mfa", timedelta(minutes=settings.MFA_TOKEN_MINUTES))
        log_event(db, "LOGIN_MFA_REQUIRED", user.id)
        return MFALoginRequiredOut(mfa_token=mfa_token)

    log_event(db, "LOGIN_SUCCESS", user.id)
    return issue_tokens(db, user)


@router.post("/mfa/verify", response_model=TokenOut)
def mfa_verify(data: MFAVerifyIn, db: Session = Depends(get_db)):
    payload = decode_token(data.mfa_token, "mfa")
    user = db.get(User, int(payload["sub"]))

    if not user or not user.mfa_enabled or not verify_mfa_code(user.mfa_secret, data.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Codigo invalido o token vencido")
    log_event(db, "LOGIN_MFA_SUCCESS", user.id)

    return issue_tokens(db, user)


@router.post("/refresh", response_model=TokenOut)
def refresh(data: RefreshIn, db: Session = Depends(get_db)):
    payload = decode_token(data.refresh_token, "refresh")

    stored = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
    if not stored or stored.revoked:
        raise INVALID

    user = db.get(User, stored.user_id)
    if not user or not user.is_active:
        raise INVALID

    # Rotacion: el refresh usado se invalida, y se entrega uno nuevo.
    # Si alguien intenta reusar este mismo refresh despues, fallara (stored.revoked ya sera True).
    stored.revoked = True
    db.commit()

    return issue_tokens(db, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(data: RefreshIn, db: Session = Depends(get_db)):
    payload = decode_token(data.refresh_token, "refresh")
    stored = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
    if stored:
        stored.revoked = True
        db.commit()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return to_user_out(user)

@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))

    if user and user.is_active:
        raw_token = generate_reset_token()
        db.add(PasswordResetToken(
            user_id=user.id,
            token_hash=hash_reset_token(raw_token),
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=settings.RESET_TOKEN_MINUTES),
        ))
        db.commit()

        # En produccion esto se envia por correo. Por ahora, lo imprimimos
        # en la consola de uvicorn para poder probarlo sin configurar SMTP.
        print(f"\n[DEV] Enlace de recuperacion para {user.email}:")
        print(f"[DEV] token = {raw_token}\n")

    # Misma respuesta exista o no el correo, para no revelar informacion.
    return {"detail": "Si el correo existe, recibiras instrucciones para recuperar tu contrasena"}


@router.post("/reset-password")
def reset_password(data: ResetPasswordIn, db: Session = Depends(get_db)):
    token_hash = hash_reset_token(data.token)
    record = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not record or record.used or record.expires_at < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token invalido o expirado")

    user = db.get(User, record.user_id)
    user.hashed_password = hash_password(data.new_password)
    record.used = True
    db.commit()

    return {"detail": "Contrasena actualizada correctamente"}


@router.post("/mfa/setup", response_model=MFASetupOut)
def mfa_setup(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.mfa_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El MFA ya esta activado")

    secret = generate_mfa_secret()
    user.mfa_secret = secret
    db.commit()

    return MFASetupOut(secret=secret, otpauth_uri=get_totp_uri(secret, user.email))


@router.post("/mfa/enable")
def mfa_enable(data: MFACodeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.mfa_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Primero debes llamar a /mfa/setup")
    if not verify_mfa_code(user.mfa_secret, data.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Codigo incorrecto")

    user.mfa_enabled = True
    db.commit()
    return {"detail": "MFA activado correctamente"}


@router.post("/mfa/disable")
def mfa_disable(data: MFACodeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.mfa_enabled or not verify_mfa_code(user.mfa_secret, data.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Codigo incorrecto")

    user.mfa_enabled = False
    user.mfa_secret = None
    db.commit()
    return {"detail": "MFA desactivado"}