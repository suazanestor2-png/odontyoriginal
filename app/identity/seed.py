from app.core.database import SessionLocal
from app.identity.models import Permission, Role

ROLE_NAMES = ["super_admin", "admin", "odontologo", "recepcionista", "usuario"]

# Iremos agregando permisos aqui a medida que construyamos cada endpoint.
PERMISSION_CODES = {
    "users.view": "Ver la lista de usuarios",
    "users.create": "Crear usuarios del personal",
    "users.edit": "Editar los datos de un usuario",
    "users.manage_role": "Cambiar el rol de un usuario",
    "users.manage_active": "Activar o desactivar un usuario",
    "audit.view": "Consultar el historial de auditoria",
    "clinics.review": "Aprobar o rechazar el registro de una clinica",
    "patients.view": "Ver la lista y el detalle de pacientes",
    "patients.create": "Registrar un paciente nuevo",
    "patients.edit": "Editar el perfil de un paciente",
    "appointments.view": "Ver las citas",
    "appointments.create": "Crear una cita",
    "appointments.edit": "Reprogramar, cancelar o actualizar el estado de una cita",
}

ROLE_PERMISSIONS = {
    "super_admin": list(PERMISSION_CODES.keys()),
    "admin": ["users.view", "users.create", "users.edit", "users.manage_role", "users.manage_active", "appointments.view", "appointments.create", "appointments.edit",
              "patients.view", "patients.create", "patients.edit"],
    "odontologo": ["patients.view", "appointments.view", "appointments.edit"],
    "recepcionista": ["patients.view", "patients.create", "patients.edit", "appointments.view", "appointments.create", "appointments.edit"],
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