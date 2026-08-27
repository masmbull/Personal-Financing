import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Core
    DATABASE_URL: str = "sqlite:///./data/finance.db"
    APP_NAME: str = "Finance"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8080

    # Environment: "development" | "production" | "test"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # Security (required before any real auth is added; not used yet)
    SECRET_KEY: str = "change-me-in-production"

    # CORS: comma-separated list of allowed origins. Never use "*" in production.
    CORS_ORIGINS: str = "http://localhost:8080,http://localhost:3000,http://127.0.0.1:8080"

    # Receipt uploads
    RECEIPT_UPLOAD_DIR: str = "data/receipts"
    RECEIPT_MAX_SIZE_MB: int = 5

    # Tesseract OCR engine path (set explicitly on Windows; overridable via env)
    TESSERACT_CMD: str = os.environ.get(
        "TESSERACT_CMD",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.name == "nt" else "tesseract",
    )

    # OCR language fallback chain: ind+eng -> eng -> none
    RECEIPT_OCR_LANG: str = os.environ.get("RECEIPT_OCR_LANG", "ind+eng")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def db_echo(self) -> bool:
        return self.DEBUG and not self.is_production

    @property
    def log_level(self) -> str:
        return "WARNING" if self.is_production else "INFO"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
