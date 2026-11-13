from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status   # NUEVO: BackgroundTasks
from sqlalchemy import func, or_, select                                                # NUEVO: or_
from sqlalchemy.exc import IntegrityError                                         # NUEVO
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permission
from app.core.security import generate_temp_password, hash_password              # NUEVO
from app.email_service import send_welcome_email                                  # NUEVO
from app.identity.audit import log_event
from app.identity.models import AuditLog, Role, User
from app.identity.schemas import ActiveChangeIn, AuditLogOut, RoleChangeIn, UserCreateIn, UserUpdateIn, UserOut # NUEVO: ActiviChangeIn
from app.identity.tokens import revoke_all_refresh_tokens #NUEVO Funcion para reutilizar
from app.core.validators import _telefono # este import para dar error 409


router = APIRouter(prefix="/users", tags=["Usuarios y permisos"])

# Roles que un admin (no super_admin) tiene permitido tocar y asignar
ADMIN_ALLOWED_ROLES = {"odontologo", "recepcionista"}


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
        if target.clinic_id != actor.clinic_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
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


@router.patch("/{user_id}/active", response_model=UserOut)
def change_active(
    user_id: int,
    data: ActiveChangeIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("users.manage_active")),
):
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


@router.get("/audit-log", response_model=list[AuditLogOut])
def get_audit_log(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("audit.view")),
    limit: int = 100,
):
    logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
    return logs

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

    response.headers["X-Total-Count"] = str(total)
    return [to_user_out(u) for u in items]

@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    data: UserUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("users.edit")),
):
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