from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.mixins import AuditMixin

ESTADOS_FACTURA = ("pendiente", "parcial", "pagada", "anulada")
METODOS_PAGO = ("efectivo", "transferencia", "tarjeta", "nequi", "daviplata", "otro")
CATEGORIAS_GASTO = ("materiales", "laboratorio", "nomina", "arriendo", "servicios", "equipos", "impuestos", "otros")
ESTADOS_GASTO = ("pendiente", "pagado", "anulado")

Dinero = Numeric(14, 2)


class BillingSettings(Base, AuditMixin):
    """Numeracion y datos que salen en las facturas de cada clinica."""
    __tablename__ = "billing_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), unique=True, index=True)

    invoice_prefix: Mapped[str] = mapped_column(String(10), default="FAC", server_default="FAC")
    next_number: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # Dias de plazo para pagar (0 = de contado). La fecha de vencimiento se calcula con esto.
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Texto al pie de la factura (ej. "Servicios de salud excluidos de IVA, art. 476 E.T.")
    footer_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class Invoice(Base, AuditMixin):
    """
    Factura emitida a un paciente. Una vez creada NO se edita (ni items ni valores):
    solo cambia su estado por los pagos o porque se anula. Cada movimiento queda en auditoria.
    """
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("clinic_id", "number_seq", name="uq_invoices_clinic_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), index=True)

    number_seq: Mapped[int] = mapped_column(Integer)
    number: Mapped[str] = mapped_column(String(30), index=True)  # ej. FAC-0007

    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    patient: Mapped["Patient"] = relationship(foreign_keys=[patient_id])  # noqa: F821
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"), nullable=True, index=True)
    appointment: Mapped["Appointment | None"] = relationship(foreign_keys=[appointment_id])  # noqa: F821

    issue_date: Mapped[date] = mapped_column(Date, index=True)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pendiente", index=True)

    subtotal: Mapped[Decimal] = mapped_column(Dinero)
    discount: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Dinero)
    paid_amount: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0"))

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    voided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Aviso de "pago pendiente vencido" ya enviado a recepcion
    overdue_notified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    items: Mapped[list["InvoiceItem"]] = relationship(
        back_populates="invoice", order_by="InvoiceItem.id", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice", order_by="Payment.id")

    @property
    def balance(self) -> Decimal:
        if self.status == "anulada":
            return Decimal("0")
        return self.total - self.paid_amount


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    invoice: Mapped["Invoice"] = relationship(back_populates="items")

    description: Mapped[str] = mapped_column(String(300))
    cups_code: Mapped[str | None] = mapped_column(ForeignKey("cups_codes.code"), nullable=True, index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Dinero)
    line_total: Mapped[Decimal] = mapped_column(Dinero)


class Payment(Base, AuditMixin):
    """Pago o abono a una factura. No se edita ni se borra (created_by = quien lo recibio)."""
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    invoice: Mapped["Invoice"] = relationship(back_populates="payments")

    amount: Mapped[Decimal] = mapped_column(Dinero)
    method: Mapped[str] = mapped_column(String(20), index=True)
    paid_on: Mapped[date] = mapped_column(Date, index=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Expense(Base, AuditMixin):
    """Gasto de la clinica (lo que 'sale'). Sirve para calcular gastos y ganancias."""
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), index=True)

    expense_date: Mapped[date] = mapped_column(Date, index=True)
    category: Mapped[str] = mapped_column(String(30), index=True)
    description: Mapped[str] = mapped_column(String(300))
    supplier: Mapped[str | None] = mapped_column(String(150), nullable=True)
    supplier_invoice: Mapped[str | None] = mapped_column(String(60), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Dinero)

    status: Mapped[str] = mapped_column(String(20), default="pendiente", index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    payment_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
