import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.catalogs.models import CupsCode
from app.catalogs.schemas import CupsOut
from app.core.database import get_db
from app.core.deps import get_active_user
from app.identity.models import User

router = APIRouter(prefix="/catalogs", tags=["Catalogos"])

_CODIGO_RE = re.compile(r"^[0-9A-Z]{1,6}$")


def _normalizar(texto: str) -> str:
    """'Obturación' -> 'OBTURACION' (la CUPS viene en mayusculas y sin tildes)."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.upper().strip()


@router.get("/cups", response_model=list[CupsOut])
def search_cups(
    q: str = Query(min_length=2, max_length=100, description="Codigo (ej. 2321) o palabras (ej. resina)"),
    dental_only: bool = Query(True, description="Solo procedimientos odontologicos"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    actor: User = Depends(get_active_user),
):
    texto = _normalizar(q)
    stmt = select(CupsCode).where(CupsCode.is_active)
    if dental_only:
        stmt = stmt.where(CupsCode.is_dental)

    if _CODIGO_RE.match(texto) and any(c.isdigit() for c in texto):
        # Escribio un codigo: los que empiezan por esos digitos
        stmt = stmt.where(CupsCode.code.startswith(texto))
    else:
        # Escribio palabras: todas deben aparecer en el nombre, en cualquier orden
        palabras = [p for p in texto.split() if p]
        stmt = stmt.where(and_(*[CupsCode.name.contains(p) for p in palabras]))

    stmt = stmt.order_by(CupsCode.is_dental.desc(), CupsCode.code).limit(limit)
    return db.scalars(stmt).all()


@router.get("/cups/{code}", response_model=CupsOut)
def get_cups(
    code: str,
    db: Session = Depends(get_db),
    actor: User = Depends(get_active_user),
):
    cups = db.get(CupsCode, code.strip().upper())
    if not cups:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Codigo CUPS no encontrado")
    return cups
