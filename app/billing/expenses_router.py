from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.billing.models import Expense
from app.billing.schemas import ExpenseCreateIn, ExpenseOut, ExpensePayIn, ExpenseVoidIn
from app.core.database import get_db
from app.core.dates import today_bogota
from app.core.deps import require_permission
from app.identity.audit import log_event
from app.identity.models import User

router = APIRouter(prefix="/expenses", tags=["Gastos"])


def _get_expense(db: Session, expense_id: int, actor: User) -> Expense:
    expense = db.get(Expense, expense_id)
    if not expense or (actor.role.name != "super_admin" and expense.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gasto no encontrado")
    return expense


@router.post("", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
def create_expense(
    data: ExpenseCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("expenses.manage")),
):
    if not actor.clinic_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tu usuario no pertenece a ninguna clinica")
    hoy = today_bogota()
    if data.expense_date > hoy:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La fecha del gasto no puede ser futura")

    expense = Expense(
        clinic_id=actor.clinic_id,
        expense_date=data.expense_date,
        category=data.category,
        description=data.description.strip(),
        supplier=data.supplier,
        supplier_invoice=data.supplier_invoice,
        amount=data.amount,
        due_date=data.due_date,
        created_by=actor.id,
    )
    if data.paid:
        if not data.payment_method:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Si el gasto ya esta pagado indica payment_method")
        expense.status = "pagado"
        expense.paid_on = data.paid_on or data.expense_date
        expense.payment_method = data.payment_method
        if expense.paid_on > hoy:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "La fecha de pago no puede ser futura")
    else:
        expense.status = "pendiente"

    db.add(expense)
    db.commit()
    db.refresh(expense)
    log_event(db, "EXPENSE_CREATED", actor.id, f"expense={expense.id} amount={expense.amount} status={expense.status}")
    return expense


@router.get("", response_model=list[ExpenseOut])
def list_expenses(
    response: Response,
    status_filter: str | None = Query(None, alias="status", pattern=r"^(pendiente|pagado|anulado)$"),
    category: str | None = Query(None),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("expenses.manage")),
):
    query = select(Expense)
    if actor.role.name != "super_admin":
        query = query.where(Expense.clinic_id == actor.clinic_id)
    if status_filter:
        query = query.where(Expense.status == status_filter)
    if category:
        query = query.where(Expense.category == category)
    if from_date:
        query = query.where(Expense.expense_date >= from_date)
    if to_date:
        query = query.where(Expense.expense_date <= to_date)

    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    items = db.scalars(query.order_by(Expense.expense_date.desc(), Expense.id.desc()).limit(limit).offset(offset)).all()
    response.headers["X-Total-Count"] = str(total)
    return items


@router.get("/{expense_id}", response_model=ExpenseOut)
def get_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("expenses.manage")),
):
    return _get_expense(db, expense_id, actor)


@router.post("/{expense_id}/pay", response_model=ExpenseOut)
def pay_expense(
    expense_id: int,
    data: ExpensePayIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("expenses.manage")),
):
    expense = _get_expense(db, expense_id, actor)
    if expense.status != "pendiente":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Solo se puede pagar un gasto pendiente")
    paid_on = data.paid_on or today_bogota()
    if paid_on > today_bogota():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La fecha de pago no puede ser futura")

    expense.status = "pagado"
    expense.paid_on = paid_on
    expense.payment_method = data.payment_method
    db.commit()
    db.refresh(expense)
    log_event(db, "EXPENSE_PAID", actor.id, f"expense={expense.id}")
    return expense


@router.post("/{expense_id}/void", response_model=ExpenseOut)
def void_expense(
    expense_id: int,
    data: ExpenseVoidIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("expenses.manage")),
):
    """Anula un gasto registrado por error (no se borra, queda en el historial)."""
    expense = _get_expense(db, expense_id, actor)
    if expense.status == "anulado":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El gasto ya esta anulado")
    expense.status = "anulado"
    expense.void_reason = data.reason.strip()
    db.commit()
    db.refresh(expense)
    log_event(db, "EXPENSE_VOIDED", actor.id, f"expense={expense.id}")
    return expense
