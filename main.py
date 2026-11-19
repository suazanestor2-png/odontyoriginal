from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_cors_origins, settings

# Modelos (necesarios para que SQLAlchemy registre todas las tablas y relaciones)
from app.identity import models  # noqa: F401
from app.clinics import models as clinic_models  # noqa: F401
from app.patients import models as patient_models  # noqa: F401
from app.appointments import models as appointment_models  # noqa: F401
from app.clinical_history import models as clinical_history_models  # noqa: F401
from app.odontogram import models as odontogram_models  # noqa: F401
from app.notifications import models as notifications_models  # noqa: F401
from app.catalogs import models as catalogs_models  # noqa: F401
from app.controls import models as controls_models  # noqa: F401
from app.billing import models as billing_models  # noqa: F401
from app.subscriptions import models as subscriptions_models  # noqa: F401
from app.consents import models as consents_models  # noqa: F401

# Routers
from app.identity import auth_router, permissions_router, users_router
from app.clinics import router as clinics_router
from app.patients import router as patients_router
from app.appointments import router as appointments_router
from app.clinical_history import router as clinical_history_router
from app.odontogram import router as odontogram_router
from app.notifications import router as notifications_router
from app.catalogs import router as catalogs_router
from app.controls import router as controls_router
from app.billing import expenses_router, invoices_router, settings_router as billing_settings_router
from app.reports import router as reports_router
from app.subscriptions import router as subscriptions_router
from app.consents import router as consents_router
from app.core import internal_router

# Seeds
from app.identity.seed import seed_roles_and_permissions
from app.odontogram.seed import seed_dental_catalogs
from app.catalogs.seed import seed_cie10, seed_cups
from app.core.database import SessionLocal
from app.subscriptions.service import seed_subscription_plans

import time


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.time()
    print("[startup] seed_roles_and_permissions: inicio", flush=True)
    seed_roles_and_permissions()
    print(f"[startup] seed_roles_and_permissions: ok ({time.time() - t0:.1f}s)", flush=True)

    t1 = time.time()
    print("[startup] seed_dental_catalogs: inicio", flush=True)
    seed_dental_catalogs()
    print(f"[startup] seed_dental_catalogs: ok ({time.time() - t1:.1f}s)", flush=True)

    t2 = time.time()
    seed_cups()
    print(f"[startup] seed_cups: ok ({time.time() - t2:.1f}s)", flush=True)
    seed_cie10()

    with SessionLocal() as db:
        seed_subscription_plans(db)
    yield


app = FastAPI(
    title="Odonty API",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)

app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(permissions_router.router)
app.include_router(clinics_router.router)
app.include_router(patients_router.router)
app.include_router(appointments_router.router)
app.include_router(clinical_history_router.router)
app.include_router(odontogram_router.router)
app.include_router(notifications_router.router)
app.include_router(catalogs_router.router)
app.include_router(controls_router.router)
app.include_router(invoices_router.router)
app.include_router(expenses_router.router)
app.include_router(billing_settings_router.router)
app.include_router(reports_router.router)
app.include_router(subscriptions_router.router)
app.include_router(consents_router.router)
app.include_router(internal_router.router)


@app.middleware("http")
async def remove_server_header(request, call_next):
    response = await call_next(request)
    response.headers["Server"] = "Odonty"
    return response


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor"})


@app.get("/")
def health():
    return {"status": "ok"}