from datetime import date

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.clinical_history import service
from app.clinical_history.schemas import AccessLogOut, ClarificationIn, ClinicalEntryCreateIn, ClinicalEntryOut
from app.core.database import get_db
from app.core.deps import require_permission
from app.identity.models import User

router = APIRouter(prefix="/clinical-history", tags=["Historia clinica"])


@router.post("", response_model=ClinicalEntryOut, status_code=status.HTTP_201_CREATED)
def create_clinical_entry(
    data: ClinicalEntryCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinical_history.create")),
):
    return service.registrar_consulta(db, actor, data)


@router.get("", response_model=list[ClinicalEntryOut])
def list_clinical_history(
    request: Request,
    response: Response,
    patient_id: int = Query(...),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinical_history.view")),
):
    items, total = service.listar_historia(db, request, actor, patient_id, limit, offset)
    response.headers["X-Total-Count"] = str(total)
    return items


@router.get("/access-log", response_model=list[AccessLogOut])
def clinical_access_log(
    response: Response,
    patient_id: int | None = Query(None),
    user_id: int | None = Query(None),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinical_history.audit")),
):
    """Quien consulto la informacion clinica de los pacientes y cuando (solo admin)."""
    items, total = service.registro_de_accesos(db, actor, patient_id, user_id, from_date, to_date, limit, offset)
    response.headers["X-Total-Count"] = str(total)
    return items


@router.get("/patients/{patient_id}/pdf")
def clinical_history_pdf(
    request: Request,
    patient_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinical_history.view")),
):
    """Copia de la historia clinica del paciente en PDF (para entregarsela si la solicita)."""
    contenido, nombre = service.historia_pdf(db, request, actor, patient_id)
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/{entry_id}", response_model=ClinicalEntryOut)
def get_clinical_entry(
    request: Request,
    entry_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinical_history.view")),
):
    return service.ver_entrada(db, request, actor, entry_id)


@router.post("/{entry_id}/clarifications", response_model=ClinicalEntryOut, status_code=status.HTTP_201_CREATED)
def add_clinical_clarification(
    entry_id: int,
    data: ClarificationIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinical_history.create")),
):
    """Nota aclaratoria: corrige o completa una consulta sin modificar lo que ya se registro."""
    return service.aclarar_consulta(db, actor, entry_id, data)
