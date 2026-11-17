from sqlalchemy import select
from sqlalchemy.orm import Session

from app.identity.models import Role, User
from app.notifications.models import Notification


def clinic_staff(db: Session, clinic_id: int, roles: tuple[str, ...]) -> list[User]:
    """Usuarios activos de la clinica con alguno de esos roles, probando en orden (el primero que tenga gente)."""
    for rol in roles:
        usuarios = db.scalars(
            select(User).join(Role, User.role_id == Role.id).where(
                User.clinic_id == clinic_id, User.is_active.is_(True), Role.name == rol,
            )
        ).all()
        if usuarios:
            return list(usuarios)
    return []


def notify(db: Session, users: list[User], clinic_id: int, type_: str, title: str, message: str,
           patient_id: int | None = None, appointment_id: int | None = None) -> None:
    """Agrega una notificacion interna (campanita) para cada usuario. No hace commit."""
    for user in users:
        db.add(Notification(
            clinic_id=clinic_id, user_id=user.id, type=type_, title=title, message=message,
            patient_id=patient_id, appointment_id=appointment_id,
        ))
