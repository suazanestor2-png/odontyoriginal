from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

METODO_PATTERN = r"^(efectivo|transferencia|tarjeta|nequi|daviplata|otro)$"
CATEGORIA_PATTERN = r"^(materiales|laboratorio|nomina|arriendo|servicios|equipos|impuestos|otros)$"

Monto = Field(gt=0, max_digits=14, decimal_places=2)


# ---------- Configuracion ----------

class BillingSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice_prefix: str
    next_number: int
    payment_terms_days: int
    footer_text: str | None


class BillingSettingsUpdateIn(BaseModel):
    invoice_prefix: str | None = Field(default=None, pattern=r"^[A-Z0-9]{1,10}$")
    next_number: int | None = Field(default=None, ge=1)
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    footer_text: str | None = Field(default=None, max_length=1000)


# ---------- Facturas ----------

class InvoiceItemIn(BaseModel):
    description: str | None = Field(default=None, min_length=3, max_length=300)
    cups_code: str | None = Field(default=None, max_length=6)
    quantity: int = Field(default=1, ge=1, le=1000)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)

    @model_validator(mode="after")
    def _descripcion_o_cups(self):
        if not self.description and not self.cups_code:
            raise ValueError("Cada item necesita description o cups_code")
        return self


class InvoiceCreateIn(BaseModel):
    patient_id: int
    appointment_id: int | None = None
    items: list[InvoiceItemIn] = Field(min_length=1, max_length=50)
    discount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    due_date: date | None = None
    notes: str | None = Field(default=None, max_length=1000)


class InvoiceVoidIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class InvoiceItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    description: str
    cups_code: str | None
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class PaymentIn(BaseModel):
    amount: Decimal = Monto
    method: str = Field(pattern=METODO_PATTERN)
    paid_on: date | None = None
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    amount: Decimal
    method: str
    paid_on: date
    reference: str | None
    notes: str | None
    created_at: datetime
    created_by: int | None


class InvoiceSummaryOut(BaseModel):
    id: int
    number: str
    patient_id: int
    patient_name: str
    appointment_id: int | None
    issue_date: date
    due_date: date
    status: str
    total: Decimal
    paid_amount: Decimal
    balance: Decimal
    is_overdue: bool


class InvoiceOut(InvoiceSummaryOut):
    patient_document: str
    subtotal: Decimal
    discount: Decimal
    notes: str | None
    void_reason: str | None
    voided_at: datetime | None
    created_at: datetime
    created_by: int | None
    items: list[InvoiceItemOut]
    payments: list[PaymentOut]


class PatientStatementOut(BaseModel):
    patient_id: int
    patient_name: str
    total_invoiced: Decimal
    total_paid: Decimal
    balance: Decimal
    open_invoices: int
    invoices: list[InvoiceSummaryOut]


# ---------- Gastos ----------

class ExpenseCreateIn(BaseModel):
    expense_date: date
    category: str = Field(pattern=CATEGORIA_PATTERN)
    description: str = Field(min_length=3, max_length=300)
    supplier: str | None = Field(default=None, max_length=150)
    supplier_invoice: str | None = Field(default=None, max_length=60)
    amount: Decimal = Monto
    # Si ya se pago, enviar paid=true (y opcionalmente paid_on / payment_method)
    paid: bool = False
    paid_on: date | None = None
    payment_method: str | None = Field(default=None, pattern=METODO_PATTERN)
    due_date: date | None = None


class ExpensePayIn(BaseModel):
    paid_on: date | None = None
    payment_method: str = Field(pattern=METODO_PATTERN)


class ExpenseVoidIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    expense_date: date
    category: str
    description: str
    supplier: str | None
    supplier_invoice: str | None
    amount: Decimal
    status: str
    due_date: date | None
    paid_on: date | None
    payment_method: str | None
    void_reason: str | None
    created_at: datetime
    created_by: int | None
