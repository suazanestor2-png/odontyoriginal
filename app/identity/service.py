"""Logica de negocio de identidad: autenticacion, MFA, usuarios del personal y permisos.

Los routers (auth_router, users_router, permissions_router) solo reciben la peticion,
validan el permiso y llaman a estas funciones.
"""
from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks, HTTPException, Request, Response, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.clinics.models import Clinic
from app.core.config import settings
from app.core.security import (
    create_token, decode_token, decrypt_mfa_secret, encrypt_mfa_secret, generate_mfa_secret,
    generate_otp_code, generate_temp_password, get_totp_uri, hash_otp_code, hash_password,
    verify_mfa_code, verify_password,
)
from app.core.validators import _telefono
from app.email_service import send_email, send_welcome_email
from app.identity.audit import log_event
from app.identity.cookies import REFRESH_COOKIE, clear_auth_cookies, set_auth_cookies
from app.identity.models import (
    AuditLog, PasswordResetOtp, Permission, RefreshToken, Role, User, UserPermissionOverride,
)
from app.identity.permissions import (
    DELEGABLE, ROLES_PERSONALIZABLES, effective_permissions, overrides, role_permissions,
)
from app.identity.schemas import (
    ActiveChangeIn, ChangePasswordIn, ForgotPasswordIn, LoginIn, MFACodeIn, MFALoginRequiredOut,
    MFASetupOut, MFAVerifyIn, PermissionCatalogOut, RefreshIn, ResetPasswordIn, RoleChangeIn,
    SelfUpdateIn, TokenOut, UserCreateIn, UserOut, UserPermissionsOut, UserPermissionsUpdateIn,
    UserUpdateIn,
)
from app.identity.tokens import revoke_all_refresh_tokens

INVALID = HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales invalidas")

# Roles que un admin (no super_admin) tiene permitido tocar y asignar
ADMIN_ALLOWED_ROLES = {"odontologo", "recepcionista"}


# ======================================================================
# Comunes
# ======================================================================

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


# ======================================================================
# Autenticacion
# ======================================================================

def iniciar_sesion(db: Session, response: Response, data: LoginIn) -> TokenOut | MFALoginRequiredOut:
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


