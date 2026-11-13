from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CupsCode(Base):
    """Clasificacion Unica de Procedimientos en Salud (CUPS), Resolucion 2706 de 2025.

    Catalogo oficial de solo lectura: se llena con seed_cups() desde
    app/catalogs/data/cups_2026.csv. Nunca se borra un codigo: si Minsalud
    lo elimina, queda is_active=False para no romper registros historicos.
    """
    __tablename__ = "cups_codes"

    code: Mapped[str] = mapped_column(String(6), primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    section: Mapped[str] = mapped_column(String(120))
    is_dental: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
