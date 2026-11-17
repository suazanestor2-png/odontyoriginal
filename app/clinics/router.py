from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.clinics.models import Clinic
from app.clinics.schemas import (
    ClinicListOut, ClinicOut, ClinicProfileOut, ClinicProfileUpdateIn, ClinicReviewIn,
)
from app.core.cloudinary_service import upload_image, upload_pdf
from app.core.database import get_db
from app.core.deps import get_active_user, require_permission
from app.core.security import hash_password
from app.core.validators import _documento, _password, _telefono, calcular_dv_nit
from app.identity.audit import log_event
from app.identity.models import Role, User
from app.subscriptions.service import ensure_trial
from app.email_service import (
    send_clinic_pending_notification,
    send_clinic_registration_received,
    send_clinic_review_result,
)

router = APIRouter(prefix="/clinics", tags=["Clinicas"])

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}


def _validar_pdf(file: UploadFile, campo: str) -> bytes:
    if file.content_type not in PDF_CONTENT_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El {campo} debe ser un archivo PDF")

    contenido = file.file.read(MAX_FILE_SIZE + 1)
    if len(contenido) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El {campo} esta vacio")
    if len(contenido) > MAX_FILE_SIZE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El {campo} no puede superar los 5 MB")
    # El content_type lo manda el navegador y se puede falsificar: se revisa la firma real del archivo
    if not contenido.startswith(b"%PDF-"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El {campo} no es un PDF valido")

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
    camara_comercio_file: UploadFile = File(...),
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
    cedula_bytes = _validar_pdf(cedula_file, "documento de cedula")
    rut_bytes = _validar_pdf(rut_file, "documento de RUT")
    camara_bytes = _validar_pdf(camara_comercio_file, "certificado de Camara de Comercio")

    # --- Subir a Cloudinary (fuera de la transaccion de BD, son operaciones independientes) ---
    try:
        cedula_url = upload_pdf(cedula_bytes, prefix=f"cedula_{nit}")
        rut_url = upload_pdf(rut_bytes, prefix=f"rut_{nit}")
        camara_comercio_url = upload_pdf(camara_bytes, prefix=f"camara_comercio_{nit}")
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
        camara_comercio_url=camara_comercio_url,
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

    super_admins = db.scalars(
        select(User.email).join(Role, User.role_id == Role.id).where(Role.name == "super_admin")
    ).all()
    if super_admins:
        send_clinic_pending_notification(
            list(super_admins), clinic.name, clinic.nit,
            clinic.cedula_url, clinic.rut_url, clinic.camara_comercio_url,
        )

    send_clinic_registration_received(admin_user.email, admin_user.full_name, clinic.name)

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
    if data.approve:
        # Al aprobarla arranca su periodo de prueba gratis
        ensure_trial(db, clinic.id)
    db.commit()
    db.refresh(clinic)

    admin_de_la_clinica = db.scalar(
        select(User).where(
            User.clinic_id == clinic.id,
            User.role_id == db.scalar(select(Role.id).where(Role.name == "admin")),
        )
    )
    if admin_de_la_clinica:
        send_clinic_review_result(admin_de_la_clinica.email, clinic.name, data.approve)

    log_event(db, "CLINIC_REVIEWED", actor.id, f"clinic={clinic.id} aprobada={data.approve}")
    return clinic

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
    query = select(Clinic)
    if status_filter:
        query = query.where(Clinic.status == status_filter)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Clinic.name.ilike(like), Clinic.nit.ilike(like)))
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    response.headers["X-Total-Count"] = str(total)
    return db.scalars(query.order_by(Clinic.name).limit(limit).offset(offset)).all()


# ---------- Mi clinica (datos, contacto y horarios) ----------

CAMPOS_OBLIGATORIOS = {
    "opening_time", "closing_time", "working_days", "default_appointment_minutes",
    "appointment_reminder_first_hours", "appointment_reminder_second_hours",
    "control_reminder_first_days", "control_reminder_second_days",
}


def _mi_clinica(db: Session, actor: User) -> Clinic:
    if not actor.clinic_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tu usuario no pertenece a ninguna clinica")
    return db.get(Clinic, actor.clinic_id)


@router.get("/me", response_model=ClinicProfileOut)
def get_my_clinic(
    db: Session = Depends(get_db),
    actor: User = Depends(get_active_user),
):
    return _mi_clinica(db, actor)


@router.patch("/me", response_model=ClinicProfileOut)
def update_my_clinic(
    data: ClinicProfileUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinic.settings")),
):
    clinic = _mi_clinica(db, actor)
    values = data.model_dump(exclude_unset=True)

    apertura = values.get("opening_time") or clinic.opening_time
    cierre = values.get("closing_time") or clinic.closing_time
    if apertura >= cierre:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La hora de apertura debe ser anterior a la de cierre")

    for primero, segundo, unidad in (
        ("appointment_reminder_first_hours", "appointment_reminder_second_hours", "horas"),
        ("control_reminder_first_days", "control_reminder_second_days", "dias"),
    ):
        a = values[primero] if values.get(primero) is not None else getattr(clinic, primero)
        b = values[segundo] if values.get(segundo) is not None else getattr(clinic, segundo)
        if a and b and a <= b:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"El primer recordatorio ({a} {unidad}) debe ser con mas anticipacion que el segundo ({b} {unidad})",
            )

    if values.get("phone"):
        try:
            values["phone"] = _telefono(values["phone"])
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    if values.get("email"):
        values["email"] = values["email"].strip().lower()
    if values.get("working_days"):
        values["working_days"] = ",".join(sorted(set(values["working_days"].split(","))))

    for field, value in values.items():
        if value is None and field in CAMPOS_OBLIGATORIOS:
            continue  # null en un campo obligatorio: se deja como estaba
        setattr(clinic, field, value)
    clinic.updated_by = actor.id
    db.commit()
    db.refresh(clinic)
    log_event(db, "CLINIC_PROFILE_UPDATED", actor.id, f"clinic={clinic.id} campos={','.join(values)}")
    return clinic


MAX_LOGO_SIZE = 2 * 1024 * 1024  # 2 MB
FIRMAS_IMAGEN = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")  # PNG, JPG


@router.post("/me/logo", response_model=ClinicProfileOut)
def upload_my_clinic_logo(
    logo: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("clinic.settings")),
):
    clinic = _mi_clinica(db, actor)
    contenido = logo.file.read(MAX_LOGO_SIZE + 1)
    if not contenido:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El logo esta vacio")
    if len(contenido) > MAX_LOGO_SIZE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El logo no puede superar los 2 MB")
    if not contenido.startswith(FIRMAS_IMAGEN):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El logo debe ser una imagen PNG o JPG")

    try:
        clinic.logo_url = upload_image(contenido, prefix=f"logo_clinica_{clinic.id}")
    except Exception:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "No se pudo subir el logo, intenta de nuevo")
    db.commit()
    db.refresh(clinic)
    log_event(db, "CLINIC_LOGO_UPDATED", actor.id, f"clinic={clinic.id}")
    return clinic
