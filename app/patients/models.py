from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import AuditMixin


class Patient(Base, AuditMixin):
    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint("clinic_id", "document_type", "document_number", name="uq_patients_clinic_document"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), index=True)

    # Datos personales: pertenecen solo a esta clinica, no se comparten con otras
    full_name: Mapped[str] = mapped_column(String(150))
    document_type: Mapped[str] = mapped_column(String(2), default="CC")
    document_number: Mapped[str] = mapped_column(String(20), index=True)
    email: Mapped[str] = mapped_column(String(255))
    phone_number: Mapped[str] = mapped_column(String(20))

    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    blood_type: Mapped[str | None] = mapped_column(String(3), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    eps: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Responsable (obligatorio si el paciente es menor de edad)
    guardian_full_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    guardian_document_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    guardian_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    guardian_relationship: Mapped[str | None] = mapped_column(String(50), nullable=True)

    emergency_contact_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    allergies: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def is_minor(self) -> bool:
        if not self.birth_date:
            return False
        today = date.today()
        age = today.year - self.birth_date.year - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))
        return age < 18