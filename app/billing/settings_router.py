from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.billing.models import Invoice
from app.billing.schemas import BillingSettingsOut, BillingSettingsUpdateIn
from app.billing.service import get_or_create_settings
from app.core.database import get_db
from app.core.deps import require_permission
from app.identity.audit import log_event
from app.identity.models import User

router = APIRouter(prefix="/billing/settings", tags=["Facturacion"])


@router.get("", response_model=BillingSettingsOut)
def get_billing_settings(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("billing.view")),
):
    if not actor.clinic_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tu usuario no pertenece a ninguna clinica")
    settings = get_or_create_settings(db, actor.clinic_id)
    db.commit()
    return settings


@router.patch("", response_model=BillingSettingsOut)
def update_billing_settings(
    data: BillingSettingsUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("billing.settings")),
):
    if not actor.clinic_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tu usuario no pertenece a ninguna clinica")
    settings = get_or_create_settings(db, actor.clinic_id, lock=True)
    values = data.model_dump(exclude_unset=True)

    if values.get("next_number") is not None:
        # No se puede bajar el consecutivo por debajo de una factura ya emitida
        maximo = db.scalar(select(func.max(Invoice.number_seq)).where(Invoice.clinic_id == actor.clinic_id)) or 0
        if values["next_number"] <= maximo:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El consecutivo debe ser mayor que {maximo}")

    for field, value in values.items():
        if value is not None or field == "footer_text":
            setattr(settings, field, value)
    db.commit()
    db.refresh(settings)
    log_event(db, "BILLING_SETTINGS_UPDATED", actor.id, f"clinic={actor.clinic_id} campos={','.join(values)}")
    return settings
