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

    # Optional AI vision OCR engine. Preferred over Tesseract when the
    # endpoint+model respond; otherwise local path is kept.
    # Back-compat: these stay as defaults; Ollama scanner reads OLLAMA_*
    # below.
    RECEIPT_AI_BASE_URL: str = os.environ.get(
        "RECEIPT_AI_BASE_URL", "http://localhost:11434/v1")
    RECEIPT_AI_MODEL: str = os.environ.get(
        "RECEIPT_AI_MODEL", "llama3.2-vision")
    RECEIPT_AI_TIMEOUT_SEC: float = float(
        os.environ.get("RECEIPT_AI_TIMEOUT_SEC", "120"))
    RECEIPT_AI_FALLBACK_TESSERACT: bool = os.environ.get(
        "RECEIPT_AI_FALLBACK_TESSERACT", "1").lower() in ("1", "true", "yes")
    RECEIPT_AI_MAX_IMAGE_WIDTH: int = int(
        os.environ.get("RECEIPT_AI_MAX_IMAGE_WIDTH", "1280"))
    # JPEG quality for the temporary downscaled inference image (higher keeps
    # more small text, larger bytes; 80 is the documented low-RAM default).
    RECEIPT_AI_JPEG_QUALITY: int = int(
        os.environ.get("RECEIPT_AI_JPEG_QUALITY", "80"))

    # ---- AI vision provider dispatch (PHASE: Ollama integration) ----
    # Provider selector: "ollama" (native /api/chat) or "openai_compat"
    # (/v1/chat/completions). Empty/disabled means AI off -> Tesseract only.
    RECEIPT_AI_ENABLED: bool = os.environ.get(
        "RECEIPT_AI_ENABLED", "true").lower() in ("1", "true", "yes")
    RECEIPT_AI_PROVIDER: str = os.environ.get(
        "RECEIPT_AI_PROVIDER", "ollama").strip().lower()

    # ---- Native Ollama (moondream:1.8b-v2-q4_K_S on 127.0.0.1:11434) ----
    # Production default (STANDARBENGKEL: ~3.6 GiB RAM, CPU-only, no GPU):
    # moondream 1.8b Q4_K_S is the vision model. qwen2.5vl:3b pushed the box
    # to ~99% RAM + swap, so it is NOT the production default. The model is a
    # runtime env var on purpose - never hardcode it into pipeline code.
    # Ollama runs on the HOST machine, NOT in a container - inside Docker
    # this 127.0.0.1 would point at the container itself. Production here
    # uses systemd (not Docker) so 127.0.0.1 reaches the host's Ollama.
    # If/when containerised, override with host.docker.internal:11434
    # (Docker Desktop) or the bridge gateway (e.g. 172.17.0.1:11434).
    OLLAMA_BASE_URL: str = os.environ.get(
        "OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    OLLAMA_VISION_MODEL: str = os.environ.get(
        "OLLAMA_VISION_MODEL", "moondream:1.8b-v2-q4_K_S")
    OLLAMA_TIMEOUT_SECONDS: float = float(
        os.environ.get("OLLAMA_TIMEOUT_SECONDS", "60"))
    # num_ctx bounds KV-cache RAM on a 3.6 GB box; 2048 is enough for one
    # receipt image + a short JSON reply.
    OLLAMA_NUM_CTX: int = int(os.environ.get("OLLAMA_NUM_CTX", "2048"))
    # Max base64 size we'll send (~2 MB raw -> ~2.7 MB base64). Anything
    # larger falls back to Tesseract to avoid OOM in Ollama.
    OLLAMA_MAX_IMAGE_BYTES: int = int(
        os.environ.get("OLLAMA_MAX_IMAGE_BYTES", str(2 * 1024 * 1024)))

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
