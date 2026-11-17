from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permission
from app.identity.audit import log_event
from app.identity.models import Permission, User, UserPermissionOverride
from app.identity.permissions import (
    DELEGABLE, ROLES_PERSONALIZABLES, effective_permissions, overrides, role_permissions,
)
from app.identity.schemas import PermissionCatalogOut, UserPermissionsOut, UserPermissionsUpdateIn

router = APIRouter(tags=["Usuarios y permisos"])


def _editables(db: Session, actor: User) -> set[str]:
    """Un admin solo puede delegar permisos delegables que el mismo tenga."""
    if actor.role.name == "super_admin":
        return set(DELEGABLE)
    return DELEGABLE & effective_permissions(db, actor)


def _target(db: Session, user_id: int, actor: User) -> User:
    target = db.get(User, user_id)
    if not target or (actor.role.name != "super_admin" and target.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    return target


def _out(db: Session, target: User, actor: User) -> UserPermissionsOut:
    otorgados, quitados = overrides(db, target.id)
    return UserPermissionsOut(
        user_id=target.id,
        full_name=target.full_name,
        role_name=target.role.name,
        role_permissions=sorted(role_permissions(target)),
        granted=sorted(otorgados),
        revoked=sorted(quitados),
        effective=sorted(effective_permissions(db, target)),
        editable=sorted(_editables(db, actor)) if target.role.name in ROLES_PERSONALIZABLES else [],
    )


@router.get("/permissions", response_model=list[PermissionCatalogOut])
def permission_catalog(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("users.manage_permissions")),
):
    """Todos los permisos del sistema, con su descripcion y si se pueden delegar."""
    permisos = db.scalars(select(Permission).order_by(Permission.code)).all()
    return [PermissionCatalogOut(code=p.code, description=p.description, delegable=p.code in DELEGABLE) for p in permisos]


@router.get("/users/{user_id}/permissions", response_model=UserPermissionsOut)
def get_user_permissions(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("users.manage_permissions")),
):
    return _out(db, _target(db, user_id, actor), actor)


@router.put("/users/{user_id}/permissions", response_model=UserPermissionsOut)
def set_user_permissions(
    user_id: int,
    data: UserPermissionsUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("users.manage_permissions")),
):
    target = _target(db, user_id, actor)
    if target.id == actor.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No puedes cambiar tus propios permisos")
    if target.role.name not in ROLES_PERSONALIZABLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo se personalizan permisos de odontologos y recepcionistas")

    granted, revoked = set(data.granted), set(data.revoked)
    if granted & revoked:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Un permiso no puede estar otorgado y quitado a la vez")

    editables = _editables(db, actor)
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
    return _out(db, target, actor)
