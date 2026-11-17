from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class Change(BaseModel):
    """Un valor comparado contra el periodo anterior."""
    current: Decimal
    previous: Decimal
    difference: Decimal
    percent: float | None  # None si el periodo anterior fue 0
    trend: str              # "subio" | "bajo" | "igual"


class Period(BaseModel):
    from_date: date
    to_date: date


class Receivables(BaseModel):
    total: Decimal
    overdue: Decimal
    open_invoices: int


class Payables(BaseModel):
    total: Decimal
    pending_expenses: int


class FinanceSummaryOut(BaseModel):
    period: Period
    previous_period: Period
    income: Change      # lo que entro (pagos recibidos)
    expenses: Change    # lo que salio (gastos pagados)
    profit: Change      # ingresos - gastos
    invoiced: Change    # lo facturado (aunque no se haya cobrado)
    receivables: Receivables  # pendiente por cobrar (hoy)
    payables: Payables        # pendiente por pagar (hoy)
    message: str


class SeriesPoint(BaseModel):
    label: str
    from_date: date
    to_date: date
    income: Decimal
    expenses: Decimal
    profit: Decimal
    profit_vs_previous: Change


class FinanceSeriesOut(BaseModel):
    group_by: str
    points: list[SeriesPoint]
    best: str | None   # etiqueta del periodo con mas ganancia
    worst: str | None  # etiqueta del periodo con menos ganancia


class CompareBlock(BaseModel):
    period: Period
    previous_period: Period
    income: Change
    expenses: Change
    profit: Change
    message: str


class FinanceCompareOut(BaseModel):
    day: CompareBlock
    week: CompareBlock
    month: CompareBlock


class MethodTotal(BaseModel):
    method: str
    total: Decimal
    count: int
    percent: float


class CategoryTotal(BaseModel):
    category: str
    total: Decimal
    count: int
    percent: float


class AppointmentsReportOut(BaseModel):
    period: Period
    total: Change
    attended: Change
    by_status: dict[str, int]
    cancellation_rate: float
    no_show_rate: float
    new_patients: Change
    patients_attended: int


class DentistActivity(BaseModel):
    dentist_id: int
    dentist_name: str
    appointments: int
    attended: int
    cancelled: int
    no_show: int
    invoiced: Decimal
    collected: Decimal
