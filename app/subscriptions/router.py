from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clinics.models import Clinic
from app.core.database import get_db
from app.core.dates import today_bogota
from app.core.deps import get_active_user, require_permission
from app.identity.audit import log_event
from app.identity.models import User
from app.subscriptions.models import ClinicSubscription, SubscriptionPlan, SubscriptionRenewal
from app.subscriptions.schemas import (
    PlanOut, PlanUpdateIn, RenewalOut, RenewIn, SubscriptionStatusOut,
)
from app.subscriptions.service import ensure_trial, new_period, status_out

router = APIRouter(prefix="/subscriptions", tags=["Suscripciones"])


@router.get("/me", response_model=SubscriptionStatusOut)
def my_subscription(
    db: Session = Depends(get_db),
    actor: User = Depends(get_active_user),
):
    """Estado de la suscripcion de mi clinica. El frontend lo usa para mostrar el aviso (banner)."""
    if not actor.clinic_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tu usuario no pertenece a ninguna clinica")
    sub = ensure_trial(db, actor.clinic_id)
    db.commit()
    return status_out(db, sub)


@router.get("/plans", response_model=list[PlanOut])
def list_plans(
    db: Session = Depends(get_db),
    actor: User = Depends(get_active_user),
):
    return db.scalars(select(SubscriptionPlan).order_by(SubscriptionPlan.months)).all()


@router.patch("/plans/{code}", response_model=PlanOut)
def update_plan(
    code: str,
    data: PlanUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("subscriptions.manage")),
):
    plan = db.get(SubscriptionPlan, code)
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan no encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(plan, field, value)
    db.commit()
    db.refresh(plan)
    log_event(db, "SUBSCRIPTION_PLAN_UPDATED", actor.id, f"plan={code} price={plan.price}")
    return plan


@router.get("", response_model=list[SubscriptionStatusOut])
def list_subscriptions(
    status_filter: str | None = Query(None, alias="status", pattern=r"^(activa|por_vencer|en_gracia|solo_lectura)$"),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("subscriptions.manage")),
):
    """Todas las clinicas con su estado (para el panel del super_admin)."""
    hoy = today_bogota()
    subs = db.scalars(
        select(ClinicSubscription).join(Clinic, ClinicSubscription.clinic_id == Clinic.id)
        .order_by(ClinicSubscription.current_period_end)
    ).all()
    salida = [status_out(db, s, hoy) for s in subs]
    if status_filter:
        salida = [s for s in salida if s.status == status_filter]
    return salida


@router.post("/{clinic_id}/renew", response_model=SubscriptionStatusOut)
def renew_subscription(
    clinic_id: int,
    data: RenewIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("subscriptions.manage")),
):
    """Registra el pago de una clinica y extiende su suscripcion (1 mes o 1 anio segun el plan)."""
    clinic = db.get(Clinic, clinic_id)
    if not clinic:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clinica no encontrada")
    plan = db.get(SubscriptionPlan, data.plan_code)
    if not plan or not plan.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Plan no valido")

    hoy = today_bogota()
    paid_on = data.paid_on or hoy
    if paid_on > hoy:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La fecha de pago no puede ser futura")

    sub = ensure_trial(db, clinic_id, hoy)
    inicio, fin = new_period(sub, plan, hoy)

    db.add(SubscriptionRenewal(
        clinic_id=clinic_id, plan_code=plan.code,
        amount=data.amount if data.amount is not None else plan.price,
        period_start=inicio, period_end=fin, paid_on=paid_on, method=data.method,
        reference=data.reference, notes=data.notes, created_by=actor.id,
    ))
    sub.plan_code = plan.code
    sub.is_trial = False
    sub.current_period_start = inicio
    sub.current_period_end = fin
    sub.alert_7d_sent = sub.alert_3d_sent = sub.alert_1d_sent = False
    sub.alert_grace_sent = sub.alert_readonly_sent = False
    sub.updated_by = actor.id
    db.commit()
    db.refresh(sub)
    log_event(db, "SUBSCRIPTION_RENEWED", actor.id, f"clinic={clinic_id} plan={plan.code} hasta={fin}")
    return status_out(db, sub, hoy)


@router.get("/{clinic_id}/renewals", response_model=list[RenewalOut])
def list_renewals(
    clinic_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("subscriptions.manage")),
):
    return db.scalars(
        select(SubscriptionRenewal).where(SubscriptionRenewal.clinic_id == clinic_id)
        .order_by(SubscriptionRenewal.id.desc())
    ).all()
