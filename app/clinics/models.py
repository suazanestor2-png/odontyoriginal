from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import AuditMixin


class Clinic(Base, AuditMixin):
    __tablename__ = "clinics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    nit: Mapped[str | None] = mapped_column(String(15), unique=True, index=True, nullable=True)
    nit_dv: Mapped[str | None] = mapped_column(String(1), nullable=True)
    # pending_email | pending_review | active | rejected | suspended
    status: Mapped[str] = mapped_column(String(20), default="pending_email", index=True)
    timezone: Mapped[str] = mapped_column(String(50), default="America/Bogota")