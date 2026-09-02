import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # ---- Authentication ----
    # Bootstrap admin created on first startup when both vars are set.
    # Never commit real credentials to the repo; provide via .env/environment.
    AUTH_BOOTSTRAP_USERNAME: str = ""
    AUTH_BOOTSTRAP_PASSWORD: str = ""
    AUTH_SESSION_TTL_DAYS: int = 30

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

    # Optional AI vision OCR engine (Ollama, OpenAI-compatible). Preferred over
    # Tesseract when the endpoint+model respond; otherwise local path is kept.
    RECEIPT_AI_BASE_URL: str = os.environ.get(
        "RECEIPT_AI_BASE_URL", "http://localhost:11434/v1")
    RECEIPT_AI_MODEL: str = os.environ.get(
        "RECEIPT_AI_MODEL", "llama3.2-vision")
    RECEIPT_AI_TIMEOUT_SEC: float = float(
        os.environ.get("RECEIPT_AI_TIMEOUT_SEC", "120"))
    RECEIPT_AI_FALLBACK_TESSERACT: bool = os.environ.get(
        "RECEIPT_AI_FALLBACK_TESSERACT", "1").lower() in ("1", "true", "yes")
    RECEIPT_AI_MAX_IMAGE_WIDTH: int = int(
        os.environ.get("RECEIPT_AI_MAX_IMAGE_WIDTH", "1600"))

    # Canonical timezone for all date-based calculations and daily jobs.
    # Indonesian-first default; override via APP_TIMEZONE env var.
    APP_TIMEZONE: str = os.environ.get("APP_TIMEZONE", "Asia/Jakarta")


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

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
