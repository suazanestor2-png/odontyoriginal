from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_permission
from app.identity.models import User
from app.patients import service
from app.patients.schemas import PatientAlertsOut, PatientCheckOut, PatientCreateIn, PatientOut, PatientUpdateIn

router = APIRouter(prefix="/patients", tags=["Pacientes"])


@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
def register_patient(
    data: PatientCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("patients.create")),
):
    return service.registrar_paciente(db, actor, data)


@router.get("", response_model=list[PatientOut])
def list_patients(
    response: Response,
    search: str | None = Query(None, description="Busca por nombre, correo o documento"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("patients.view")),
):
    items, total = service.listar_pacientes(db, actor, search, limit, offset)
    response.headers["X-Total-Count"] = str(total)
    return items


@router.get("/check", response_model=PatientCheckOut)
def check_patient(
    document_number: str = Query(...),
    document_type: str = Query("CC", pattern=r"^(TI|CC|CE|PA)$"),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("patients.create")),
):
    return service.verificar_documento(db, actor, document_type, document_number)


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("patients.view")),
):
    return service.paciente_de_mi_clinica(db, patient_id, actor)


@router.get("/{patient_id}/alerts", response_model=PatientAlertsOut)
def get_patient_alerts(
    request: Request,
    patient_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("patients.view")),
):
    return service.alertas_del_paciente(db, request, actor, patient_id)


@router.patch("/{patient_id}", response_model=PatientOut)
def update_patient(
    patient_id: int,
    data: PatientUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("patients.edit")),
):
    return service.actualizar_paciente(db, actor, patient_id, data)
