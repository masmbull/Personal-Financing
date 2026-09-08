"""OPTIONAL live smoke test against a real Ollama instance.

Only runs when OLLAMA_INTEGRATION_TEST=1 (skipped by default so CI and
plain ``pytest tests/`` never require a live model):

  * asserts the configured vision model (qwen2.5vl:3b) is present
    (GET /api/tags on OLLAMA_BASE_URL)
  * sends ONE small locally-generated receipt image through the real
    OllamaVisionReceiptScannerService
  * validates the structured reply against the app's server-side schema
  * asserts the scan itself NEVER created a transaction

Run with:

    OLLAMA_INTEGRATION_TEST=1 python -m pytest tests/test_ollama_integration.py -v
"""
import os

import pytest

if os.environ.get("OLLAMA_INTEGRATION_TEST") != "1":
    pytest.skip("set OLLAMA_INTEGRATION_TEST=1 to run the live Ollama smoke test",
                allow_module_level=True)

from app.config import settings  # noqa: E402
from app.services.receipt_ocr import ReceiptScanResult  # noqa: E402
from app.services.receipt_ollama import (  # noqa: E402
    OllamaClient, OllamaVisionReceiptScannerService,
)


def _make_fixture_receipt(path: str) -> None:
    """Render a tiny deterministic Indonesian-style receipt with PIL."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (640, 420), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 640, 420], outline="black")
    d.text((30, 30), "WARUNG BU SRI - STRUK", fill="black")
    d.text((30, 70), "Air Mineral 1x  Rp 5.000", fill="black")
    d.text((30, 110), "Kopi 1x  Rp 20.000", fill="black")
    d.text((30, 150), "TOTAL  Rp 25.000", fill="black")
    d.text((30, 190), "METODE: QRIS", fill="black")
    img.save(path, format="PNG")


def test_qwen_model_available():
    c = OllamaClient()
    ok, reason = c.ping()
    assert ok, f"Ollama not usable: {reason}"
    assert c.model == settings.OLLAMA_VISION_MODEL


def test_live_vision_scan_returns_valid_schema(tmp_path):
    img = tmp_path / "fixture_receipt.png"
    _make_fixture_receipt(str(img))

    svc = OllamaVisionReceiptScannerService()
    res = svc.scan(str(img))
    assert isinstance(res, ReceiptScanResult)
    assert res.status == "processed", f"scan failed: {res.error}"

    # Server-side validation already guaranteed these invariants; assert the
    # important ones here so a validation regression is visible immediately.
    if res.total_amount is not None:
        assert res.total_amount > 0
    if res.date is not None:
        import re
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", res.date)
    if res.payment_method is not None:
        from app.services.receipt_ollama import _ALLOWED_PM
        assert res.payment_method.upper() in _ALLOWED_PM
    assert res.confidence in ("HIGH", "MEDIUM", "LOW")

    # SMOKE-TEST CONTRACT: scanning NEVER creates a transaction - the scanner
    # only returns a plain draft for the human review/confirm step. Enforce
    # that this service has no transaction/DB surface at all.
    import inspect
    src = inspect.getsource(svc.scan)
    assert "create_transaction" not in src
    assert "db." not in src