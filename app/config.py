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
    AUTH_BOOTSTRAP_IS_ADMIN: bool = True
    AUTH_BOOTSTRAP_PASSWORD: str = ""
    AUTH_SESSION_TTL_DAYS: int = 30

    # CORS: comma-separated list of allowed origins. Never use "*" in production.
    CORS_ORIGINS: str = "http://localhost:8080,http://localhost:3000,http://127.0.0.1:8080"

    # Receipt uploads.
    # Mobile reality: a 50 MP Android camera can produce a 10-20 MB JPEG.
    # Combined with slow mobile (3G/4G) upstream such uploads exceed
    # Cloudflare's free-tier 100-second read timeout, causing the browser
    # to show ERR_CONNECTION_ABORTED.  The frontend now compresses images
    # client-side to ~150-250 KB, so the SERVER limit just needs to accept
    # the worst-case compressed body.  3 MB is comfortably above the
    # worst-case client-side result (1600 px @ q=0.55) while still fitting
    # inside Cloudflare's free tier on slow mobile.
    RECEIPT_UPLOAD_DIR: str = "data/receipts"
    RECEIPT_MAX_SIZE_MB: int = 3

    # Tesseract OCR engine path (set explicitly on Windows; overridable via env)
    TESSERACT_CMD: str = os.environ.get(
        "TESSERACT_CMD",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.name == "nt" else "tesseract",
    )

    # OCR language fallback chain: ind+eng -> eng -> none
    RECEIPT_OCR_LANG: str = os.environ.get("RECEIPT_OCR_LANG", "ind+eng")


    # ---- AI vision provider dispatch ----
    # Provider selector: "openai" (default), "gemini", "ollama" (rollback),
    # or "none" (Tesseract only). Empty/disabled means AI off -> Tesseract only.
    RECEIPT_AI_ENABLED: bool = os.environ.get(
        "RECEIPT_AI_ENABLED", "true").lower() in ("1", "true", "yes")
    RECEIPT_AI_PROVIDER: str = os.environ.get(
        "RECEIPT_AI_PROVIDER", "openai").strip().lower()

    # ---- Native Ollama (moondream:1.8b-v2-q4_K_S on 127.0.0.1:11434) ----
    # Optional / rollback only. Not the default after cloud-provider support.
    OLLAMA_BASE_URL: str = os.environ.get(
        "OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    OLLAMA_VISION_MODEL: str = os.environ.get(
        "OLLAMA_VISION_MODEL", "moondream:1.8b-v2-q4_K_S")
    OLLAMA_TIMEOUT_SECONDS: float = float(
        os.environ.get("OLLAMA_TIMEOUT_SECONDS", "60"))
    OLLAMA_NUM_CTX: int = int(os.environ.get("OLLAMA_NUM_CTX", "2048"))
    OLLAMA_MAX_IMAGE_BYTES: int = int(
        os.environ.get("OLLAMA_MAX_IMAGE_BYTES", str(2 * 1024 * 1024)))

    # ---- OpenAI (cloud vision) ----
    OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_BASE_URL: str = os.environ.get(
        "OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_TIMEOUT_SECONDS: float = float(
        os.environ.get("OPENAI_TIMEOUT_SECONDS", "60"))

    # ---- Gemini / Google AI Studio (cloud vision, OpenAI-compatible endpoint) ----
    GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    # OpenAI-compatible shim for Gemini. Override for private/enterprise endpoints.
    GEMINI_BASE_URL: str = os.environ.get(
        "GEMINI_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai/")
    GEMINI_TIMEOUT_SECONDS: float = float(
        os.environ.get("GEMINI_TIMEOUT_SECONDS", "60"))

    # ---- Shared image-preprocessing + cross-check knobs (used by all providers) ----
    RECEIPT_AI_FALLBACK_TESSERACT: bool = os.environ.get(
        "RECEIPT_AI_FALLBACK_TESSERACT", "1").lower() in ("1", "true", "yes")
    RECEIPT_AI_MAX_IMAGE_WIDTH: int = int(
        os.environ.get("RECEIPT_AI_MAX_IMAGE_WIDTH", "1280"))
    RECEIPT_AI_JPEG_QUALITY: int = int(
        os.environ.get("RECEIPT_AI_JPEG_QUALITY", "80"))
    RECEIPT_CROSSCHECK_TESSERACT: bool = os.environ.get(
        "RECEIPT_CROSSCHECK_TESSERACT", "1").lower() in ("1", "true", "yes")
    RECEIPT_RAW_TEXT_MAX_CHARS: int = int(
        os.environ.get("RECEIPT_RAW_TEXT_MAX_CHARS", "4000"))

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
