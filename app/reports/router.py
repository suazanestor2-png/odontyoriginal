from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.appointments.models import Appointment
from app.billing.models import Expense, Invoice, Payment
from app.core.database import get_db
from app.core.dates import today_bogota
from app.core.deps import require_permission
from app.identity.models import User
from app.patients.models import Patient
from app.reports.schemas import (
    AppointmentsReportOut, CategoryTotal, CompareBlock, DentistActivity, FinanceCompareOut,
    FinanceSeriesOut, FinanceSummaryOut, MethodTotal, Payables, Period, Receivables, SeriesPoint,
)
from app.reports.service import (
    CERO, build_buckets, bucket_label, change, daily_expenses, daily_income, expenses_total,
    income_total, invoiced_total, previous_range, profit_message, sum_by_bucket,
)

router = APIRouter(prefix="/reports", tags=["Reportes"])

MAX_DIAS = 366 * 3


def _clinic(actor: User) -> int | None:
    """El super_admin ve el consolidado de todas las clinicas; los demas, solo la suya."""
    return None if actor.role.name == "super_admin" else actor.clinic_id


def _rango(from_date: date | None, to_date: date | None) -> tuple[date, date]:
    """Por defecto: el mes actual hasta hoy."""
    hoy = today_bogota()
    end = to_date or hoy
    start = from_date or end.replace(day=1)
    if start > end:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "from_date no puede ser posterior a to_date")
    if (end - start).days > MAX_DIAS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El rango maximo es de 3 anios")
    return start, end


def _scope(query, model, clinic_id):
    return query.where(model.clinic_id == clinic_id) if clinic_id is not None else query


def _bloque(db: Session, clinic_id, start: date, end: date, prev_start: date, prev_end: date, unidad: str) -> CompareBlock:
    ing = change(income_total(db, clinic_id, start, end), income_total(db, clinic_id, prev_start, prev_end))
    gas = change(expenses_total(db, clinic_id, start, end), expenses_total(db, clinic_id, prev_start, prev_end))
    gan = change(ing.current - gas.current, ing.previous - gas.previous)
    return CompareBlock(
        period=Period(from_date=start, to_date=end),
        previous_period=Period(from_date=prev_start, to_date=prev_end),
        income=ing, expenses=gas, profit=gan, message=profit_message(gan, unidad),
    )


@router.get("/finance/summary", response_model=FinanceSummaryOut)
def finance_summary(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("reports.view")),
):
    """Tarjetas del dashboard: ingresos, gastos, ganancia y pendientes, comparados con el periodo anterior."""
    clinic_id = _clinic(actor)
    start, end = _rango(from_date, to_date)
    prev_start, prev_end = previous_range(start, end)
    bloque = _bloque(db, clinic_id, start, end, prev_start, prev_end, "periodo")
    facturado = change(invoiced_total(db, clinic_id, start, end), invoiced_total(db, clinic_id, prev_start, prev_end))

    hoy = today_bogota()
    abiertas = _scope(select(Invoice).where(Invoice.status.in_(("pendiente", "parcial"))), Invoice, clinic_id)
    abiertas = db.scalars(abiertas).all()
    pendientes_gasto = db.execute(_scope(
        select(func.coalesce(func.sum(Expense.amount), 0), func.count()).where(Expense.status == "pendiente"),
        Expense, clinic_id,
    )).one()

    return FinanceSummaryOut(
        period=bloque.period,
        previous_period=bloque.previous_period,
        income=bloque.income,
        expenses=bloque.expenses,
        profit=bloque.profit,
        invoiced=facturado,
        receivables=Receivables(
            total=sum((i.balance for i in abiertas), CERO),
            overdue=sum((i.balance for i in abiertas if i.due_date < hoy), CERO),
            open_invoices=len(abiertas),
        ),
        payables=Payables(total=Decimal(pendientes_gasto[0]), pending_expenses=pendientes_gasto[1]),
        message=bloque.message,
    )


