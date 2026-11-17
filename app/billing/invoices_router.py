from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.appointments.models import Appointment
from app.billing.models import Invoice, InvoiceItem, Payment
from app.billing.pdf import render_invoice_pdf
from app.billing.schemas import (
    InvoiceCreateIn, InvoiceOut, InvoiceSummaryOut, InvoiceVoidIn, PatientStatementOut, PaymentIn,
)
from app.billing.service import (
    CERO, default_due_date, get_invoice_for_actor, get_or_create_settings, invoice_detail,
    invoice_summary, next_invoice_number, status_for,
)
from app.catalogs.models import CupsCode
from app.clinics.models import Clinic
from app.core.database import get_db
from app.core.dates import today_bogota
from app.core.deps import require_permission
from app.identity.audit import log_event
from app.identity.models import User
from app.patients.models import Patient

router = APIRouter(prefix="/invoices", tags=["Facturacion"])


def _patient_of_clinic(db: Session, patient_id: int, actor: User) -> Patient:
    patient = db.get(Patient, patient_id)
    if not patient or (actor.role.name != "super_admin" and patient.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    return patient


@router.post("", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def create_invoice(
    data: InvoiceCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("billing.create")),
):
    patient = _patient_of_clinic(db, data.patient_id, actor)

    if data.appointment_id is not None:
        appt = db.get(Appointment, data.appointment_id)
        if not appt or appt.clinic_id != patient.clinic_id or appt.patient_id != patient.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "La cita no corresponde a este paciente")

    items: list[InvoiceItem] = []
    subtotal = CERO
    for item in data.items:
        description = item.description
        cups_code = None
        if item.cups_code:
            cups = db.get(CupsCode, item.cups_code.strip().upper())
            if not cups or not cups.is_active:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El codigo CUPS {item.cups_code} no existe o no esta vigente")
            cups_code = cups.code
            description = description or cups.name[:300]
        line_total = item.unit_price * item.quantity
        subtotal += line_total
        items.append(InvoiceItem(
            description=description.strip(), cups_code=cups_code, quantity=item.quantity,
            unit_price=item.unit_price, line_total=line_total,
        ))

    if data.discount > subtotal:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El descuento no puede ser mayor que el subtotal")
    total = subtotal - data.discount

    hoy = today_bogota()
    seq, number, settings = next_invoice_number(db, patient.clinic_id)
    due_date = data.due_date or default_due_date(settings, hoy)
    if due_date < hoy:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La fecha de vencimiento no puede ser anterior a hoy")

    invoice = Invoice(
        clinic_id=patient.clinic_id,
        number_seq=seq,
        number=number,
        patient_id=patient.id,
        appointment_id=data.appointment_id,
        issue_date=hoy,
        due_date=due_date,
        subtotal=subtotal,
        discount=data.discount,
        total=total,
        paid_amount=CERO,
        status=status_for(total, CERO),
        notes=data.notes,
        created_by=actor.id,
        items=items,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    log_event(db, "INVOICE_CREATED", actor.id, f"invoice={invoice.id} number={invoice.number} total={invoice.total}")
    return invoice_detail(invoice)


@router.get("", response_model=list[InvoiceSummaryOut])
def list_invoices(
    response: Response,
    patient_id: int | None = Query(None),
    status_filter: str | None = Query(None, alias="status", pattern=r"^(pendiente|parcial|pagada|anulada)$"),
    overdue: bool | None = Query(None, description="true = solo las vencidas con saldo"),
    from_date: date | None = Query(None, description="Fecha de emision desde"),
    to_date: date | None = Query(None, description="Fecha de emision hasta"),
    q: str | None = Query(None, max_length=50, description="Numero de factura o nombre/documento del paciente"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("billing.view")),
):
    query = select(Invoice).join(Patient, Invoice.patient_id == Patient.id)
    if actor.role.name != "super_admin":
        query = query.where(Invoice.clinic_id == actor.clinic_id)
    if patient_id:
        query = query.where(Invoice.patient_id == patient_id)
    if status_filter:
        query = query.where(Invoice.status == status_filter)
    if overdue:
        query = query.where(Invoice.status.in_(("pendiente", "parcial")), Invoice.due_date < today_bogota())
    if from_date:
        query = query.where(Invoice.issue_date >= from_date)
    if to_date:
        query = query.where(Invoice.issue_date <= to_date)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Invoice.number.ilike(like), Patient.full_name.ilike(like), Patient.document_number.ilike(like)))

    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    items = db.scalars(query.order_by(Invoice.issue_date.desc(), Invoice.id.desc()).limit(limit).offset(offset)).all()
    response.headers["X-Total-Count"] = str(total)
    return [invoice_summary(i) for i in items]


