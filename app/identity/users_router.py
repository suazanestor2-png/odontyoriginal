from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permission
from app.identity import service
from app.identity.models import User
from app.identity.schemas import ActiveChangeIn, AuditLogOut, RoleChangeIn, UserCreateIn, UserOut, UserUpdateIn

router = APIRouter(prefix="/users", tags=["Usuarios y permisos"])


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreateIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("users.create")),
):
    """El admin no escribe contrasena: se genera una temporal y se envia por correo."""
    return service.crear_usuario(db, background, actor, data)


@router.patch("/{user_id}/role", response_model=UserOut)
def change_role(
    user_id: int,
    data: RoleChangeIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("users.manage_role")),
):
    return service.cambiar_rol(db, actor, user_id, data)


@router.patch("/{user_id}/active", response_model=UserOut)
def change_active(
    user_id: int,
    data: ActiveChangeIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("users.manage_active")),
):
    return service.cambiar_activo(db, actor, user_id, data)


@router.get("/audit-log", response_model=list[AuditLogOut])
def get_audit_log(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("audit.view")),
    limit: int = 100,
):
    return service.bitacora(db, limit)


@router.get("", response_model=list[UserOut])
def list_users(
    response: Response,
    search: str | None = Query(None, description="Busca por nombre o correo"),
    role: str | None = Query(None, description="Filtra por rol"),
    is_active: bool | None = Query(None, description="Filtra por activo/inactivo"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("users.view")),
):
    items, total = service.listar_usuarios(db, actor, search, role, is_active, limit, offset)
    response.headers["X-Total-Count"] = str(total)
    return items


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    data: UserUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("users.edit")),
):
    return service.actualizar_usuario(db, actor, user_id, data)
