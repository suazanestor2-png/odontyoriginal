from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.identity.models import User
from app.core.security import decode_token

bearer = HTTPBearer()


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_token(creds.credentials, "access")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario no autorizado")
    return user


# NUEVO de lugar: ahora va antes de require_permission
def get_active_user(user: User = Depends(get_current_user)) -> User:
    # Mientras deba cambiar la clave temporal, solo puede usar /auth/change-password
    if user.must_change_password:
        raise HTTPException(
            status_code=403,
            detail={"code": "PASSWORD_CHANGE_REQUIRED", "message": "Debes cambiar tu contraseña"},
        )
    return user


METODOS_LECTURA = {"GET", "HEAD", "OPTIONS"}


def require_permission(code: str):
    def checker(
        request: Request,
        user: User = Depends(get_active_user),   # CAMBIO: antes get_current_user
        db: Session = Depends(get_db),
    ) -> User:
        from app.identity.permissions import effective_permissions  # import aqui para evitar ciclos
        user_permissions = effective_permissions(db, user)
        if code not in user_permissions:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permisos para esta accion")
        # Suscripcion vencida (despues de los dias de gracia): la clinica queda en solo lectura
        if request.method not in METODOS_LECTURA and user.role.name != "super_admin":
            from app.subscriptions.service import is_read_only  # import aqui para evitar ciclos
            if is_read_only(db, user.clinic_id):
                raise HTTPException(
                    status.HTTP_402_PAYMENT_REQUIRED,
                    detail={
                        "code": "SUBSCRIPTION_READ_ONLY",
                        "message": "La suscripcion de la clinica vencio: solo puedes consultar hasta que se renueve",
                    },
                )
        return user

    return checker