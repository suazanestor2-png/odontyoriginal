from sqlalchemy.orm import Session

from app.models import AuditLog


def log_event(db: Session, action: str, user_id: int | None = None, detail: str | None = None) -> None:
    db.add(AuditLog(action=action, user_id=user_id, detail=detail))
    db.commit()