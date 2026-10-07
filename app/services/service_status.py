"""Runtime service status for the admin panel.

Probes the host's runtime dependencies and reports online/offline/disabled.
Side-effect free: nothing is written to the DB, and no secret (API key,
token) is ever returned - only presence/absence is reported. Every probe is
isolated so one failure cannot blank the whole page.

Callers gate access (admin only) - this module performs no auth.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text

from app.config import settings

log = logging.getLogger(__name__)

ONLINE = "online"
OFFLINE = "offline"
DISABLED = "disabled"


def _svc(name: str, category: str, status: str, detail: str = "") -> dict:
    return {"name": name, "category": category, "status": status, "detail": detail}


def _probe_database(db) -> dict:
    """Core: the DB answers a trivial query (same probe as /health/ready)."""
    try:
        db.execute(text("SELECT 1")).scalar()
        return _svc("Database", "core", ONLINE, "SELECT 1 ok")
    except Exception as e:  # noqa: BLE001 - report, never raise
        return _svc("Database", "core", OFFLINE, type(e).__name__)


def _probe_disk() -> dict:
    """Core: the data dir is writable (receipts/uploads live there)."""
    data_dir = Path("data")
    probe = data_dir / ".service_probe"
    try:
        data_dir.mkdir(exist_ok=True)
        probe.write_text("ok")
        probe.unlink()
        return _svc("Penyimpanan disk", "core", ONLINE, str(data_dir.resolve()))
    except OSError as e:
        return _svc("Penyimpanan disk", "core", OFFLINE, type(e).__name__)


def _probe_tesseract() -> dict:
    """OCR: local Tesseract binary present (fallback receipt engine)."""
    try:
        from app.services.receipt_ocr import _available_langs, _tesseract_available

        if _tesseract_available():
            langs = _available_langs()
            return _svc("Tesseract OCR", "ocr", ONLINE,
                        "lang: " + (", ".join(langs) or "-"))
        return _svc("Tesseract OCR", "ocr", OFFLINE, "binary tidak ditemukan")
    except Exception as e:  # noqa: BLE001
        return _svc("Tesseract OCR", "ocr", OFFLINE, type(e).__name__)


def _probe_ollama() -> dict:
    """AI: native Ollama endpoint + vision model reachable."""
    try:
        from app.services.receipt_ollama import OllamaClient

        client = OllamaClient(timeout=3)
        ok, reason = client.ping()
        detail = (f"{client.base_url} · model {client.model}" if ok
                  else f"{client.base_url} · {reason}")
        return _svc("Ollama endpoint", "ai", ONLINE if ok else OFFLINE, detail)
    except Exception as e:  # noqa: BLE001
        return _svc("Ollama endpoint", "ai", OFFLINE, type(e).__name__)


def _probe_ai_provider() -> dict:
    """AI: the selected cloud vision provider (key presence only, no call)."""
    provider = settings.RECEIPT_AI_PROVIDER
    label = f"AI Vision ({provider})"
    if not settings.RECEIPT_AI_ENABLED or provider == "none":
        return _svc(label, "ai", DISABLED, "AI nonaktif / provider none")
    if provider == "ollama":
        return _probe_ollama()
    if provider in ("openai", "gemini"):
        try:
            from app.services.receipt_ai import _default_provider, ProviderNotConfigured

            _default_provider()
            return _svc(label, "ai", ONLINE, "API key tersedia")
        except ProviderNotConfigured:
            return _svc(label, "ai", OFFLINE, "API key belum diset")
        except Exception as e:  # noqa: BLE001
            return _svc(label, "ai", OFFLINE, type(e).__name__)
    return _svc(label, "ai", OFFLINE, f"provider {provider!r} tidak dikenal")


def collect_service_status(db) -> list[dict]:
    """Return the status of every runtime dependency (newest form, no secrets)."""
    services = [
        _probe_database(db),
        _probe_disk(),
        _probe_ai_provider(),
        _probe_tesseract(),
    ]
    # Surface Ollama separately unless it is already the selected provider.
    if settings.RECEIPT_AI_PROVIDER != "ollama":
        services.append(_probe_ollama())
    return services