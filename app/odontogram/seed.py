from app.core.database import SessionLocal
from app.odontogram.models import DentalCondition, DentalProcedure

DENTAL_CONDITIONS = {
    "sano": "Sano",
    "caries": "Caries",
    "obturado": "Obturado / restaurado",
    "fracturado": "Fracturado",
    "ausente": "Ausente (extraido)",
    "corona": "Corona",
    "endodoncia_realizada": "Endodoncia realizada",
    "movil": "Movilidad dental",
    "implante": "Implante",
    "sellante": "Sellante",
    "protesis_fija": "Protesis fija",
    "protesis_removible": "Protesis removible",
    "en_erupcion": "En erupcion",
    "impactado": "Impactado",
}

DENTAL_PROCEDURES = {
    "profilaxis": "Profilaxis (limpieza)",
    "resina": "Resina (obturacion estetica)",
    "amalgama": "Amalgama",
    "extraccion": "Extraccion",
    "endodoncia": "Endodoncia",
    "corona": "Corona",
    "sellante": "Aplicacion de sellante",
    "blanqueamiento": "Blanqueamiento",
    "ortodoncia": "Ortodoncia",
    "implante": "Implante",
    "cirugia": "Cirugia oral",
    "raspado_alisado": "Raspado y alisado radicular",
    "fluorizacion": "Fluorizacion",
    "radiografia": "Radiografia",
}


def seed_dental_catalogs() -> None:
    with SessionLocal() as db:
        conditions = {c.code: c for c in db.query(DentalCondition).all()}
        for code, name in DENTAL_CONDITIONS.items():
            if code not in conditions:
                db.add(DentalCondition(code=code, name=name))

        procedures = {p.code: p for p in db.query(DentalProcedure).all()}
        for code, name in DENTAL_PROCEDURES.items():
            if code not in procedures:
                db.add(DentalProcedure(code=code, name=name))

        db.commit()