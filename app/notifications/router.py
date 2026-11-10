from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_active_user, require_permission
from app.identity.models import User
from app.notifications.models import Notification
from app.notifications.schemas import NotificationCreateIn, NotificationOut

router = APIRouter(prefix="/notifications", tags=["Notificaciones"])


def _to_out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        user_id=n.user_id,
        type=n.type,
        title=n.title,
        message=n.message,
        appointment_id=n.appointment_id,
        patient_id=n.patient_id,
        is_read=n.is_read,
        read_at=n.read_at,
        created_at=n.created_at,
    )


@router.get("", response_model=list[NotificationOut])
def list_my_notifications(
    response: Response,
    unread_only: bool = Query(default=False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    actor: User = Depends(get_active_user),
):
    query = select(Notification).where(Notification.user_id == actor.id)
    if unread_only:
        query = query.where(Notification.is_read.is_(False))

    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    items = db.scalars(query.order_by(Notification.created_at.desc()).limit(limit).offset(offset)).all()

    response.headers["X-Total-Count"] = str(total)
    return [_to_out(n) for n in items]


@router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_active_user),
):
    notif = db.get(Notification, notification_id)
    if not notif or notif.user_id != actor.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notificacion no encontrada")

    if not notif.is_read:
        notif.is_read = True
        notif.read_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        db.refresh(notif)

    return _to_out(notif)


@router.post("", response_model=NotificationOut, status_code=status.HTTP_201_CREATED)
def create_notification(
    data: NotificationCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("notifications.create")),
):
    recipient = db.get(User, data.user_id)
    if not recipient or (actor.role.name != "super_admin" and recipient.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario destinatario no encontrado")

    notif = Notification(
        clinic_id=recipient.clinic_id,
        user_id=data.user_id,
        type=data.type,
        title=data.title,
        message=data.message,
        appointment_id=data.appointment_id,
        patient_id=data.patient_id,
        created_by=actor.id,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return _to_out(notif)