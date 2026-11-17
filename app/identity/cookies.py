import secrets
from datetime import datetime, timezone

from fastapi import Response

from app.core.config import settings

ACCESS_COOKIE = "odonty_access"
REFRESH_COOKIE = "odonty_refresh"
CSRF_COOKIE = "odonty_csrf"
CSRF_HEADER = "X-CSRF-Token"


def _max_age(expires_at: datetime) -> int:
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    return max(int((expires_at - ahora).total_seconds()), 0)


def set_auth_cookies(response: Response, access: str, access_exp: datetime, refresh: str, refresh_exp: datetime) -> None:
    """
    Guarda la sesion en cookies httpOnly (JavaScript no las puede leer, asi un script malicioso
    no roba el token). La cookie CSRF si es legible: el frontend la copia en el header
    X-CSRF-Token en cada POST/PUT/PATCH/DELETE (patron "double submit").
    """
    comunes = {"secure": settings.COOKIE_SECURE, "samesite": settings.COOKIE_SAMESITE, "path": "/"}
    response.set_cookie(ACCESS_COOKIE, access, max_age=_max_age(access_exp), httponly=True, **comunes)
    response.set_cookie(REFRESH_COOKIE, refresh, max_age=_max_age(refresh_exp), httponly=True, **comunes)
    response.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(32), max_age=_max_age(refresh_exp), httponly=False, **comunes)


def clear_auth_cookies(response: Response) -> None:
    for nombre in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(nombre, path="/", secure=settings.COOKIE_SECURE, samesite=settings.COOKIE_SAMESITE)
