from datetime import date, time

from sqlalchemy import Date, ForeignKey, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.mixins import AuditMixin

ESTADOS = ("programada", "confirmada", "atendida", "cancelada", "no_asistio")
ORIGENES = ("presencial", "llamada", "whatsapp")


class Appointment(Base, AuditMixin):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)

    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    dentist_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    patient: Mapped["Patient"] = relationship(foreign_keys=[patient_id])  # noqa: F821
    dentist: Mapped["User"] = relationship(foreign_keys=[dentist_id])  # noqa: F821

    scheduled_date: Mapped[date] = mapped_column(Date, index=True)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)

    reason: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(20), default="presencial")
    status: Mapped[str] = mapped_column(String(20), default="programada", index=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)