def verificar_mfa_login(db: Session, response: Response, data: MFAVerifyIn) -> TokenOut:
    payload = decode_token(data.mfa_token, "mfa")
    user = db.get(User, int(payload["sub"]))

    if not user or not user.mfa_enabled or not verify_mfa_code(decrypt_mfa_secret(user.mfa_secret), data.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Codigo invalido o token vencido")
    log_event(db, "LOGIN_MFA_SUCCESS", user.id)

    return issue_tokens(db, user, response)


def leer_refresh_token(request: Request, data: RefreshIn | None) -> str:
    """El refresh token viene en el body (Postman/apps) o en la cookie httpOnly (navegador)."""
    token = (data.refresh_token if data else None) or request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise INVALID
    return token


def renovar_sesion(db: Session, request: Request, response: Response, data: RefreshIn | None) -> TokenOut:
    payload = decode_token(leer_refresh_token(request, data), "refresh")

    stored = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
    if not stored or stored.revoked:
        raise INVALID

    user = db.get(User, stored.user_id)
    if not user or not user.is_active:
        raise INVALID

    stored.revoked = True
    db.commit()

    return issue_tokens(db, user, response)


def cerrar_sesion(db: Session, request: Request, response: Response, data: RefreshIn | None) -> None:
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


def mi_perfil(db: Session, user: User) -> UserOut:
    out = to_user_out(user)
    out.permissions = sorted(effective_permissions(db, user))
    return out


def actualizar_mi_perfil(db: Session, user: User, data: SelfUpdateIn) -> UserOut:
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


def solicitar_recuperacion(db: Session, data: ForgotPasswordIn) -> dict:
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


def restablecer_contrasena(db: Session, data: ResetPasswordIn) -> dict:
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


def cambiar_contrasena(db: Session, user: User, data: ChangePasswordIn) -> None:
    if not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La contrasena actual no es correcta")
    if verify_password(data.new_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La nueva contrasena debe ser distinta a la actual")

    user.hashed_password = hash_password(data.new_password)
    user.must_change_password = False
    revoke_all_refresh_tokens(db, user.id)
    db.commit()
    log_event(db, "PASSWORD_CHANGED", user.id)


# ---------- MFA ----------

def configurar_mfa(db: Session, user: User) -> MFASetupOut:
    if user.mfa_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El MFA ya esta activado")

    secret = generate_mfa_secret()
    user.mfa_secret = encrypt_mfa_secret(secret)
    db.commit()

    return MFASetupOut(secret=secret, otpauth_uri=get_totp_uri(secret, user.email))


def activar_mfa(db: Session, user: User, data: MFACodeIn) -> dict:
    if not user.mfa_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Primero debes llamar a /mfa/setup")
    if not verify_mfa_code(decrypt_mfa_secret(user.mfa_secret), data.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Codigo incorrecto")

    user.mfa_enabled = True
    db.commit()
    return {"detail": "MFA activado correctamente"}


def desactivar_mfa(db: Session, user: User, data: MFACodeIn) -> dict:
    if not user.mfa_enabled or not verify_mfa_code(decrypt_mfa_secret(user.mfa_secret), data.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Codigo incorrecto")

    user.mfa_enabled = False
    user.mfa_secret = None
    db.commit()
    return {"detail": "MFA desactivado"}


# ======================================================================
# Usuarios del personal
# ======================================================================

def get_target_user(db: Session, user_id: int) -> User:
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    return target


def crear_usuario(db: Session, background: BackgroundTasks, actor: User, data: UserCreateIn) -> UserOut:
    # Un admin normal solo puede crear estos 3 roles (igual que en change_role)
    if actor.role.name != "super_admin" and data.role not in ADMIN_ALLOWED_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Un admin solo puede crear odontologo o recepcionista",
        )

    email = data.email.lower()   # CAMBIO: el login busca en minusculas, asi que se guarda en minusculas

    exists = db.scalar(
        select(User).where(
            or_(User.email == email, User.document_number == data.document_number)   # CAMBIO: usa email
        )
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese correo o documento")

    role = db.scalar(select(Role).where(Role.name == data.role))
    if not role:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rol invalido")

    temp_password = generate_temp_password()

    user = User(
        email=email,
        document_number=data.document_number,
        full_name=data.full_name,
        phone_number=data.phone_number,
        role_id=role.id,
        hashed_password=hash_password(temp_password),
        is_active=True,
        must_change_password=True,
        clinic_id=actor.clinic_id,
    )

    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese correo o documento")
    db.refresh(user)

    background.add_task(send_welcome_email, user.email, user.full_name, temp_password)
    log_event(db, "USER_CREATED", actor.id, f"target={user.id} rol={data.role}")
    return to_user_out(user)


def cambiar_rol(db: Session, actor: User, user_id: int, data: RoleChangeIn) -> UserOut:
    target = get_target_user(db, user_id)

    if actor.id == target.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No puedes modificar tu propio rol")

    if target.role.name == "super_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El super admin no se puede modificar")

    if actor.role.name != "super_admin":
        if target.clinic_id != actor.clinic_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
        # Un admin normal solo puede tocar y asignar estos 3 roles
        if target.role.name not in ADMIN_ALLOWED_ROLES:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Un admin no puede modificar a otro admin")
        if data.role not in ADMIN_ALLOWED_ROLES:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Un admin solo puede asignar odontologo o recepcionista")

    if data.role == "super_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No se puede asignar el rol super admin")

    new_role = db.scalar(select(Role).where(Role.name == data.role))
    if not new_role:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rol invalido")

    if target.role_id != new_role.id:
        # Los permisos personalizados eran para el rol anterior: se descartan
        db.execute(delete(UserPermissionOverride).where(UserPermissionOverride.user_id == target.id))
    target.role_id = new_role.id
    db.commit()
    db.refresh(target)
    log_event(db, "ROLE_CHANGED", actor.id, f"target={target.id} nuevo_rol={data.role}")
    return to_user_out(target)


def cambiar_activo(db: Session, actor: User, user_id: int, data: ActiveChangeIn) -> UserOut:
    target = get_target_user(db, user_id)

    if actor.id == target.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No puedes activar o desactivar tu propia cuenta")

    if target.role.name == "super_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El super admin no se puede modificar")

    if actor.role.name != "super_admin" and target.clinic_id != actor.clinic_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")

    target.is_active = data.is_active
    db.commit()
    db.refresh(target)

    if not data.is_active:
        # Si lo desactivan, se le cierran todas las sesiones activas de inmediato.
        revoke_all_refresh_tokens(db, target.id)
        db.commit()

    log_event(db, "USER_ACTIVE_CHANGED", actor.id, f"target={target.id} is_active={data.is_active}")
    return to_user_out(target)


def bitacora(db: Session, limit: int) -> list[AuditLog]:
    logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
    return logs


def listar_usuarios(db: Session, actor: User, search: str | None, role: str | None, is_active: bool | None,
                    limit: int, offset: int) -> tuple[list[UserOut], int]:
    query = select(User)
    if actor.role.name != "super_admin":
        query = query.where(User.clinic_id == actor.clinic_id)
    if search:
        like = f"%{search.strip()}%"
        query = query.where(or_(User.full_name.ilike(like), User.email.ilike(like)))
    if role:
        query = query.join(Role, User.role_id == Role.id).where(Role.name == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)

    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    items = db.scalars(query.order_by(User.id).limit(limit).offset(offset)).all()

    return [to_user_out(u) for u in items], total


def actualizar_usuario(db: Session, actor: User, user_id: int, data: UserUpdateIn) -> UserOut:
    target = get_target_user(db, user_id)

    if actor.id == target.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Para editar tu propio perfil usa /auth/me")

    if target.role.name == "super_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El super admin no se puede modificar")

    if actor.role.name != "super_admin":
        if target.clinic_id != actor.clinic_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
        if target.role.name not in ADMIN_ALLOWED_ROLES:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Un admin no puede modificar a otro admin")

    if data.email is not None:
        new_email = data.email.strip().lower()
        duplicado = db.scalar(select(User).where(User.email == new_email, User.id != target.id))
        if duplicado:
            raise HTTPException(status.HTTP_409_CONFLICT, "Ese correo ya esta en uso")
        target.email = new_email

    if data.phone_number is not None:
        try:
            target.phone_number = _telefono(data.phone_number)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    if data.full_name is not None:
        target.full_name = data.full_name.strip()

    db.commit()
    db.refresh(target)
    log_event(db, "USER_UPDATED", actor.id, f"target={target.id}")
    return to_user_out(target)


