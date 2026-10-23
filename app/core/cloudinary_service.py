import cloudinary
import cloudinary.uploader

from app.core.config import settings

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,
)


def upload_document(file_bytes: bytes, public_id: str) -> str:
    result = cloudinary.uploader.upload(
        file_bytes,
        public_id=public_id,
        folder="odonty/clinic_documents",
        resource_type="image",
    )
    return result["secure_url"]