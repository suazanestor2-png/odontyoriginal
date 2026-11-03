from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_active_user, require_permission
from app.core.security import generate_temp_password, hash_password
from app.core.validators import _documento, _telefono
from app.email_service import send_welcome_email
from app.identity.audit import log_event
from app.identity.models import Role, User
from app.patients.models import Patient
from app.patients.schemas import PatientCheckOut, PatientCreateIn, PatientOut, PatientRegisterIn, PatientUpdateIn

router = APIRouter(prefix="/patients", tags=["Pacientes"])


def _to_out(patient: Patient) -> PatientOut:
    return PatientOut(
        id=patient.id,
        user_id=patient.user_id,
        full_name=patient.user.full_name,
        email=patient.user.email,
        document_number=patient.user.document_number,
        document_type=patient.document_type,
        birth_date=patient.birth_date,
        is_minor=patient.is_minor,
        gender=patient.gender,
        blood_type=patient.blood_type,
        address=patient.address,
        eps=patient.eps,
        guardian_full_name=patient.guardian_full_name,
        guardian_document_number=patient.guardian_document_number,
        guardian_phone=patient.guardian_phone,
        guardian_relationship=patient.guardian_relationship,
        emergency_contact_name=patient.emergency_contact_name,
        emergency_contact_phone=patient.emergency_contact_phone,
        allergies=patient.allergies,
        notes=patient.notes,
    )


# Registro hecho por el personal de la clinica

@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
def register_patient(
    data: PatientRegisterIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("patients.create")),
):
    email = data.email.strip().lower()
    try:
        document_number = _documento(data.document_number)
        phone_number = _telefono(data.phone_number)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    existing_user = db.scalar(select(User).where(or_(User.email == email, User.document_number == document_number)))

    if existing_user:
        ya_tiene_perfil = db.scalar(select(Patient).where(Patient.user_id == existing_user.id))
        if ya_tiene_perfil:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Este usuario ya tiene un perfil de paciente (id={ya_tiene_perfil.id}); "
                f"usa PATCH /patients/{ya_tiene_perfil.id} para editarlo",
            )
        if existing_user.role.name != "usuario":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Ese correo o documento pertenece a una cuenta de personal, no se puede registrar como paciente",
            )
        if existing_user.clinic_id and existing_user.clinic_id != actor.clinic_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Ese usuario pertenece a otra clinica")

        # El usuario ya existe (se registro solo, por ejemplo): solo completamos su perfil clinico.
        if not existing_user.clinic_id:
            existing_user.clinic_id = actor.clinic_id

        patient = Patient(
            user_id=existing_user.id,
            clinic_id=actor.clinic_id,
            **data.model_dump(exclude={"email", "document_number", "full_name", "phone_number"}),
        )
        db.add(patient)
        db.commit()
        db.refresh(patient)
        log_event(db, "PATIENT_LINKED_EXISTING_USER", actor.id, f"patient={patient.id} user={existing_user.id}")
        return _to_out(patient)

    # No existia ningun usuario: flujo original, crea User + Patient desde cero.
    usuario_role = db.scalar(select(Role).where(Role.name == "usuario"))
    temp_password = generate_temp_password()

    user = User(
        email=email,
        document_number=document_number,
        full_name=data.full_name.strip(),
        phone_number=phone_number,
        role_id=usuario_role.id,
        clinic_id=actor.clinic_id,
        hashed_password=hash_password(temp_password),
        is_active=True,
        must_change_password=True,
    )
    db.add(user)
    db.flush()

    patient = Patient(
        user_id=user.id,
        clinic_id=actor.clinic_id,
        **data.model_dump(exclude={"email", "document_number", "full_name", "phone_number"}),
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)

    send_welcome_email(user.email, user.full_name, temp_password)
    log_event(db, "PATIENT_REGISTERED", actor.id, f"patient={patient.id}")
    return _to_out(patient)


# ---------- El propio paciente (self-service) ----------

@router.post("/me", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
def create_my_patient_profile(
    data: PatientCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_active_user),
):
    if user.role.name != "usuario":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo un usuario puede completar un perfil de paciente")
    if not user.clinic_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tu cuenta no esta asociada a una clinica")

    existe = db.scalar(select(Patient).where(Patient.user_id == user.id))
    if existe:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya tienes un perfil de paciente, usa PATCH /patients/me")

    patient = Patient(user_id=user.id, clinic_id=user.clinic_id, **data.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    log_event(db, "PATIENT_PROFILE_CREATED", user.id)
    return _to_out(patient)


@router.get("/me", response_model=PatientOut)
def get_my_patient_profile(db: Session = Depends(get_db), user: User = Depends(get_active_user)):
    patient = db.scalar(select(Patient).where(Patient.user_id == user.id))
    if not patient:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aun no has completado tu perfil de paciente")
    return _to_out(patient)


@router.patch("/me", response_model=PatientOut)
def update_my_patient_profile(
    data: PatientUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_active_user),
):
    patient = db.scalar(select(Patient).where(Patient.user_id == user.id))
    if not patient:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aun no has completado tu perfil de paciente")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(patient, field, value)
    db.commit()
    db.refresh(patient)
    log_event(db, "PATIENT_PROFILE_UPDATED", user.id)
    return _to_out(patient)


# El personal de la clinica

@router.get("", response_model=list[PatientOut])
def list_patients(
    response: Response,
    search: str | None = Query(None, description="Busca por nombre, correo o documento"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("patients.view")),
):
    query = select(Patient).join(User, Patient.user_id == User.id)
    if actor.role.name != "super_admin":
        query = query.where(Patient.clinic_id == actor.clinic_id)
    if search:
        like = f"%{search.strip()}%"
        query = query.where(or_(User.full_name.ilike(like), User.email.ilike(like), User.document_number.ilike(like)))

    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    items = db.scalars(query.order_by(Patient.id).limit(limit).offset(offset)).all()

    response.headers["X-Total-Count"] = str(total)
    return [_to_out(p) for p in items]

@router.get("/check", response_model=PatientCheckOut)
def check_existing_user(
    email: str | None = Query(None),
    document_number: str | None = Query(None),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("patients.create")),
):
    if not email and not document_number:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Debes enviar email o document_number")

    conditions = []
    if email:
        conditions.append(User.email == email.strip().lower())
    if document_number:
        conditions.append(User.document_number == document_number.strip())

    user = db.scalar(select(User).where(or_(*conditions)))
    if not user:
        return PatientCheckOut(
            user_exists=False, user_id=None, full_name=None, email=None,
            document_number=None, has_patient_profile=False, same_clinic=False,
        )

    patient = db.scalar(select(Patient).where(Patient.user_id == user.id))
    return PatientCheckOut(
        user_exists=True,
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        document_number=user.document_number,
        has_patient_profile=patient is not None,
        same_clinic=(user.clinic_id == actor.clinic_id),
    )

@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("patients.view")),
):
    patient = db.get(Patient, patient_id)
    if not patient or (actor.role.name != "super_admin" and patient.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")
    return _to_out(patient)


@router.patch("/{patient_id}", response_model=PatientOut)
def update_patient(
    patient_id: int,
    data: PatientUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("patients.edit")),
):
    patient = db.get(Patient, patient_id)
    if not patient or (actor.role.name != "super_admin" and patient.clinic_id != actor.clinic_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paciente no encontrado")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(patient, field, value)
    db.commit()
    db.refresh(patient)
    log_event(db, "PATIENT_PROFILE_UPDATED", actor.id, f"patient={patient.id}")
    return _to_out(patient)




