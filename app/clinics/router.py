from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.clinics.models import Clinic
from app.core.cloudinary_service import upload_document
from app.core.database import get_db
from app.core.security import hash_password
from app.core.validators import _documento, _password, _telefono, calcular_dv_nit
from app.identity.audit import log_event
from app.identity.models import Role, User
from app.core.deps import require_permission

from app.clinics.schemas import ClinicOut, ClinicReviewIn

router = APIRouter(prefix="/clinics", tags=["Clinicas"])

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def _validar_imagen(file: UploadFile, campo: str) -> bytes:
    content_types_validos = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in content_types_validos:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El {campo} debe ser una imagen JPG, PNG o WEBP")

    contenido = file.file.read()
    if len(contenido) > MAX_FILE_SIZE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El {campo} no puede superar los 5 MB")
    if len(contenido) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El {campo} esta vacio")

    return contenido


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
    db: Session = Depends(get_db),
):
    # --- Validaciones de datos (las mismas reglas que ya usas en otros registros) ---
    if len(clinic_name.strip()) < 3:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El nombre de la clinica debe tener al menos 3 caracteres")

    nit = nit.strip()
    if not nit.isdigit():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El NIT solo debe contener numeros")

    dv_calculado = calcular_dv_nit(nit)
    if dv_calculado != nit_dv.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El digito de verificacion del NIT no coincide")

    try:
        document_number = _documento(document_number)
        phone_number = _telefono(phone_number)
        password = _password(password)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    email = email.strip().lower()
    full_name = full_name.strip()

    # --- Verificar duplicados antes de subir nada a Cloudinary (evita gasto innecesario) ---
    nit_existe = db.scalar(select(Clinic).where(Clinic.nit == nit))
    if nit_existe:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una clinica registrada con ese NIT")

    usuario_existe = db.scalar(
        select(User).where(or_(User.email == email, User.document_number == document_number))
    )
    if usuario_existe:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese correo o documento")

    admin_role = db.scalar(select(Role).where(Role.name == "admin"))
    if not admin_role:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "El rol 'admin' no existe, revisa el seed")

    # --- Validar los archivos antes de subirlos ---
    cedula_bytes = _validar_imagen(cedula_file, "documento de cedula")
    rut_bytes = _validar_imagen(rut_file, "documento de RUT")

    # --- Subir a Cloudinary (fuera de la transaccion de BD, son operaciones independientes) ---
    try:
        cedula_url = upload_document(cedula_bytes, public_id=f"cedula_{nit}")
        rut_url = upload_document(rut_bytes, public_id=f"rut_{nit}")
    except Exception:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "No se pudieron subir los documentos, intenta de nuevo")

    # --- Crear clinica + usuario admin, en una sola transaccion ---
    clinic = Clinic(
        name=clinic_name,
        nit=nit,
        nit_dv=nit_dv,
        status="pending_review",
        cedula_url=cedula_url,
        rut_url=rut_url,
    )
    db.add(clinic)
    db.flush()  # para obtener clinic.id sin cerrar la transaccion todavia

    admin_user = User(
        email=email,
        document_number=document_number,
        full_name=full_name,
        phone_number=phone_number,
        hashed_password=hash_password(password),
        role_id=admin_role.id,
        clinic_id=clinic.id,
        is_active=True,
    )
    db.add(admin_user)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "No se pudo completar el registro")

    db.refresh(clinic)
    db.refresh(admin_user)

    log_event(db, "CLINIC_REGISTERED", admin_user.id, f"clinic={clinic.id} nit={nit}")

    return {
        "detail": "Registro recibido. Tu clinica sera revisada antes de activarse.",
        "clinic_id": clinic.id,
        "clinic_status": clinic.status,
    }


@router.get("/pending", response_model=list[ClinicOut])
def list_pending_clinics(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinics.review")),
):
    clinics = db.scalars(select(Clinic).where(Clinic.status == "pending_review").order_by(Clinic.id)).all()
    return clinics


@router.patch("/{clinic_id}/review", response_model=ClinicOut)
def review_clinic(
    clinic_id: int,
    data: ClinicReviewIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinics.review")),
):
    clinic = db.get(Clinic, clinic_id)
    if not clinic:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clinica no encontrada")
    if clinic.status != "pending_review":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Esta clinica ya fue revisada")

    clinic.status = "active" if data.approve else "rejected"
    db.commit()
    db.refresh(clinic)

    log_event(db, "CLINIC_REVIEWED", actor.id, f"clinic={clinic.id} aprobada={data.approve}")
    return clinic