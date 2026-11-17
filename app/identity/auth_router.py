from datetime import timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update                                     # CAMBIO: update
from sqlalchemy.orm import Session

from datetime import datetime, timezone

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_active_user, get_current_user              # CAMBIO: get_active_user
from app.identity.models import RefreshToken, User
from app.identity.schemas import LoginIn, RefreshIn, TokenOut, UserOut
from app.identity.schemas import ChangePasswordIn, SelfUpdateIn          # NUEVO
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.identity.schemas import MFACodeIn, MFALoginRequiredOut, MFASetupOut, MFAVerifyIn
from app.core.security import generate_mfa_secret, get_totp_uri, verify_mfa_code
from app.identity.audit import log_event
from app.email_service import send_email
from app.identity.models import PasswordResetOtp
from app.core.security import generate_otp_code, hash_otp_code
from app.identity.schemas import ForgotPasswordIn, ResetPasswordIn
from app.clinics.models import Clinic
from app.identity.tokens import revoke_all_refresh_tokens #Funcion para reutilizar
from app.core.validators import _telefono
from app.identity.permissions import effective_permissions
from app.identity.cookies import REFRESH_COOKIE, clear_auth_cookies, set_auth_cookies


router = APIRouter(prefix="/auth", tags=["Autenticacion"])

INVALID = HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales invalidas")


def to_user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        document_number=user.document_number,
        full_name=user.full_name,
        role_name=user.role.name,
        is_active=user.is_active,
        phone_number=user.phone_number,                      # NUEVO
        must_change_password=user.must_change_password,      # NUEVO
    )


def issue_tokens(db: Session, user: User, response: Response) -> TokenOut:
    access, _, access_exp = create_token(user.id, "access", timedelta(minutes=settings.ACCESS_TOKEN_MINUTES))
    refresh, jti, exp = create_token(user.id, "refresh", timedelta(days=settings.REFRESH_TOKEN_DAYS))
    db.add(RefreshToken(jti=jti, user_id=user.id, expires_at=exp))
    db.commit()
    set_auth_cookies(response, access, access_exp, refresh, exp)
    en_body = settings.AUTH_TOKENS_IN_BODY
    return TokenOut(
        access_token=access if en_body else None,
        refresh_token=refresh if en_body else None,
        must_change_password=user.must_change_password,      # NUEVO
    )


# El registro publico (/auth/register) se elimino: las cuentas solo son para el personal
# de la clinica y las crea el admin desde /users. Los pacientes no tienen cuenta.


@router.post("/login", response_model=TokenOut | MFALoginRequiredOut)
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))

    if not user:
        log_event(db, "LOGIN_FAILED", detail=f"email={data.email} (no existe)")
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

    # super_admin no pertenece a ninguna clinica, se salta esta validacion
    if user.clinic_id is not None and user.role.name != "super_admin":
        clinic = db.get(Clinic, user.clinic_id)
        if not clinic or clinic.status != "active":
            log_event(db, "LOGIN_CLINIC_NOT_ACTIVE", user.id, f"clinic={user.clinic_id} status={clinic.status if clinic else 'N/A'}")
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Tu clinica aun no ha sido aprobada. Te notificaremos por correo cuando este activa.",
            )

    user.failed_attempts = 0
    db.commit()

    if user.mfa_enabled:
        mfa_token, _, _ = create_token(user.id, "mfa", timedelta(minutes=settings.MFA_TOKEN_MINUTES))
        log_event(db, "LOGIN_MFA_REQUIRED", user.id)
        return MFALoginRequiredOut(mfa_token=mfa_token)

    log_event(db, "LOGIN_SUCCESS", user.id)
    return issue_tokens(db, user, response)


@router.post("/mfa/verify", response_model=TokenOut)
def mfa_verify(data: MFAVerifyIn, response: Response, db: Session = Depends(get_db)):
    payload = decode_token(data.mfa_token, "mfa")
    user = db.get(User, int(payload["sub"]))

    if not user or not user.mfa_enabled or not verify_mfa_code(user.mfa_secret, data.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Codigo invalido o token vencido")
    log_event(db, "LOGIN_MFA_SUCCESS", user.id)

    return issue_tokens(db, user, response)


def _refresh_token(request: Request, data: RefreshIn | None) -> str:
    """El refresh token viene en el body (Postman/apps) o en la cookie httpOnly (navegador)."""
    token = (data.refresh_token if data else None) or request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise INVALID
    return token


@router.post("/refresh", response_model=TokenOut)
def refresh(
    request: Request,
    response: Response,
    data: RefreshIn | None = Body(default=None),
    db: Session = Depends(get_db),
):
    payload = decode_token(_refresh_token(request, data), "refresh")

    stored = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
    if not stored or stored.revoked:
        raise INVALID

    user = db.get(User, stored.user_id)
    if not user or not user.is_active:
        raise INVALID

    stored.revoked = True
    db.commit()

    return issue_tokens(db, user, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    data: RefreshIn | None = Body(default=None),
    db: Session = Depends(get_db),
):
    # Siempre se borran las cookies, aunque el token ya este vencido
    clear_auth_cookies(response)
    token = (data.refresh_token if data else None) or request.cookies.get(REFRESH_COOKIE)
    if not token:
        return
    try:
        payload = decode_token(token, "refresh")
    except HTTPException:
        return
    stored = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
    if stored:
        stored.revoked = True
        db.commit()


# /me se queda con get_current_user a proposito: el frontend puede consultarlo
# aunque deba cambiar la clave, y asi leer must_change_password.
@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    out = to_user_out(user)
    out.permissions = sorted(effective_permissions(db, user))
    return out


@router.patch("/me", response_model=UserOut)
def update_me(
    data: SelfUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_active_user),
):
    """Cada usuario edita sus propios datos (nombre y telefono)."""
    if data.full_name is not None:
        user.full_name = data.full_name.strip()
    if data.phone_number is not None:
        try:
            user.phone_number = _telefono(data.phone_number)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    db.commit()
    db.refresh(user)
    log_event(db, "PROFILE_UPDATED", user.id)
    return to_user_out(user)


