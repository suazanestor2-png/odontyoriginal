from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,   # detecta conexiones caídas antes de usarlas
    pool_size=5,          # Supabase gratis limita conexiones; mantenlo pequeño
    max_overflow=5,
    pool_recycle=300,     # renueva conexiones cada 5 min (el pooler cierra las inactivas)
)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()