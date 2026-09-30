from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SECRET_KEY: str
    DATABASE_URL: str = "postgresql+psycopg://suaza:1120Fai.@localhost:5432/odonty"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 15
    REFRESH_TOKEN_DAYS: int = 7
    RESET_TOKEN_MINUTES: int = 30
    MFA_TOKEN_MINUTES: int = 5
    MAX_FAILED_ATTEMPTS: int = 5
    LOCK_MINUTES: int = 15


settings = Settings()