@router.get("/finance/series", response_model=FinanceSeriesOut)
def finance_series(
    group_by: str = Query("month", pattern=r"^(day|week|month)$"),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("reports.view")),
):
    """
    Datos para las graficas: ingresos, gastos y ganancia por dia, semana o mes, y cada punto
    comparado con el anterior. Por defecto: 30 dias, 12 semanas o 12 meses hasta hoy.
    """
    clinic_id = _clinic(actor)
    end = to_date or today_bogota()
    if from_date:
        start = from_date
    elif group_by == "day":
        start = end - timedelta(days=29)
    elif group_by == "week":
        start = end - timedelta(weeks=11)
    else:
        start = (end.replace(day=1) - timedelta(days=330)).replace(day=1)
    start, end = _rango(start, end)

    buckets = build_buckets(start, end, group_by)
    if len(buckets) > 400:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Demasiados puntos: usa un rango menor o agrupa por semana/mes")

    # Se incluye un periodo extra antes del primero para poder comparar el primer punto
    previo = build_buckets(buckets[0][0] - timedelta(days=1), buckets[0][0] - timedelta(days=1), group_by)
    todos = previo + buckets
    ingresos = sum_by_bucket(daily_income(db, clinic_id, todos[0][0], todos[-1][1]), todos)
    gastos = sum_by_bucket(daily_expenses(db, clinic_id, todos[0][0], todos[-1][1]), todos)
    ganancias = [i - g for i, g in zip(ingresos, gastos)]

    puntos = []
    for idx in range(1, len(todos)):
        ini, fin = todos[idx]
        puntos.append(SeriesPoint(
            label=bucket_label(ini, group_by),
            from_date=ini,
            to_date=min(fin, end),
            income=ingresos[idx],
            expenses=gastos[idx],
            profit=ganancias[idx],
            profit_vs_previous=change(ganancias[idx], ganancias[idx - 1]),
        ))

    con_movimiento = [p for p in puntos if p.income or p.expenses]
    best = max(con_movimiento, key=lambda p: p.profit).label if con_movimiento else None
    worst = min(con_movimiento, key=lambda p: p.profit).label if con_movimiento else None
    return FinanceSeriesOut(group_by=group_by, points=puntos, best=best, worst=worst)


@router.get("/finance/compare", response_model=FinanceCompareOut)
def finance_compare(
    reference_date: date | None = Query(None, description="Por defecto hoy"),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("reports.view")),
):
    """
    Hoy vs ayer, esta semana vs la anterior y este mes vs el anterior. Para la semana y el
    mes en curso se compara contra la misma cantidad de dias del periodo anterior (justo).
    """
    clinic_id = _clinic(actor)
    ref = reference_date or today_bogota()

    dia = _bloque(db, clinic_id, ref, ref, ref - timedelta(days=1), ref - timedelta(days=1), "dia")

    lunes = ref - timedelta(days=ref.weekday())
    transcurridos = (ref - lunes).days
    semana = _bloque(db, clinic_id, lunes, ref, lunes - timedelta(days=7),
                     lunes - timedelta(days=7) + timedelta(days=transcurridos), "semana")

    inicio_mes = ref.replace(day=1)
    fin_mes_ant = inicio_mes - timedelta(days=1)
    inicio_mes_ant = fin_mes_ant.replace(day=1)
    hasta_ant = min(inicio_mes_ant.replace(day=min(ref.day, fin_mes_ant.day)), fin_mes_ant)
    mes = _bloque(db, clinic_id, inicio_mes, ref, inicio_mes_ant, hasta_ant, "mes")

    return FinanceCompareOut(day=dia, week=semana, month=mes)


@router.get("/finance/payment-methods", response_model=list[MethodTotal])
def payment_methods(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("reports.view")),
):
    clinic_id = _clinic(actor)
    start, end = _rango(from_date, to_date)
    q = select(Payment.method, func.sum(Payment.amount), func.count()).where(
        Payment.paid_on >= start, Payment.paid_on <= end
    )
    filas = db.execute(_scope(q, Payment, clinic_id).group_by(Payment.method)).all()
    total = sum((Decimal(f[1]) for f in filas), CERO)
    salida = [
        MethodTotal(method=m, total=Decimal(t), count=c, percent=round(float(Decimal(t) / total * 100), 1) if total else 0.0)
        for m, t, c in filas
    ]
    return sorted(salida, key=lambda x: x.total, reverse=True)


@router.get("/finance/expenses-by-category", response_model=list[CategoryTotal])
def expenses_by_category(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("reports.view")),
):
    clinic_id = _clinic(actor)
    start, end = _rango(from_date, to_date)
    q = select(Expense.category, func.sum(Expense.amount), func.count()).where(
        Expense.status == "pagado", Expense.paid_on >= start, Expense.paid_on <= end
    )
    filas = db.execute(_scope(q, Expense, clinic_id).group_by(Expense.category)).all()
    total = sum((Decimal(f[1]) for f in filas), CERO)
    salida = [
        CategoryTotal(category=c, total=Decimal(t), count=n, percent=round(float(Decimal(t) / total * 100), 1) if total else 0.0)
        for c, t, n in filas
    ]
    return sorted(salida, key=lambda x: x.total, reverse=True)


