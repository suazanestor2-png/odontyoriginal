from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.clinics import service
from app.clinics.schemas import (
    ClinicListOut, ClinicOut, ClinicProfileOut, ClinicProfileUpdateIn, ClinicReviewIn,
)
from app.core.database import get_db
from app.core.deps import get_active_user, require_permission
from app.identity.models import User

router = APIRouter(prefix="/clinics", tags=["Clinicas"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_clinic(
    clinic_name: str = Form(...),
    nit: str = Form(...),
    nit_dv: str = Form(...),
    email: str = Form(...),
    document_number: str = Form(...),
    full_name: str = Form(...),
    phone_number: str = Form(...),
    password: str = Form(...),
    cedula_file: UploadFile = File(...),
    rut_file: UploadFile = File(...),
    camara_comercio_file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    return service.registrar_clinica(
        db, clinic_name, nit, nit_dv, email, document_number, full_name, phone_number, password,
        cedula_file, rut_file, camara_comercio_file,
    )


@router.get("/pending", response_model=list[ClinicOut])
def list_pending_clinics(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinics.review")),
):
    return service.clinicas_pendientes(db)


@router.patch("/{clinic_id}/review", response_model=ClinicOut)
def review_clinic(
    clinic_id: int,
    data: ClinicReviewIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinics.review")),
):
    return service.revisar_clinica(db, actor, clinic_id, data)


# ---------- Listado (super_admin) ----------

@router.get("", response_model=list[ClinicListOut])
def list_clinics(
    response: Response,
    status_filter: str | None = Query(
        None, alias="status", pattern=r"^(pending_email|pending_review|active|rejected|suspended)$"
    ),
    q: str | None = Query(None, max_length=100, description="Nombre o NIT"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinics.view")),
):
    items, total = service.listar_clinicas(db, status_filter, q, limit, offset)
    response.headers["X-Total-Count"] = str(total)
    return items


# ---------- Mi clinica (datos, contacto y horarios) ----------

@router.get("/me", response_model=ClinicProfileOut)
def get_my_clinic(
    db: Session = Depends(get_db),
    actor: User = Depends(get_active_user),
):
    return service.mi_clinica(db, actor)


@router.patch("/me", response_model=ClinicProfileOut)
def update_my_clinic(
    data: ClinicProfileUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinic.settings")),
):
    return service.actualizar_mi_clinica(db, actor, data)


@router.post("/me/logo", response_model=ClinicProfileOut)
def upload_my_clinic_logo(
    logo: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinic.settings")),
):
    return service.subir_logo(db, actor, logo)
