import secrets

import cloudinary
import cloudinary.uploader

from app.core.config import settings

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,
)


def upload_pdf(file_bytes: bytes, prefix: str) -> str:
    """Sube un PDF a Cloudinary y devuelve su URL.

    Se sube como "raw" (archivo tal cual): Cloudinary bloquea por defecto la
    entrega de PDFs subidos como imagen en cuentas gratuitas.
    El nombre lleva un sufijo aleatorio para que la URL no se pueda adivinar
    a partir del NIT (son documentos con datos personales).
    """
    public_id = f"{prefix}_{secrets.token_urlsafe(16)}.pdf"
    result = cloudinary.uploader.upload(
        file_bytes,
        public_id=public_id,
        folder="odonty/clinic_documents",
        resource_type="raw",
    )
    return result["secure_url"]
