"""Logica de busqueda en el catalogo CUPS."""
import re
import unicodedata

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.catalogs.models import Cie10Code, CupsCode

_CODIGO_RE = re.compile(r"^[0-9A-Z]{1,6}$")


def normalizar(texto: str) -> str:
    """'Obturación' -> 'OBTURACION' (la CUPS viene en mayusculas y sin tildes)."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.upper().strip()


def buscar_cups(db: Session, q: str, dental_only: bool, limit: int) -> list[CupsCode]:
    texto = normalizar(q)
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


def obtener_cups(db: Session, code: str) -> CupsCode:
    cups = db.get(CupsCode, code.strip().upper())
    if not cups:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Codigo CUPS no encontrado")
    return cups


def buscar_cie10(db: Session, q: str, dental_only: bool, limit: int) -> list[Cie10Code]:
    texto = normalizar(q)
    stmt = select(Cie10Code).where(Cie10Code.is_active)
    if dental_only:
        stmt = stmt.where(Cie10Code.is_dental)
    codigo = texto.replace(".", "")
    if re.match(r"^[A-Z][0-9]{1,3}$", codigo):
        # Escribio un codigo (ej. K02 o K02.1): los que empiezan asi
        stmt = stmt.where(Cie10Code.code.startswith(codigo))
    else:
        palabras = [p for p in texto.split() if p]
        stmt = stmt.where(and_(*[Cie10Code.name.contains(p) for p in palabras]))
    stmt = stmt.order_by(Cie10Code.is_dental.desc(), Cie10Code.code).limit(limit)
    return db.scalars(stmt).all()


def obtener_cie10(db: Session, code: str) -> Cie10Code:
    cie = db.get(Cie10Code, code.strip().upper().replace(".", ""))
    if not cie:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Codigo CIE-10 no encontrado")
    return cie
