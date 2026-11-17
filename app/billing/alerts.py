from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.models import Invoice
from app.billing.pdf import _cop
from app.core.dates import today_bogota
from app.notifications.service import clinic_staff, notify

TIPO = "pago_pendiente"


def run_overdue_invoice_alerts(db: Session, hoy: date | None = None) -> dict:
    """Avisa a recepcion (o al admin) una vez por cada factura vencida con saldo pendiente."""
    hoy = hoy or today_bogota()
    vencidas = db.scalars(
        select(Invoice).where(
            Invoice.status.in_(("pendiente", "parcial")),
            Invoice.due_date < hoy,
            Invoice.overdue_notified.is_(False),
        )
    ).all()

    for invoice in vencidas:
        patient = invoice.patient
        dias = (hoy - invoice.due_date).days
        destinatarios = clinic_staff(db, invoice.clinic_id, ("recepcionista", "admin"))
        notify(
            db, destinatarios, invoice.clinic_id, TIPO,
            "Pago pendiente vencido",
            f"La factura {invoice.number} de {patient.full_name} tiene un saldo de {_cop(invoice.balance)} "
            f"vencido hace {dias} dia(s). Telefono: {patient.phone_number}",
            patient_id=patient.id,
        )
        invoice.overdue_notified = True

    db.commit()
    return {"pagos_vencidos": len(vencidas)}
