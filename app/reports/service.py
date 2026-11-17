from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.billing.models import Expense, Invoice, Payment
from app.reports.schemas import Change

CERO = Decimal("0")


def change(current: Decimal | int, previous: Decimal | int) -> Change:
    current, previous = Decimal(current), Decimal(previous)
    diff = current - previous
    percent = None if previous == 0 else round(float(diff / abs(previous) * 100), 1)
    trend = "subio" if diff > 0 else "bajo" if diff < 0 else "igual"
    return Change(current=current, previous=previous, difference=diff, percent=percent, trend=trend)


def previous_range(start: date, end: date) -> tuple[date, date]:
    """Periodo inmediatamente anterior, de la misma cantidad de dias."""
    dias = (end - start).days + 1
    return start - timedelta(days=dias), start - timedelta(days=1)


def _scope(query, model, clinic_id: int | None):
    return query.where(model.clinic_id == clinic_id) if clinic_id is not None else query


def income_total(db: Session, clinic_id: int | None, start: date, end: date) -> Decimal:
    q = select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.paid_on >= start, Payment.paid_on <= end)
    return Decimal(db.scalar(_scope(q, Payment, clinic_id)))


def expenses_total(db: Session, clinic_id: int | None, start: date, end: date) -> Decimal:
    q = select(func.coalesce(func.sum(Expense.amount), 0)).where(
        Expense.status == "pagado", Expense.paid_on >= start, Expense.paid_on <= end
    )
    return Decimal(db.scalar(_scope(q, Expense, clinic_id)))


def invoiced_total(db: Session, clinic_id: int | None, start: date, end: date) -> Decimal:
    q = select(func.coalesce(func.sum(Invoice.total), 0)).where(
        Invoice.status != "anulada", Invoice.issue_date >= start, Invoice.issue_date <= end
    )
    return Decimal(db.scalar(_scope(q, Invoice, clinic_id)))


def daily_income(db: Session, clinic_id: int | None, start: date, end: date) -> dict[date, Decimal]:
    q = select(Payment.paid_on, func.sum(Payment.amount)).where(Payment.paid_on >= start, Payment.paid_on <= end)
    q = _scope(q, Payment, clinic_id).group_by(Payment.paid_on)
    return {d: Decimal(v) for d, v in db.execute(q).all()}


def daily_expenses(db: Session, clinic_id: int | None, start: date, end: date) -> dict[date, Decimal]:
    q = select(Expense.paid_on, func.sum(Expense.amount)).where(
        Expense.status == "pagado", Expense.paid_on >= start, Expense.paid_on <= end
    )
    q = _scope(q, Expense, clinic_id).group_by(Expense.paid_on)
    return {d: Decimal(v) for d, v in db.execute(q).all()}


def profit_message(profit: Change, unidad: str = "periodo") -> str:
    if profit.trend == "igual":
        return f"La ganancia de este {unidad} es igual a la del {unidad} anterior."
    mas_menos = "mas" if profit.trend == "subio" else "menos"
    detalle = f" ({profit.percent:+.1f}%)" if profit.percent is not None else ""
    return f"Este {unidad} hubo {mas_menos} ganancia que el {unidad} anterior{detalle}."


# ---------- Agrupacion por dia / semana / mes ----------

MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def bucket_start(d: date, group_by: str) -> date:
    if group_by == "day":
        return d
    if group_by == "week":
        return d - timedelta(days=d.weekday())  # lunes
    return d.replace(day=1)


def next_bucket(start: date, group_by: str) -> date:
    if group_by == "day":
        return start + timedelta(days=1)
    if group_by == "week":
        return start + timedelta(days=7)
    return (start.replace(day=28) + timedelta(days=4)).replace(day=1)


def bucket_label(start: date, group_by: str) -> str:
    if group_by == "day":
        return start.strftime("%d/%m/%Y")
    if group_by == "week":
        return f"Semana del {start.strftime('%d/%m/%Y')}"
    return f"{MESES[start.month - 1]} {start.year}"


def build_buckets(start: date, end: date, group_by: str) -> list[tuple[date, date]]:
    buckets = []
    actual = bucket_start(start, group_by)
    while actual <= end:
        siguiente = next_bucket(actual, group_by)
        buckets.append((actual, siguiente - timedelta(days=1)))
        actual = siguiente
    return buckets


def sum_by_bucket(daily: dict[date, Decimal], buckets: list[tuple[date, date]]) -> list[Decimal]:
    totales = defaultdict(lambda: CERO)
    for dia, valor in daily.items():
        for i, (ini, fin) in enumerate(buckets):
            if ini <= dia <= fin:
                totales[i] += valor
                break
    return [totales[i] for i in range(len(buckets))]
