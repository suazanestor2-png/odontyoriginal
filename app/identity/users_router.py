from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status   # NUEVO: BackgroundTasks
from sqlalchemy import or_, select                                                # NUEVO: or_
from sqlalchemy.exc import IntegrityError                                         # NUEVO
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permission
from app.core.security import generate_temp_password, hash_password              # NUEVO
from app.email_service import send_welcome_email                                  # NUEVO
from app.identity.audit import log_event
from app.identity.models import AuditLog, Role, User
from app.identity.schemas import AuditLogOut, RoleChangeIn, UserCreateIn, UserOut  # NUEVO: UserCreateIn

router = APIRouter(prefix="/users", tags=["Usuarios y permisos"])

# Roles que un admin (no super_admin) tiene permitido tocar y asignar
ADMIN_ALLOWED_ROLES = {"usuario", "odontologo", "recepcionista"}


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


def get_target_user(db: Session, user_id: int) -> User:
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    return target


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("users.view")),
):
    users = db.scalars(select(User).order_by(User.id)).all()
    return [to_user_out(u) for u in users]


# NUEVO: crear trabajadores (el admin no escribe contraseña, se genera una temporal)
@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreateIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("users.create")),
):
    # Un admin normal solo puede crear estos 3 roles (igual que en change_role)
    if actor.role.name != "super_admin" and data.role not in ADMIN_ALLOWED_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Un admin solo puede crear odontologo, recepcionista o usuario",
        )

    exists = db.scalar(
        select(User).where(
            or_(User.email == data.email, User.document_number == data.document_number)
        )
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese correo o documento")

    role = db.scalar(select(Role).where(Role.name == data.role))
    if not role:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rol invalido")

    temp_password = generate_temp_password()

    user = User(
        email=data.email,
        document_number=data.document_number,
        full_name=data.full_name,
        phone_number=data.phone_number,
        role_id=role.id,
        hashed_password=hash_password(temp_password),
        is_active=True,
        must_change_password=True,
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


@router.patch("/{user_id}/role", response_model=UserOut)
def change_role(
    user_id: int,
    data: RoleChangeIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("users.manage_role")),
):
    target = get_target_user(db, user_id)

    if actor.id == target.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No puedes modificar tu propio rol")

    if target.role.name == "super_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "El super admin no se puede modificar")

    if actor.role.name != "super_admin":
        # Un admin normal solo puede tocar y asignar estos 3 roles
        if target.role.name not in ADMIN_ALLOWED_ROLES:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Un admin no puede modificar a otro admin")
        if data.role not in ADMIN_ALLOWED_ROLES:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Un admin solo puede asignar odontologo, recepcionista o usuario")

    if data.role == "super_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No se puede asignar el rol super admin")

    new_role = db.scalar(select(Role).where(Role.name == data.role))
    if not new_role:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rol invalido")

    target.role_id = new_role.id
    db.commit()
    db.refresh(target)
    log_event(db, "ROLE_CHANGED", actor.id, f"target={target.id} nuevo_rol={data.role}")
    return to_user_out(target)


@router.get("/audit-log", response_model=list[AuditLogOut])
def get_audit_log(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("audit.view")),
    limit: int = 100,
):
    logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
    return logs