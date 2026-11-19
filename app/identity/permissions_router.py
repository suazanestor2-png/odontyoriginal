from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permission
from app.identity import service
from app.identity.models import User
from app.identity.schemas import PermissionCatalogOut, UserPermissionsOut, UserPermissionsUpdateIn

router = APIRouter(tags=["Usuarios y permisos"])


@router.get("/permissions", response_model=list[PermissionCatalogOut])
def permission_catalog(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("users.manage_permissions")),
):
    """Todos los permisos del sistema, con su descripcion y si se pueden delegar."""
    return service.catalogo_permisos(db)


@router.get("/users/{user_id}/permissions", response_model=UserPermissionsOut)
def get_user_permissions(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("users.manage_permissions")),
):
    return service.permisos_de_usuario(db, actor, user_id)


@router.put("/users/{user_id}/permissions", response_model=UserPermissionsOut)
def set_user_permissions(
    user_id: int,
    data: UserPermissionsUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("users.manage_permissions")),
):
    return service.asignar_permisos(db, actor, user_id, data)
