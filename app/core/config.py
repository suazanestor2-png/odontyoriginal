from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SECRET_KEY: str
    MFA_ENCRYPTION_KEY: str = ""  # llave Fernet (base64 de 32 bytes) para cifrar el secreto MFA
    DATABASE_URL: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 15
    REFRESH_TOKEN_DAYS: int = 7
    RESET_TOKEN_MINUTES: int = 30
    MFA_TOKEN_MINUTES: int = 5
    MAX_FAILED_ATTEMPTS: int = 5
    LOCK_MINUTES: int = 15
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    OTP_MINUTES: int = 10
    MAX_OTP_ATTEMPTS: int = 5
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost:8080"
    BREVO_API_KEY: str = ""
    INTERNAL_CRON_SECRET: str = ""
    # Sesion en cookies httpOnly. En local por http poner COOKIE_SECURE=false en el .env
    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: str = "lax"
    # Mientras el frontend migra a cookies, los tokens tambien se devuelven en el JSON.
    # Cuando ya use solo cookies, poner AUTH_TOKENS_IN_BODY=false en Render.
    AUTH_TOKENS_IN_BODY: bool = True
    ENVIRONMENT: str = "development"
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""


settings = Settings()

def get_cors_origins() -> list[str]:
    return [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]