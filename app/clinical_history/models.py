from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.mixins import utcnow


# Historia clinica = el conjunto de ClinicalEntry de un paciente, ordenadas por fecha.
# No existe update ni delete a proposito: es un documento legal, "solo se agrega"
# (Resolucion 1995 de 1999: sin tachones ni enmendaduras). Solo se registra durante la cita
# o hasta 2 horas despues; si el odontologo se equivoca, agrega una nota aclaratoria.
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
    # Diagnostico principal codificado (Res. 866 de 2021). Nullable solo por las consultas
    # registradas antes de existir el campo; las nuevas lo exigen.
    diagnosis_code: Mapped[str | None] = mapped_column(ForeignKey("cie10_codes.code"), nullable=True, index=True)
    diagnosis: Mapped["Cie10Code"] = relationship(foreign_keys=[diagnosis_code])
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

    # ej. historia.listar, historia.ver_entrada, historia.pdf, odontograma.ver, odontograma.historial, alertas.ver
    action: Mapped[str] = mapped_column(String(40))
    resource_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    accessed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class ClinicalNote(Base):
    """
    Nota aclaratoria sobre una consulta o un registro del odontograma ya guardado.
    Lo original nunca se modifica: la correccion queda como una nota nueva con fecha y autor.
    """
    __tablename__ = "clinical_notes"
    __table_args__ = (
        CheckConstraint(
            "(clinical_entry_id IS NOT NULL) <> (odontogram_entry_id IS NOT NULL)",
            name="ck_clinical_notes_un_solo_registro",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    clinical_entry_id: Mapped[int | None] = mapped_column(ForeignKey("clinical_entries.id"), nullable=True, index=True)
    odontogram_entry_id: Mapped[int | None] = mapped_column(ForeignKey("odontogram_entries.id"), nullable=True, index=True)

    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    author: Mapped["User"] = relationship(foreign_keys=[created_by])
