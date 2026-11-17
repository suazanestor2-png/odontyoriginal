from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
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


class ClinicalAccessLog(Base):
    """
    Quien consulto la informacion clinica de un paciente y cuando (historia clinica, odontograma
    y alertas medicas). Solo se agrega, nunca se edita ni se borra.
    """
    __tablename__ = "clinical_access_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    patient: Mapped["Patient"] = relationship(foreign_keys=[patient_id])
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    user: Mapped["User"] = relationship(foreign_keys=[user_id])

    # ej. historia.listar, historia.ver_entrada, odontograma.ver, odontograma.historial, alertas.ver
    action: Mapped[str] = mapped_column(String(40))
    resource_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    accessed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
