from sqlalchemy import select
from sqlalchemy.orm import Session

from app.identity.models import Permission, User, UserPermissionOverride

# Permisos que un admin puede dar o quitar a su personal. Quedan fuera los de administracion
# (usuarios, roles, auditoria, configuracion de la clinica y de facturacion, suscripciones).
DELEGABLE = frozenset({
    "patients.view", "patients.create", "patients.edit",
    "appointments.view", "appointments.create", "appointments.edit",
    "clinical_history.view", "clinical_history.create",
    "odontogram.view", "odontogram.create",
    "notifications.create",
    "controls.view", "controls.create", "controls.edit",
    "billing.view", "billing.create", "billing.void",
    "expenses.manage", "reports.view",
    "consents.manage",
})

# Roles a los que un admin les puede personalizar permisos
ROLES_PERSONALIZABLES = frozenset({"odontologo", "recepcionista"})


def role_permissions(user: User) -> set[str]:
    return {p.code for p in user.role.permissions}


def overrides(db: Session, user_id: int) -> tuple[set[str], set[str]]:
    """(otorgados, quitados) de un usuario."""
    filas = db.execute(
        select(Permission.code, UserPermissionOverride.allowed)
        .join(Permission, UserPermissionOverride.permission_id == Permission.id)
        .where(UserPermissionOverride.user_id == user_id)
    ).all()
    otorgados = {code for code, allowed in filas if allowed}
    quitados = {code for code, allowed in filas if not allowed}
    return otorgados, quitados


def effective_permissions(db: Session, user: User) -> set[str]:
    """Permisos reales de la persona: los de su rol + los otorgados - los quitados."""
    otorgados, quitados = overrides(db, user.id)
    return (role_permissions(user) | otorgados) - quitados
