from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.mixins import AuditMixin

METODOS_FIRMA = ("firma_fisica", "firma_digital", "verbal")


class PrivacyPolicy(Base, AuditMixin):
    """
    Politica de tratamiento de datos de la clinica (Ley 1581 de 2012). Tiene versiones: cuando
    la clinica la cambia, se crea una version nueva y las autorizaciones anteriores quedan
    asociadas al texto que el paciente realmente acepto.
    """
    __tablename__ = "privacy_policies"
    __table_args__ = (UniqueConstraint("clinic_id", "version", name="uq_privacy_policy_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), index=True)
    version: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class PatientConsent(Base, AuditMixin):
    """
    Autorizacion del paciente (o de su acudiente si es menor) para el tratamiento de sus datos.
    Es prueba legal: no se edita ni se borra. Si el paciente la revoca, queda la fecha y el motivo.
    created_by = quien la registro.
    """
    __tablename__ = "patient_consents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    patient: Mapped["Patient"] = relationship(foreign_keys=[patient_id])  # noqa: F821
    policy_id: Mapped[int] = mapped_column(ForeignKey("privacy_policies.id"))
    policy: Mapped["PrivacyPolicy"] = relationship(foreign_keys=[policy_id])

    method: Mapped[str] = mapped_column(String(20))
    accepted_at: Mapped[datetime] = mapped_column(DateTime)

    # Quien firma: el paciente, o su acudiente si es menor de edad
    signer_name: Mapped[str] = mapped_column(String(150))
    signer_document: Mapped[str] = mapped_column(String(20))
    signer_relationship: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Soportes opcionales
    evidence_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    revoked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
