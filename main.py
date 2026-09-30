from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401
from app.database import Base, engine
from app.routers import auth
from app.seed import seed_roles_and_permissions
from app.routers import auth, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    seed_roles_and_permissions()
    yield


app = FastAPI(title="Odonty API", lifespan=lifespan)
app.include_router(auth.router)

app.include_router(auth.router)
app.include_router(users.router)


@app.get("/")
def health():
    return {"status": "ok"}