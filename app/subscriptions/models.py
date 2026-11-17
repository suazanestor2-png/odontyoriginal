from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.mixins import AuditMixin


class SubscriptionPlan(Base, AuditMixin):
    """Planes que Odonty vende a las clinicas (mensual, anual). El precio lo ajusta el super_admin."""
    __tablename__ = "subscription_plans"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    months: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class ClinicSubscription(Base, AuditMixin):
    """Suscripcion vigente de una clinica (una por clinica). El historial de pagos esta en SubscriptionRenewal."""
    __tablename__ = "clinic_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), unique=True, index=True)
    clinic: Mapped["Clinic"] = relationship(foreign_keys=[clinic_id])  # noqa: F821

    plan_code: Mapped[str | None] = mapped_column(ForeignKey("subscription_plans.code"), nullable=True)
    is_trial: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    current_period_start: Mapped[date] = mapped_column(Date)
    current_period_end: Mapped[date] = mapped_column(Date, index=True)  # ultimo dia pagado (incluido)

    # Avisos ya enviados en el periodo actual (se reinician al renovar)
    alert_7d_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    alert_3d_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    alert_1d_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    alert_grace_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    alert_readonly_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class SubscriptionRenewal(Base, AuditMixin):
    """Cada pago/renovacion registrado por el super_admin (created_by)."""
    __tablename__ = "subscription_renewals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), index=True)
    plan_code: Mapped[str] = mapped_column(ForeignKey("subscription_plans.code"))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    paid_on: Mapped[date] = mapped_column(Date)
    method: Mapped[str] = mapped_column(String(20))
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
