from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permission
from app.identity.models import User
from app.odontogram import service
from app.odontogram.schemas import OdontogramEntryCreateIn, OdontogramEntryOut

router = APIRouter(prefix="/odontogram", tags=["Odontograma"])


@router.post("", response_model=OdontogramEntryOut, status_code=status.HTTP_201_CREATED)
def create_odontogram_entry(
    data: OdontogramEntryCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("odontogram.create")),
):
    return service.registrar_entrada(db, actor, data)


@router.get("/catalogs")
def list_dental_catalogs(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("odontogram.view")),
):
    """Hallazgos y procedimientos dentales validos para el formulario del odontograma."""
    return service.catalogos_dentales(db)


@router.get("/{patient_id}", response_model=list[OdontogramEntryOut])
def get_current_odontogram(
    request: Request,
    patient_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("odontogram.view")),
):
    return service.odontograma_actual(db, request, actor, patient_id)


@router.get("/{patient_id}/history", response_model=list[OdontogramEntryOut])
def get_odontogram_history(
    request: Request,
    patient_id: int,
    response: Response,
    tooth_fdi: int | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("odontogram.view")),
):
    items, total = service.historial(db, request, actor, patient_id, tooth_fdi, limit, offset)
    response.headers["X-Total-Count"] = str(total)
    return items
