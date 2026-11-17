from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.appointments.reminders import run_appointment_reminders
from app.core.config import settings
from app.core.database import get_db
from app.controls.alerts import run_control_alerts

router = APIRouter(prefix="/internal", tags=["Interno"])


def verify_cron_secret(x_cron_secret: str = Header(default="")) -> None:
    if not settings.INTERNAL_CRON_SECRET or x_cron_secret != settings.INTERNAL_CRON_SECRET:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No autorizado")


@router.post("/run-reminders", dependencies=[Depends(verify_cron_secret)])
def run_reminders(db: Session = Depends(get_db)):
    resultado = run_appointment_reminders(db)
    resultado.update(run_control_alerts(db))
    return {"status": "ok", **resultado}