from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SECRET_KEY: str
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



settings = Settings()

def get_cors_origins() -> list[str]:
    return [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]