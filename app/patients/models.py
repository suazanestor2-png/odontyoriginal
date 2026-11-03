from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.mixins import AuditMixin


class Patient(Base, AuditMixin):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    user: Mapped["User"] = relationship(foreign_keys=[user_id])  # noqa: F821

    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), index=True)

    document_type: Mapped[str] = mapped_column(String(2), default="CC")
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    blood_type: Mapped[str | None] = mapped_column(String(3), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    eps: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Responsable (obligatorio si el paciente es menor de edad)
    guardian_full_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    guardian_document_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    guardian_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    guardian_relationship: Mapped[str | None] = mapped_column(String(50), nullable=True)  # padre, madre, tutor...

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