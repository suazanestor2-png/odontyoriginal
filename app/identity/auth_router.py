from fastapi import APIRouter, Body, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_active_user, get_current_user
from app.identity import service
from app.identity.models import User
from app.identity.schemas import (
    ChangePasswordIn, ForgotPasswordIn, LoginIn, MFACodeIn, MFALoginRequiredOut, MFASetupOut,
    MFAVerifyIn, RefreshIn, ResetPasswordIn, SelfUpdateIn, TokenOut, UserOut,
)

router = APIRouter(prefix="/auth", tags=["Autenticacion"])

# El registro publico (/auth/register) se elimino: las cuentas solo son para el personal
# de la clinica y las crea el admin desde /users. Los pacientes no tienen cuenta.


@router.post("/login", response_model=TokenOut | MFALoginRequiredOut)
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    return service.iniciar_sesion(db, response, data)


@router.post("/mfa/verify", response_model=TokenOut)
def mfa_verify(data: MFAVerifyIn, response: Response, db: Session = Depends(get_db)):
    return service.verificar_mfa_login(db, response, data)


@router.post("/refresh", response_model=TokenOut)
def refresh(
    request: Request,
    response: Response,
    data: RefreshIn | None = Body(default=None),
    db: Session = Depends(get_db),
):
    return service.renovar_sesion(db, request, response, data)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    data: RefreshIn | None = Body(default=None),
    db: Session = Depends(get_db),
):
    service.cerrar_sesion(db, request, response, data)


# /me se queda con get_current_user a proposito: el frontend puede consultarlo
# aunque deba cambiar la clave, y asi leer must_change_password.
@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.mi_perfil(db, user)


@router.patch("/me", response_model=UserOut)
def update_me(
    data: SelfUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_active_user),
):
    """Cada usuario edita sus propios datos (nombre y telefono)."""
    return service.actualizar_mi_perfil(db, user, data)


@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordIn, db: Session = Depends(get_db)):
    return service.solicitar_recuperacion(db, data)


@router.post("/reset-password")
def reset_password(data: ResetPasswordIn, db: Session = Depends(get_db)):
    return service.restablecer_contrasena(db, data)


# Los endpoints de MFA usan get_active_user (primero debe cambiar la clave temporal)
@router.post("/mfa/setup", response_model=MFASetupOut)
def mfa_setup(user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    return service.configurar_mfa(db, user)


@router.post("/mfa/enable")
def mfa_enable(data: MFACodeIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    return service.activar_mfa(db, user, data)


@router.post("/mfa/disable")
def mfa_disable(data: MFACodeIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    return service.desactivar_mfa(db, user, data)


# Unico endpoint permitido mientras must_change_password este activo (usa get_current_user)
@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    data: ChangePasswordIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    service.cambiar_contrasena(db, user, data)
