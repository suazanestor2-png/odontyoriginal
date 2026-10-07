from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import User
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

def require_permission(code: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        user_permissions = {p.code for p in user.role.permissions}
        if code not in user_permissions:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permisos para esta accion")
        return user

    return checker