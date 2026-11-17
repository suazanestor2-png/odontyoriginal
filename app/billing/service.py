from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.models import BillingSettings, Invoice
from app.billing.schemas import InvoiceOut, InvoiceSummaryOut, PaymentOut, InvoiceItemOut
from app.core.dates import today_bogota

CERO = Decimal("0")


def get_or_create_settings(db: Session, clinic_id: int, lock: bool = False) -> BillingSettings:
    query = select(BillingSettings).where(BillingSettings.clinic_id == clinic_id)
    if lock:
        query = query.with_for_update()
    settings = db.scalar(query)
    if not settings:
        settings = BillingSettings(clinic_id=clinic_id, invoice_prefix="FAC", next_number=1, payment_terms_days=0)
        db.add(settings)
        db.flush()
        if lock:
            settings = db.scalar(query)
    return settings


def next_invoice_number(db: Session, clinic_id: int) -> tuple[int, str, BillingSettings]:
    """Reserva el siguiente consecutivo de la clinica (con bloqueo, para que dos cajas no repitan numero)."""
    settings = get_or_create_settings(db, clinic_id, lock=True)
    seq = settings.next_number
    settings.next_number = seq + 1
    return seq, f"{settings.invoice_prefix}-{seq:04d}", settings


def status_for(total: Decimal, paid: Decimal) -> str:
    if paid <= CERO and total > CERO:
        return "pendiente"
    if paid < total:
        return "parcial"
    return "pagada"


def is_overdue(invoice: Invoice, hoy: date | None = None) -> bool:
    hoy = hoy or today_bogota()
    return invoice.status in ("pendiente", "parcial") and invoice.due_date < hoy


def invoice_summary(invoice: Invoice) -> InvoiceSummaryOut:
    return InvoiceSummaryOut(
        id=invoice.id,
        number=invoice.number,
        patient_id=invoice.patient_id,
        patient_name=invoice.patient.full_name,
        appointment_id=invoice.appointment_id,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        status=invoice.status,
        total=invoice.total,
        paid_amount=invoice.paid_amount,
        balance=invoice.balance,
        is_overdue=is_overdue(invoice),
    )


def invoice_detail(invoice: Invoice) -> InvoiceOut:
    base = invoice_summary(invoice).model_dump()
    return InvoiceOut(
        **base,
        patient_document=f"{invoice.patient.document_type} {invoice.patient.document_number}",
        subtotal=invoice.subtotal,
        discount=invoice.discount,
        notes=invoice.notes,
        void_reason=invoice.void_reason,
        voided_at=invoice.voided_at,
        created_at=invoice.created_at,
        created_by=invoice.created_by,
        items=[InvoiceItemOut.model_validate(i) for i in invoice.items],
        payments=[PaymentOut.model_validate(p) for p in invoice.payments],
    )


def get_invoice_for_actor(db: Session, invoice_id: int, actor, lock: bool = False) -> Invoice:
    query = select(Invoice).where(Invoice.id == invoice_id)
    if lock:
        query = query.with_for_update()
    invoice = db.scalar(query)
    if not invoice or (actor.role.name != "super_admin" and invoice.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Factura no encontrada")
    return invoice


def default_due_date(settings: BillingSettings, issue_date: date) -> date:
    return issue_date + timedelta(days=settings.payment_terms_days or 0)
