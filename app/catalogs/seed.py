"""Carga la tabla CUPS desde el CSV oficial.

Se llama en el lifespan de main.py. Si la tabla ya tiene la misma cantidad
de codigos que el CSV, no hace nada (tarda milisegundos).

Para forzar la recarga (por ejemplo, si Minsalud cambio descripciones sin
cambiar la cantidad de codigos):
    python -m app.catalogs.seed --force
"""
import csv
import sys
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.catalogs.models import CupsCode
from app.core.database import SessionLocal

CSV_PATH = Path(__file__).parent / "data" / "cups_2026.csv"
CHUNK = 1000


def _leer_csv() -> list[dict]:
    with CSV_PATH.open(encoding="utf-8") as f:
        return [
            {
                "code": r["code"],
                "name": r["name"],
                "section": r["section"],
                "is_dental": r["is_dental"] == "1",
                "is_active": True,
            }
            for r in csv.DictReader(f)
        ]


def seed_cups(force: bool = False) -> None:
    filas = _leer_csv()
    db = SessionLocal()
    try:
        total = db.scalar(select(func.count()).select_from(CupsCode))
        activos = db.scalar(select(func.count()).select_from(CupsCode).where(CupsCode.is_active))
        if not force and total == len(filas) and activos == len(filas):
            return

        for i in range(0, len(filas), CHUNK):
            stmt = insert(CupsCode).values(filas[i:i + CHUNK])
            stmt = stmt.on_conflict_do_update(
                index_elements=[CupsCode.code],
                set_={
                    "name": stmt.excluded.name,
                    "section": stmt.excluded.section,
                    "is_dental": stmt.excluded.is_dental,
                    "is_active": True,
                },
            )
            db.execute(stmt)

        # Codigos que ya no estan en la CUPS vigente: se desactivan, no se borran
        vigentes = [f["code"] for f in filas]
        db.execute(
            update(CupsCode)
            .where(CupsCode.code.not_in(vigentes), CupsCode.is_active)
            .values(is_active=False)
        )
        db.commit()
        print(f"[seed_cups] {len(filas)} codigos CUPS cargados", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    seed_cups(force="--force" in sys.argv)