@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))

    if user and user.is_active:
        code = generate_otp_code()
        db.add(PasswordResetOtp(
            user_id=user.id,
            code_hash=hash_otp_code(code),
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=settings.OTP_MINUTES),
        ))
        db.commit()

        text_body = (
            f"Hola {user.full_name},\n\n"
            f"Tu codigo de recuperacion es: {code}\n\n"
            f"Este codigo vence en {settings.OTP_MINUTES} minutos.\n"
            "Si no solicitaste esto, ignora este mensaje."
        )
        html_body = f"""\
<html>
  <body style="font-family: Arial, sans-serif; background-color: #f4f4f7; padding: 24px;">
    <div style="max-width: 480px; margin: 0 auto; background: #ffffff; border-radius: 8px; padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
      <h2 style="color: #1a1a2e; margin-top: 0;">Recuperacion de contrasena</h2>
      <p style="color: #333; font-size: 15px;">Hola <strong>{user.full_name}</strong>,</p>
      <p style="color: #333; font-size: 15px;">
        Usa el siguiente codigo para restablecer tu contrasena en Odonty:
      </p>
      <div style="text-align: center; margin: 28px 0;">
        <span style="display: inline-block; font-size: 32px; letter-spacing: 8px; font-weight: bold; color: #4f46e5; background: #eef2ff; padding: 16px 24px; border-radius: 8px;">
          {code}
        </span>
      </div>
      <p style="color: #666; font-size: 13px;">
        Este codigo vence en {settings.OTP_MINUTES} minutos.
      </p>
      <p style="color: #999; font-size: 12px; margin-top: 24px;">
        Si no solicitaste este cambio, puedes ignorar este correo con tranquilidad.
      </p>
    </div>
  </body>
</html>
"""
        send_email(
            to=user.email,
            subject="Codigo de recuperacion - Odonty",
            body=text_body,
            html_body=html_body,
        )
        log_event(db, "PASSWORD_RESET_REQUESTED", user.id)

    return {"detail": "Si el correo existe, recibiras un codigo de recuperacion"}


@router.post("/reset-password")
def reset_password(data: ResetPasswordIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Codigo invalido o expirado")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    otp = db.scalar(
        select(PasswordResetOtp)
        .where(PasswordResetOtp.user_id == user.id, PasswordResetOtp.used == False)
        .order_by(PasswordResetOtp.id.desc())
    )

    if not otp or otp.expires_at < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Codigo invalido o expirado")

    if otp.attempts >= settings.MAX_OTP_ATTEMPTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Demasiados intentos, solicita un codigo nuevo")

    if otp.code_hash != hash_otp_code(data.code):
        otp.attempts += 1
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Codigo invalido o expirado")

    if verify_password(data.new_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La nueva contrasena debe ser distinta a la anterior")

    user.hashed_password = hash_password(data.new_password)
    user.must_change_password = False
    otp.used = True
    revoke_all_refresh_tokens(db, user.id)
    db.commit()
    log_event(db, "PASSWORD_RESET_DONE", user.id)

    return {"detail": "Contrasena actualizada correctamente"}


# CAMBIO: los endpoints de MFA ahora usan get_active_user (primero debe cambiar la clave)
@router.post("/mfa/setup", response_model=MFASetupOut)
def mfa_setup(user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    if user.mfa_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El MFA ya esta activado")

    secret = generate_mfa_secret()
    user.mfa_secret = secret
    db.commit()

    return MFASetupOut(secret=secret, otpauth_uri=get_totp_uri(secret, user.email))


@router.post("/mfa/enable")
def mfa_enable(data: MFACodeIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    if not user.mfa_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Primero debes llamar a /mfa/setup")
    if not verify_mfa_code(user.mfa_secret, data.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Codigo incorrecto")

    user.mfa_enabled = True
    db.commit()
    return {"detail": "MFA activado correctamente"}


@router.post("/mfa/disable")
def mfa_disable(data: MFACodeIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    if not user.mfa_enabled or not verify_mfa_code(user.mfa_secret, data.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Codigo incorrecto")

    user.mfa_enabled = False
    user.mfa_secret = None
    db.commit()
    return {"detail": "MFA desactivado"}


# NUEVO/CAMBIO: usa get_current_user (unico endpoint permitido con el flag activo)
@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    data: ChangePasswordIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La contrasena actual no es correcta")
    if verify_password(data.new_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La nueva contrasena debe ser distinta a la actual")

    user.hashed_password = hash_password(data.new_password)
    user.must_change_password = False
    revoke_all_refresh_tokens(db, user.id)
    db.commit()
    log_event(db, "PASSWORD_CHANGED", user.id)