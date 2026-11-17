from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.mixins import AuditMixin

# pendiente: todavia no tiene cita, se envian los avisos (7 y 3 dias antes)
# agendado:  ya tiene una cita que lo cubre, no se envian mas avisos
# cancelado: el control ya no aplica
ESTADOS_CONTROL = ("pendiente", "agendado", "cancelado")


class PatientControl(Base, AuditMixin):
    """
    Proximo control de un paciente (ej. "vuelva en 6 meses"). A diferencia de una cita,
    un control todavia NO esta agendado: es una fecha aproximada en la que el paciente
    deberia volver. El cron avisa al paciente (correo) y a la recepcion (campanita)
    para que se agende la cita.
    """
    __tablename__ = "patient_controls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    patient: Mapped["Patient"] = relationship(foreign_keys=[patient_id])  # noqa: F821

    due_date: Mapped[date] = mapped_column(Date, index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pendiente", server_default="pendiente", index=True)

    # Consulta de la historia clinica donde el odontologo lo dejo indicado (si vino de ahi)
    clinical_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("clinical_entries.id"), nullable=True, index=True
    )
    # Cita con la que quedo agendado
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"), nullable=True, index=True)

    reminder_7d_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    reminder_3d_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
