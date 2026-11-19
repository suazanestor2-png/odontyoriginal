from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.catalogs import service
from app.catalogs.schemas import Cie10Out, CupsOut
from app.core.database import get_db
from app.core.deps import get_active_user
from app.identity.models import User

router = APIRouter(prefix="/catalogs", tags=["Catalogos"])


@router.get("/cups", response_model=list[CupsOut])
def search_cups(
    q: str = Query(min_length=2, max_length=100, description="Codigo (ej. 2321) o palabras (ej. resina)"),
    dental_only: bool = Query(True, description="Solo procedimientos odontologicos"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    actor: User = Depends(get_active_user),
):
    return service.buscar_cups(db, q, dental_only, limit)


@router.get("/cups/{code}", response_model=CupsOut)
def get_cups(
    code: str,
    db: Session = Depends(get_db),
    actor: User = Depends(get_active_user),
):
    return service.obtener_cups(db, code)


@router.get("/cie10", response_model=list[Cie10Out])
def search_cie10(
    q: str = Query(min_length=2, max_length=100, description="Codigo (ej. K02) o palabras (ej. caries)"),
    dental_only: bool = Query(True, description="Solo diagnosticos odontologicos (K00-K14)"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    actor: User = Depends(get_active_user),
):
    return service.buscar_cie10(db, q, dental_only, limit)


@router.get("/cie10/{code}", response_model=Cie10Out)
def get_cie10(
    code: str,
    db: Session = Depends(get_db),
    actor: User = Depends(get_active_user),
):
    return service.obtener_cie10(db, code)
