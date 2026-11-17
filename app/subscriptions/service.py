import calendar
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dates import today_bogota
from app.subscriptions.models import ClinicSubscription, SubscriptionPlan
from app.subscriptions.schemas import SubscriptionStatusOut

GRACE_DAYS = 5      # dias de gracia despues del vencimiento (todo sigue funcionando)
TRIAL_DAYS = 30     # prueba gratis para clinicas nuevas o que ya existian
WARNING_DAYS = 7    # desde cuantos dias antes se considera "por vencer"

PLANES_INICIALES = (
    ("mensual", "Plan mensual", 1),
    ("anual", "Plan anual", 12),
)


def seed_subscription_plans(db: Session) -> None:
    existentes = {p.code for p in db.scalars(select(SubscriptionPlan)).all()}
    for code, name, months in PLANES_INICIALES:
        if code not in existentes:
            db.add(SubscriptionPlan(code=code, name=name, months=months, price=0, is_active=True))
    db.commit()


def add_months(d: date, months: int) -> date:
    mes = d.month - 1 + months
    anio = d.year + mes // 12
    mes = mes % 12 + 1
    dia = min(d.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def get_subscription(db: Session, clinic_id: int) -> ClinicSubscription | None:
    return db.scalar(select(ClinicSubscription).where(ClinicSubscription.clinic_id == clinic_id))


def ensure_trial(db: Session, clinic_id: int, hoy: date | None = None) -> ClinicSubscription:
    """Crea la suscripcion de prueba si la clinica todavia no tiene una (sin commit)."""
    sub = get_subscription(db, clinic_id)
    if sub:
        return sub
    hoy = hoy or today_bogota()
    sub = ClinicSubscription(
        clinic_id=clinic_id, plan_code=None, is_trial=True,
        current_period_start=hoy, current_period_end=hoy + timedelta(days=TRIAL_DAYS - 1),
    )
    db.add(sub)
    db.flush()
    return sub


def compute_status(sub: ClinicSubscription, hoy: date | None = None) -> dict:
    hoy = hoy or today_bogota()
    days_left = (sub.current_period_end - hoy).days
    fin = sub.current_period_end.strftime("%d/%m/%Y")
    if days_left > WARNING_DAYS:
        estado, gracia, mensaje = "activa", 0, f"Tu suscripcion esta activa hasta el {fin}."
    elif days_left >= 0:
        estado, gracia = "por_vencer", 0
        cuando = "hoy" if days_left == 0 else ("manana" if days_left == 1 else f"en {days_left} dias")
        mensaje = f"Tu suscripcion vence {cuando} ({fin}). Renuevala para no perder acceso."
    elif days_left >= -GRACE_DAYS:
        estado = "en_gracia"
        gracia = GRACE_DAYS + days_left + 1  # incluye el dia de hoy
        mensaje = (f"Tu suscripcion vencio el {fin}. Tienes {gracia} dia(s) de gracia; "
                   "despues la cuenta quedara en solo lectura.")
    else:
        estado, gracia = "solo_lectura", 0
        mensaje = (f"Tu suscripcion vencio el {fin}. La cuenta esta en modo solo lectura: puedes consultar "
                   "la informacion, pero no crear ni modificar nada hasta renovar.")
    return {"status": estado, "days_left": days_left, "grace_days_left": gracia,
            "read_only": estado == "solo_lectura", "message": mensaje}


def status_out(db: Session, sub: ClinicSubscription, hoy: date | None = None) -> SubscriptionStatusOut:
    plan = db.get(SubscriptionPlan, sub.plan_code) if sub.plan_code else None
    return SubscriptionStatusOut(
        clinic_id=sub.clinic_id,
        clinic_name=sub.clinic.name,
        plan_code=sub.plan_code,
        plan_name=plan.name if plan else ("Prueba gratis" if sub.is_trial else None),
        is_trial=sub.is_trial,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        **compute_status(sub, hoy),
    )


def is_read_only(db: Session, clinic_id: int | None) -> bool:
    if not clinic_id:
        return False
    sub = get_subscription(db, clinic_id)
    return bool(sub) and compute_status(sub)["read_only"]


def new_period(sub: ClinicSubscription, plan: SubscriptionPlan, hoy: date) -> tuple[date, date]:
    """
    Si renueva antes de quedar en solo lectura, el nuevo periodo sigue justo despues del anterior
    (los dias de gracia no se regalan). Si ya estaba en solo lectura, arranca desde hoy.
    """
    if (sub.current_period_end - hoy).days >= -GRACE_DAYS:
        # Tambien aplica a la prueba gratis: si paga antes de que termine, el plan empieza al terminarla
        inicio = sub.current_period_end + timedelta(days=1)
    else:
        inicio = hoy
    fin = add_months(inicio, plan.months) - timedelta(days=1)
    return inicio, fin