@router.get("/patients/{patient_id}/statement", response_model=PatientStatementOut)
def patient_statement(
    patient_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("billing.view")),
):
    """Estado de cuenta del paciente: lo facturado, lo pagado y lo que debe."""
    patient = _patient_of_clinic(db, patient_id, actor)
    invoices = db.scalars(
        select(Invoice).where(Invoice.patient_id == patient.id).order_by(Invoice.issue_date.desc(), Invoice.id.desc())
    ).all()
    validas = [i for i in invoices if i.status != "anulada"]
    return PatientStatementOut(
        patient_id=patient.id,
        patient_name=patient.full_name,
        total_invoiced=sum((i.total for i in validas), CERO),
        total_paid=sum((i.paid_amount for i in validas), CERO),
        balance=sum((i.balance for i in validas), CERO),
        open_invoices=sum(1 for i in validas if i.status in ("pendiente", "parcial")),
        invoices=[invoice_summary(i) for i in invoices],
    )


@router.get("/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("billing.view")),
):
    return invoice_detail(get_invoice_for_actor(db, invoice_id, actor))


@router.get("/{invoice_id}/pdf")
def get_invoice_pdf(
    invoice_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("billing.view")),
):
    invoice = get_invoice_for_actor(db, invoice_id, actor)
    clinic = db.get(Clinic, invoice.clinic_id)
    settings = get_or_create_settings(db, invoice.clinic_id)
    pdf_bytes = render_invoice_pdf(invoice, clinic, settings)
    log_event(db, "INVOICE_PDF_DOWNLOADED", actor.id, f"invoice={invoice.id}")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice.number}.pdf"'},
    )


@router.post("/{invoice_id}/payments", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def register_payment(
    invoice_id: int,
    data: PaymentIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("billing.create")),
):
    """Registra un pago total o un abono. Bloquea la factura para que dos pagos simultaneos no se pasen del total."""
    invoice = get_invoice_for_actor(db, invoice_id, actor, lock=True)
    if invoice.status == "anulada":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No se pueden registrar pagos en una factura anulada")
    if invoice.status == "pagada":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La factura ya esta pagada")

    saldo = invoice.total - invoice.paid_amount
    if data.amount > saldo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El pago supera el saldo pendiente ({saldo})")

    hoy = today_bogota()
    paid_on = data.paid_on or hoy
    if paid_on > hoy:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La fecha del pago no puede ser futura")

    db.add(Payment(
        clinic_id=invoice.clinic_id, invoice_id=invoice.id, amount=data.amount, method=data.method,
        paid_on=paid_on, reference=data.reference, notes=data.notes, created_by=actor.id,
    ))
    invoice.paid_amount = invoice.paid_amount + data.amount
    invoice.status = status_for(invoice.total, invoice.paid_amount)
    db.commit()
    db.refresh(invoice)
    log_event(db, "PAYMENT_REGISTERED", actor.id,
              f"invoice={invoice.id} amount={data.amount} method={data.method} status={invoice.status}")
    return invoice_detail(invoice)


@router.post("/{invoice_id}/void", response_model=InvoiceOut)
def void_invoice(
    invoice_id: int,
    data: InvoiceVoidIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("billing.void")),
):
    """Anula una factura (no se borra). Solo si no tiene pagos registrados."""
    invoice = get_invoice_for_actor(db, invoice_id, actor, lock=True)
    if invoice.status == "anulada":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La factura ya esta anulada")
    if invoice.paid_amount > CERO:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "La factura tiene pagos registrados y no se puede anular",
        )

    invoice.status = "anulada"
    invoice.void_reason = data.reason.strip()
    invoice.voided_at = datetime.now(timezone.utc).replace(tzinfo=None)
    invoice.voided_by = actor.id
    db.commit()
    db.refresh(invoice)
    log_event(db, "INVOICE_VOIDED", actor.id, f"invoice={invoice.id} number={invoice.number}")
    return invoice_detail(invoice)
