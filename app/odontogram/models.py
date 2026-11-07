from enum import Enum as PyEnum

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.mixins import AuditMixin


# Numeracion FDI (ISO 3950) acordada con el frontend: 32 permanentes + 20 temporales
PERMANENT_TEETH = [
    11, 12, 13, 14, 15, 16, 17, 18,
    21, 22, 23, 24, 25, 26, 27, 28,
    31, 32, 33, 34, 35, 36, 37, 38,
    41, 42, 43, 44, 45, 46, 47, 48,
]

TEMPORARY_TEETH = [
    51, 52, 53, 54, 55,
    61, 62, 63, 64, 65,
    71, 72, 73, 74, 75,
    81, 82, 83, 84, 85,
]

VALID_FDI_CODES = sorted(set(PERMANENT_TEETH) | set(TEMPORARY_TEETH))
_fdi_in_clause = ", ".join(str(c) for c in VALID_FDI_CODES)


class ToothSurface(str, PyEnum):
    VESTIBULAR = "vestibular"
    LINGUAL_PALATINO = "lingual_palatino"
    MESIAL = "mesial"
    DISTAL = "distal"
    OCLUSAL = "oclusal"


class DentalCondition(Base, AuditMixin):
    """Catalogo de estados clinicos (caries, ausente, obturado, corona, sano, etc.)."""
    __tablename__ = "dental_conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)


class DentalProcedure(Base, AuditMixin):
    """Catalogo de tratamientos/procedimientos (extraccion, resina, endodoncia, etc.)."""
    __tablename__ = "dental_procedures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)


class OdontogramEntry(Base, AuditMixin):
    """
    Registro historico e inmutable por diente/superficie (igual que ClinicalEntry).
    El estado 'actual' de una pieza = la entrada mas reciente para
    (patient_id, tooth_fdi, surface). No se borra ni se actualiza, solo se inserta.
    """
    __tablename__ = "odontogram_entries"
    __table_args__ = (
        CheckConstraint(f"tooth_fdi IN ({_fdi_in_clause})", name="ck_odontogram_valid_fdi"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), index=True)

    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    patient: Mapped["Patient"] = relationship(foreign_keys=[patient_id])

    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"), index=True)
    appointment: Mapped["Appointment"] = relationship(foreign_keys=[appointment_id])

    # dentist_id es el odontologo duenio de la cita (igual que en ClinicalEntry).
    # created_by (de AuditMixin) es quien tipeo el registro; normalmente la misma
    # persona, pero se manejan separados por si un auxiliar/admin lo registra.
    dentist_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    dentist: Mapped["User"] = relationship(foreign_keys=[dentist_id])

    tooth_fdi: Mapped[int] = mapped_column(Integer, index=True)
    surface: Mapped[ToothSurface | None] = mapped_column(
        Enum(ToothSurface, name="tooth_surface"), nullable=True
    )  # null = aplica a todo el diente

    condition_id: Mapped[int | None] = mapped_column(ForeignKey("dental_conditions.id"), nullable=True, index=True)
    condition: Mapped["DentalCondition | None"] = relationship(foreign_keys=[condition_id])

    procedure_id: Mapped[int | None] = mapped_column(ForeignKey("dental_procedures.id"), nullable=True, index=True)
    procedure: Mapped["DentalProcedure | None"] = relationship(foreign_keys=[procedure_id])

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)