from fastapi import Request
from sqlalchemy.orm import Session

from app.clinical_history.models import ClinicalAccessLog
from app.core.mixins import utcnow


def client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    # En Render la app esta detras de un proxy: la IP real viene en X-Forwarded-For
    reenviada = request.headers.get("x-forwarded-for")
    if reenviada:
        return reenviada.split(",")[0].strip()[:45]
    return request.client.host[:45] if request.client else None


def log_access(
    db: Session,
    request: Request | None,
    user,
    clinic_id: int,
    patient_id: int,
    action: str,
    resource_id: int | None = None,
) -> None:
    """Registra la consulta de informacion clinica (hace commit)."""
    db.add(ClinicalAccessLog(
        clinic_id=clinic_id, patient_id=patient_id, user_id=user.id, action=action,
        resource_id=resource_id, ip_address=client_ip(request), accessed_at=utcnow(),
    ))
    db.commit()