@router.get("/appointments", response_model=AppointmentsReportOut)
def appointments_report(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("reports.view")),
):
    """Citas por estado, cancelaciones, inasistencias y pacientes nuevos en el periodo."""
    clinic_id = _clinic(actor)
    start, end = _rango(from_date, to_date)
    prev_start, prev_end = previous_range(start, end)

    def por_estado(ini, fin) -> dict[str, int]:
        q = select(Appointment.status, func.count()).where(
            Appointment.scheduled_date >= ini, Appointment.scheduled_date <= fin
        )
        return dict(db.execute(_scope(q, Appointment, clinic_id).group_by(Appointment.status)).all())

    def nuevos(ini, fin) -> int:
        q = select(func.count()).select_from(Patient).where(
            func.date(Patient.created_at) >= ini, func.date(Patient.created_at) <= fin
        )
        return db.scalar(_scope(q, Patient, clinic_id))

    actual, anterior = por_estado(start, end), por_estado(prev_start, prev_end)
    total = sum(actual.values())
    atendidos_q = select(func.count(func.distinct(Appointment.patient_id))).where(
        Appointment.status == "atendida", Appointment.scheduled_date >= start, Appointment.scheduled_date <= end
    )
    return AppointmentsReportOut(
        period=Period(from_date=start, to_date=end),
        total=change(total, sum(anterior.values())),
        attended=change(actual.get("atendida", 0), anterior.get("atendida", 0)),
        by_status={s: actual.get(s, 0) for s in ("programada", "confirmada", "atendida", "cancelada", "no_asistio")},
        cancellation_rate=round(actual.get("cancelada", 0) / total * 100, 1) if total else 0.0,
        no_show_rate=round(actual.get("no_asistio", 0) / total * 100, 1) if total else 0.0,
        new_patients=change(nuevos(start, end), nuevos(prev_start, prev_end)),
        patients_attended=db.scalar(_scope(atendidos_q, Appointment, clinic_id)),
    )


@router.get("/dentists", response_model=list[DentistActivity])
def dentists_activity(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("reports.view")),
):
    """Citas, atenciones y dinero facturado/cobrado por cada odontologo."""
    clinic_id = _clinic(actor)
    start, end = _rango(from_date, to_date)

    citas_q = select(Appointment.dentist_id, Appointment.status, func.count()).where(
        Appointment.scheduled_date >= start, Appointment.scheduled_date <= end
    )
    citas = db.execute(_scope(citas_q, Appointment, clinic_id).group_by(Appointment.dentist_id, Appointment.status)).all()

    fact_q = select(Appointment.dentist_id, func.sum(Invoice.total)).join(
        Appointment, Invoice.appointment_id == Appointment.id
    ).where(Invoice.status != "anulada", Invoice.issue_date >= start, Invoice.issue_date <= end)
    facturado = dict(db.execute(_scope(fact_q, Invoice, clinic_id).group_by(Appointment.dentist_id)).all())

    cob_q = select(Appointment.dentist_id, func.sum(Payment.amount)).join(
        Invoice, Payment.invoice_id == Invoice.id
    ).join(Appointment, Invoice.appointment_id == Appointment.id).where(
        Payment.paid_on >= start, Payment.paid_on <= end
    )
    cobrado = dict(db.execute(_scope(cob_q, Payment, clinic_id).group_by(Appointment.dentist_id)).all())

    por_odontologo: dict[int, dict[str, int]] = {}
    for dentist_id, estado, n in citas:
        por_odontologo.setdefault(dentist_id, {})[estado] = n
    for dentist_id in list(facturado) + list(cobrado):
        por_odontologo.setdefault(dentist_id, {})

    salida = []
    for dentist_id, estados in por_odontologo.items():
        dentist = db.get(User, dentist_id)
        salida.append(DentistActivity(
            dentist_id=dentist_id,
            dentist_name=dentist.full_name if dentist else "",
            appointments=sum(estados.values()),
            attended=estados.get("atendida", 0),
            cancelled=estados.get("cancelada", 0),
            no_show=estados.get("no_asistio", 0),
            invoiced=Decimal(facturado.get(dentist_id) or 0),
            collected=Decimal(cobrado.get(dentist_id) or 0),
        ))
    return sorted(salida, key=lambda x: x.collected, reverse=True)
