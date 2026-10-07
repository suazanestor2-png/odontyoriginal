from app.core.database import SessionLocal
from app.models import Permission, Role

ROLE_NAMES = ["super_admin", "admin", "odontologo", "recepcionista", "usuario"]

# Iremos agregando codigos aqui a medida que construyamos cada endpoint protegido.
PERMISSION_CODES = {
    "users.view": "Ver la lista de usuarios",
    "users.manage_role": "Cambiar el rol de un usuario",
    "users.manage_active": "Activar o desactivar un usuario",
    "audit.view": "Consultar el historial de auditoria",
}

ROLE_PERMISSIONS = {
    "super_admin": list(PERMISSION_CODES.keys()),
    "admin": ["users.view", "users.manage_role", "users.manage_active"],
    "odontologo": [],
    "recepcionista": [],
    "usuario": [],
}


def seed_roles_and_permissions() -> None:
    with SessionLocal() as db:
        roles = {r.name: r for r in db.query(Role).all()}
        for name in ROLE_NAMES:
            if name not in roles:
                roles[name] = Role(name=name)
                db.add(roles[name])
        db.flush()  # asigna los IDs sin cerrar la transaccion

        perms = {p.code: p for p in db.query(Permission).all()}
        for code, desc in PERMISSION_CODES.items():
            if code not in perms:
                perms[code] = Permission(code=code, description=desc)
                db.add(perms[code])
        db.flush()

        for role_name, codes in ROLE_PERMISSIONS.items():
            roles[role_name].permissions = [perms[c] for c in codes]

        db.commit()