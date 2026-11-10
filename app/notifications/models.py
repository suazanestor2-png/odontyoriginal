from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.mixins import AuditMixin


class Notification(Base, AuditMixin):
    """
    Bandeja de notificaciones internas (no es el envio del correo en si, eso lo
    maneja la tarea de 'Recordatorios de citas por correo' por separado).
    'type' es texto libre (no Enum de BD) porque este catalogo va a seguir
    creciendo (recordatorio_cita, proximo_control, pago_pendiente, manual, etc.)
    y no queremos migrar la base cada vez que se agregue un tipo nuevo.
    """
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), index=True)

    # Destinatario: puede ser un paciente o alguien del personal (recepcion, admin, etc.)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    user: Mapped["User"] = relationship(foreign_keys=[user_id])

    type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(150))
    message: Mapped[str] = mapped_column(Text)

    # Referencias opcionales, segun el tipo de aviso
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"), nullable=True, index=True)
    appointment: Mapped["Appointment | None"] = relationship(foreign_keys=[appointment_id])

    patient_id: Mapped[int | None] = mapped_column(ForeignKey("patients.id"), nullable=True, index=True)
    patient: Mapped["Patient | None"] = relationship(foreign_keys=[patient_id])

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)