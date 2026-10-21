from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AuditMixin:
    """Columnas de auditoria comunes a (casi) todas las tablas."""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    @declared_attr
    def created_by(cls) -> Mapped[int | None]:
        return mapped_column(
            ForeignKey("users.id", use_alter=True, name=f"fk_{cls.__tablename__}_created_by"),
            nullable=True,
        )

    @declared_attr
    def updated_by(cls) -> Mapped[int | None]:
        return mapped_column(
            ForeignKey("users.id", use_alter=True, name=f"fk_{cls.__tablename__}_updated_by"),
            nullable=True,
        )