from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clinics.models import Clinic
from app.core.dates import today_bogota
from app.email_service import send_subscription_alert_email
from app.identity.models import Role, User
from app.notifications.service import clinic_staff, notify
from app.subscriptions.models import ClinicSubscription
from app.subscriptions.service import GRACE_DAYS, compute_status

TIPO = "suscripcion"

# (bandera, condicion sobre los dias que faltan, asunto)
AVISOS = (
    ("alert_7d_sent", lambda d: 4 <= d <= 7, "Tu suscripcion vence pronto"),
    ("alert_3d_sent", lambda d: 2 <= d <= 3, "Tu suscripcion vence en pocos dias"),
    ("alert_1d_sent", lambda d: 0 <= d <= 1, "Tu suscripcion vence manana"),
    ("alert_grace_sent", lambda d: -GRACE_DAYS <= d < 0, "Tu suscripcion vencio: periodo de gracia"),
    ("alert_readonly_sent", lambda d: d < -GRACE_DAYS, "Tu cuenta esta en solo lectura"),
)


def run_subscription_alerts(db: Session, hoy: date | None = None) -> dict:
    hoy = hoy or today_bogota()
    enviados = 0

    subs = db.scalars(
        select(ClinicSubscription).join(Clinic, ClinicSubscription.clinic_id == Clinic.id)
        .where(Clinic.status == "active")
    ).all()

    for sub in subs:
        dias = (sub.current_period_end - hoy).days
        aviso = next((a for a in AVISOS if a[1](dias)), None)
        if not aviso or getattr(sub, aviso[0]):
            continue
        # Si salta directo a un aviso posterior (ej. el cron estuvo caido), no se envian los anteriores
        flag, _, asunto = aviso
        mensaje = compute_status(sub, hoy)["message"]

        admins = clinic_staff(db, sub.clinic_id, ("admin",))
        for admin in admins:
            send_subscription_alert_email(admin.email, sub.clinic.name, asunto, mensaje)
        notify(db, admins, sub.clinic_id, TIPO, asunto, mensaje)

        if flag == "alert_readonly_sent":
            # Avisar tambien al equipo de Odonty
            super_admins = db.scalars(
                select(User).join(Role, User.role_id == Role.id).where(Role.name == "super_admin", User.is_active.is_(True))
            ).all()
            for sa in super_admins:
                send_subscription_alert_email(
                    sa.email, sub.clinic.name, "Clinica en solo lectura",
                    f"La clinica {sub.clinic.name} (id {sub.clinic_id}) no renovo y quedo en solo lectura.",
                )

        setattr(sub, flag, True)
        enviados += 1

    db.commit()
    return {"avisos_suscripcion": enviados}
