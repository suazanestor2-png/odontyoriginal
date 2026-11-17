from sqlalchemy import Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import AuditMixin
from datetime import time


class Clinic(Base, AuditMixin):
    __tablename__ = "clinics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    nit: Mapped[str | None] = mapped_column(String(15), unique=True, index=True, nullable=True)
    nit_dv: Mapped[str | None] = mapped_column(String(1), nullable=True)
    # pending_email | pending_review | active | rejected | suspended
    status: Mapped[str] = mapped_column(String(20), default="pending_email", index=True)
    timezone: Mapped[str] = mapped_column(String(50), default="America/Bogota")
    cedula_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rut_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    camara_comercio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # dentro de la clase Clinic:
    opening_time: Mapped[time] = mapped_column(Time, default=time(8, 0))
    closing_time: Mapped[time] = mapped_column(Time, default=time(18, 0))
    # dias de atencion: 1=lunes ... 7=domingo, separados por coma. Ej: "1,2,3,4,5,6"
    working_days: Mapped[str] = mapped_column(String(20), default="1,2,3,4,5,6")
    # Duracion por defecto de una cita (si al crearla no se envia hora de fin)
    default_appointment_minutes: Mapped[int] = mapped_column(Integer, default=30, server_default="30")

    # Recordatorios (0 = desactivado). Citas: horas antes; controles: dias antes.
    appointment_reminder_first_hours: Mapped[int] = mapped_column(Integer, default=24, server_default="24")
    appointment_reminder_second_hours: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    control_reminder_first_days: Mapped[int] = mapped_column(Integer, default=7, server_default="7")
    control_reminder_second_days: Mapped[int] = mapped_column(Integer, default=3, server_default="3")

    # Datos de contacto (salen en la factura PDF)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)