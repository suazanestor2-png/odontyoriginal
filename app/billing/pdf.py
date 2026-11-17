from decimal import Decimal

from fpdf import FPDF

from app.billing.models import BillingSettings, Invoice
from app.clinics.models import Clinic

ESTADOS = {"pendiente": "PENDIENTE", "parcial": "ABONO PARCIAL", "pagada": "PAGADA", "anulada": "ANULADA"}


def _cop(valor: Decimal) -> str:
    """1234567.5 -> '$ 1.234.568' (pesos colombianos, sin decimales)."""
    entero = int(Decimal(valor).quantize(Decimal("1")))
    return "$ " + f"{entero:,}".replace(",", ".")


def _txt(texto: str | None) -> str:
    # Las fuentes base del PDF son latin-1: se reemplaza lo que no se pueda representar
    return (texto or "").encode("latin-1", "replace").decode("latin-1")


def render_invoice_pdf(invoice: Invoice, clinic: Clinic, settings: BillingSettings) -> bytes:
    pdf = FPDF(format="Letter")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # Encabezado de la clinica
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, _txt(clinic.name), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    if clinic.nit:
        pdf.cell(0, 5, _txt(f"NIT {clinic.nit}-{clinic.nit_dv or ''}"), new_x="LMARGIN", new_y="NEXT")
    for dato in (getattr(clinic, "address", None), getattr(clinic, "city", None),
                 getattr(clinic, "phone", None), getattr(clinic, "email", None)):
        if dato:
            pdf.cell(0, 5, _txt(dato), new_x="LMARGIN", new_y="NEXT")

    # Numero y estado
    pdf.set_xy(130, 12)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(70, 8, _txt(f"Factura {invoice.number}"), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(130)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(70, 5, _txt(f"Emision: {invoice.issue_date.strftime('%d/%m/%Y')}"), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(130)
    pdf.cell(70, 5, _txt(f"Vence: {invoice.due_date.strftime('%d/%m/%Y')}"), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(130)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(70, 5, ESTADOS.get(invoice.status, invoice.status.upper()), align="R", new_x="LMARGIN", new_y="NEXT")

    # Paciente
    pdf.ln(8)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "Paciente", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    p = invoice.patient
    pdf.cell(0, 5, _txt(f"{p.full_name}  -  {p.document_type} {p.document_number}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, _txt(f"Tel. {p.phone_number}   {p.email}"), new_x="LMARGIN", new_y="NEXT")

    # Items
    pdf.ln(5)
    anchos = (22, 92, 16, 30, 30)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(238, 242, 255)
    for ancho, titulo in zip(anchos, ("CUPS", "Descripcion", "Cant.", "Valor unit.", "Total")):
        pdf.cell(ancho, 7, titulo, border=1, fill=True, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for item in invoice.items:
        descripcion = _txt(item.description)
        if len(descripcion) > 55:
            descripcion = descripcion[:52] + "..."
        pdf.cell(anchos[0], 6, item.cups_code or "", border=1)
        pdf.cell(anchos[1], 6, descripcion, border=1)
        pdf.cell(anchos[2], 6, str(item.quantity), border=1, align="C")
        pdf.cell(anchos[3], 6, _cop(item.unit_price), border=1, align="R")
        pdf.cell(anchos[4], 6, _cop(item.line_total), border=1, align="R")
        pdf.ln()

    # Totales
    pdf.ln(3)
    for etiqueta, valor, negrita in (
        ("Subtotal", invoice.subtotal, False),
        ("Descuento", invoice.discount, False),
        ("Total", invoice.total, True),
        ("Pagado", invoice.paid_amount, False),
        ("Saldo", invoice.balance, True),
    ):
        pdf.set_x(120)
        pdf.set_font("Helvetica", "B" if negrita else "", 10)
        pdf.cell(40, 6, etiqueta, align="R")
        pdf.cell(40, 6, _cop(valor), align="R", new_x="LMARGIN", new_y="NEXT")

    if invoice.status == "anulada":
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(200, 30, 30)
        pdf.multi_cell(0, 6, _txt(f"FACTURA ANULADA. Motivo: {invoice.void_reason}"))
        pdf.set_text_color(0, 0, 0)

    if invoice.notes:
        pdf.ln(3)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, _txt(f"Notas: {invoice.notes}"))

    if settings.footer_text:
        pdf.ln(6)
        pdf.set_font("Helvetica", "I", 8)
        pdf.multi_cell(0, 4, _txt(settings.footer_text))

    return bytes(pdf.output())
