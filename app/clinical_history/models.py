from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.mixins import utcnow


# Historia clinica = el conjunto de ClinicalEntry de un paciente, ordenadas por fecha.
# No existe update ni delete a proposito: es un documento legal, "solo se agrega".
# Si el odontologo se equivoca, registra una entrada nueva en vez de editar la anterior.
class ClinicalEntry(Base):
    __tablename__ = "clinical_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"), unique=True, index=True)
    dentist_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    patient: Mapped["Patient"] = relationship(foreign_keys=[patient_id])
    appointment: Mapped["Appointment"] = relationship(foreign_keys=[appointment_id])
    dentist: Mapped["User"] = relationship(foreign_keys=[dentist_id])

    antecedentes: Mapped[str | None] = mapped_column(Text, nullable=True)
    motivo_consulta: Mapped[str] = mapped_column(Text)
    examen: Mapped[str] = mapped_column(Text)
    diagnostico: Mapped[str] = mapped_column(Text)
    tratamiento: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)