# ======================================================================
# Permisos por usuario
# ======================================================================

def permisos_editables(db: Session, actor: User) -> set[str]:
    """Un admin solo puede delegar permisos delegables que el mismo tenga."""
    if actor.role.name == "super_admin":
        return set(DELEGABLE)
    return DELEGABLE & effective_permissions(db, actor)


def usuario_de_mi_clinica(db: Session, user_id: int, actor: User) -> User:
    target = db.get(User, user_id)
    if not target or (actor.role.name != "super_admin" and target.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    return target


def permisos_out(db: Session, target: User, actor: User) -> UserPermissionsOut:
    otorgados, quitados = overrides(db, target.id)
    return UserPermissionsOut(
        user_id=target.id,
        full_name=target.full_name,
        role_name=target.role.name,
        role_permissions=sorted(role_permissions(target)),
        granted=sorted(otorgados),
        revoked=sorted(quitados),
        effective=sorted(effective_permissions(db, target)),
        editable=sorted(permisos_editables(db, actor)) if target.role.name in ROLES_PERSONALIZABLES else [],
    )


def catalogo_permisos(db: Session) -> list[PermissionCatalogOut]:
    permisos = db.scalars(select(Permission).order_by(Permission.code)).all()
    return [PermissionCatalogOut(code=p.code, description=p.description, delegable=p.code in DELEGABLE) for p in permisos]


def permisos_de_usuario(db: Session, actor: User, user_id: int) -> UserPermissionsOut:
    return permisos_out(db, usuario_de_mi_clinica(db, user_id, actor), actor)


def asignar_permisos(db: Session, actor: User, user_id: int, data: UserPermissionsUpdateIn) -> UserPermissionsOut:
    target = usuario_de_mi_clinica(db, user_id, actor)
    if target.id == actor.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No puedes cambiar tus propios permisos")
    if target.role.name not in ROLES_PERSONALIZABLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo se personalizan permisos de odontologos y recepcionistas")

    granted, revoked = set(data.granted), set(data.revoked)
    if granted & revoked:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Un permiso no puede estar otorgado y quitado a la vez")

    editables = permisos_editables(db, actor)
    no_permitidos = (granted | revoked) - editables
    if no_permitidos:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"No puedes dar ni quitar estos permisos: {', '.join(sorted(no_permitidos))}",
        )

    del_rol = role_permissions(target)
    granted -= del_rol  # si ya lo trae su rol no hace falta otorgarlo
    sobran = revoked - del_rol
    if sobran:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"No se puede quitar lo que su rol no trae: {', '.join(sorted(sobran))}",
        )

    ids = {p.code: p.id for p in db.scalars(select(Permission).where(Permission.code.in_(granted | revoked))).all()}
    db.execute(delete(UserPermissionOverride).where(UserPermissionOverride.user_id == target.id))
    for code in granted:
        db.add(UserPermissionOverride(user_id=target.id, permission_id=ids[code], allowed=True, created_by=actor.id))
    for code in revoked:
        db.add(UserPermissionOverride(user_id=target.id, permission_id=ids[code], allowed=False, created_by=actor.id))
    db.commit()

    log_event(db, "USER_PERMISSIONS_CHANGED", actor.id,
              f"target={target.id} +{','.join(sorted(granted)) or '-'} -{','.join(sorted(revoked)) or '-'}"[:300])
    return permisos_out(db, target, actor)
