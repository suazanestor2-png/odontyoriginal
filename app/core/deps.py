from fastapi import Depends, HTTPException, status
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


def require_permission(code: str):
    def checker(user: User = Depends(get_active_user)) -> User:   # CAMBIO: antes get_current_user
        user_permissions = {p.code for p in user.role.permissions}
        if code not in user_permissions:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permisos para esta accion")
        return user

    return checker