from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.identity import models  # noqa: F401
from app.core.config import get_cors_origins, settings
from app.core.database import Base, engine
from app.identity import auth_router, users_router
from app.identity.seed import seed_roles_and_permissions


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    seed_roles_and_permissions()
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
)


app.include_router(auth_router.router)
app.include_router(users_router.router)


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