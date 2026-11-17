from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    months: int
    price: Decimal
    is_active: bool


class PlanUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=60)
    price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    is_active: bool | None = None


class SubscriptionStatusOut(BaseModel):
    clinic_id: int
    clinic_name: str
    plan_code: str | None
    plan_name: str | None
    is_trial: bool
    current_period_start: date
    current_period_end: date
    # activa | por_vencer | en_gracia | solo_lectura
    status: str
    days_left: int            # dias hasta el vencimiento (negativo si ya vencio)
    grace_days_left: int      # dias de gracia que quedan (0 si no esta en gracia)
    read_only: bool
    message: str


class RenewIn(BaseModel):
    plan_code: str = Field(pattern=r"^[a-z_]{3,20}$")
    amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)  # por defecto, el precio del plan
    paid_on: date | None = None
    method: str = Field(pattern=r"^(efectivo|transferencia|tarjeta|nequi|daviplata|otro)$")
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)


class RenewalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clinic_id: int
    plan_code: str
    amount: Decimal
    period_start: date
    period_end: date
    paid_on: date
    method: str
    reference: str | None
    notes: str | None
    created_at: datetime
    created_by: int | None
