from datetime import date, datetime
from zoneinfo import ZoneInfo

# Las fechas de negocio (citas, facturas, pagos) se manejan en hora de Colombia
BOGOTA_TZ = ZoneInfo("America/Bogota")


def today_bogota() -> date:
    return datetime.now(BOGOTA_TZ).date()
