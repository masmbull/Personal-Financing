"""Tests for the native Ollama (moondream:1.8b-v2-q4_K_S) receipt scanner.

These never require a live Ollama instance: HTTP is mocked. A separate
optional live smoke test lives in tests/test_ollama_integration.py and only
runs when OLLAMA_INTEGRATION_TEST=1.

Covered: successful extraction, valid JSON coercion, malformed JSON,
unavailable/timeout/model-missing -> graceful failure, negative & over-limit
amounts rejected, missing fields stay null, ownership/IDOR protection, the
AI scan NEVER creates a transaction, explicit confirmation is still required,
duplicate detection, the full upload->scan->confirm flow, and the per-scan
fallback chain.
"""
import json
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import pytest
from PIL import Image

from app.config import settings
from app.models.models import Receipt, Transaction, User
from app.services import receipt_ollama as oa
from app.services import receipts as receipts_service
from app.services.finance import MAX_TX_AMOUNT
from app.services.receipt_ocr import (
    FallbackReceiptScannerService,
    OfflineReceiptScannerService,
    ReceiptScanResult,
    TesseractReceiptScannerService,
)
from tests.conftest import (
    PNG_BYTES, _default_user_ctx, client, default_user_id,
    TestingSessionLocal, DEFAULT_USER_2,
)


# ----------------------------------------------------------- fakes
class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {}

    def json(self):
        return self._body


class FakeClient:
    """Mimics the bits of httpx.Client we use (get/post returning FakeResp)."""

    def __init__(self, get_resp=None, post_resp=None,
                 get_raises=None, post_raises=None):
        self.get_resp = get_resp
        self.post_resp = post_resp
        self.get_raises = get_raises
        self.post_raises = post_raises
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(("get", url))
        if self.get_raises:
            raise self.get_raises
        return self.get_resp

    def post(self, url, json=None, timeout=None):
        self.calls.append(("post", url))
        if self.post_raises:
            raise self.post_raises
        return self.post_resp


class FakeOllamaClient:
    """Injectable stand-in for OllamaClient passed straight to the scanner."""

    def __init__(self, chat_result=None, chat_raises=None, ping=(False, "x")):
        self.chat_result = chat_result
        self.chat_raises = chat_raises
        self.ping = ping
        self.chat_calls = 0

    def chat(self, image_b64):
        self.chat_calls += 1
        if self.chat_raises is not None:
            raise self.chat_raises
        return self.chat_result


GOOD_DICT = {
    "merchant": "Indomaret", "date": "2026-08-31", "time": "14:22",
    "total_amount": 17500, "subtotal": 17500, "tax": None, "discount": None,
    "payment_method": "DEBIT",
    "items": [{"name": "Susu", "quantity": 1, "unit_price": 17500,
               "total_price": 17500}],
    "confidence": 0.9,
}


@pytest.fixture
def tmp_png(tmp_path: Path) -> str:
    p = tmp_path / "receipt.png"
    Image.new("RGB", (40, 40), (255, 255, 255)).save(p, format="PNG")
    return str(p)


# ----------------------------------------------------------- helpers
from contextlib import contextmanager


@contextmanager
def _mock_ollama(monkeypatch, content_dict):
    """Force the Ollama engine ACTIVE with a fully mocked HTTP client.

    Within the ``with`` block the production ``build_scanner()`` chain sees
    RECEIPT_AI_ENABLED=ollama and its HTTP layer is a FakeClient that
    answers every /api/chat call with ``content_dict`` serialized as the
    model's text reply. ``yield`` hands the fake back for call counting.
    Outside the block everything is restored so the rest of the suite
    stays Ollama-free.
    """
    content = json.dumps(content_dict)
    fake = FakeClient(post_resp=FakeResp(
        200, {"message": {"content": content}}))
    monkeypatch.setattr(oa, "_client", lambda: fake)
    monkeypatch.setattr(settings, "RECEIPT_AI_ENABLED", True)
    monkeypatch.setattr(settings, "RECEIPT_AI_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "RECEIPT_AI_FALLBACK_TESSERACT", False)
    import app.services.receipt_ocr as ro
    ro._scanner = None
    oa._reset_for_tests()
    try:
        yield fake
    finally:
        ro._scanner = None
        oa._reset_for_tests()
# ----------------------------------------------------------- 1/2 success + coercion
def test_successful_extraction_via_mock(tmp_png):
    svc = oa.OllamaVisionReceiptScannerService(
        client=FakeOllamaClient(chat_result=GOOD_DICT))
    res = svc.scan(tmp_png)
    assert isinstance(res, ReceiptScanResult)
    assert res.status == "processed"
    assert res.merchant == "Indomaret"
    assert res.total_amount == 17500
    assert res.payment_method == "DEBIT"
    assert len(res.items) == 1
    assert res.items[0].name == "Susu"
    assert res.items[0].total_price == 17500
    assert res.confidence in ("HIGH", "MEDIUM", "LOW")


def test_valid_json_coercion():
    assert oa._int("25000") == 25000
    assert oa._int(25000.0) == 25000
    assert oa._int(True) is None
    assert oa._int("25.000") is None  # thousands separator must be dropped by model
    assert oa._int(None) is None
    val, err = oa._money("5000")
    assert val == 5000 and err is None
    # Date / time formatting enforced
    assert oa._validate_date("2026-02-30")[1] is not None  # impossible date
    assert oa._validate_date("2026-12-01") == ("2026-12-01", None)
    assert oa._validate_date("2026-13-01")[1] is not None
    assert oa._validate_time("14:22") == ("14:22", None)
    assert oa._validate_time("14:22:03") == ("14:22:03", None)
    assert oa._validate_time("1422")[1] is not None


def test_string_int_total_coerced(tmp_png):
    svc = oa.OllamaVisionReceiptScannerService(
        client=FakeOllamaClient(chat_result={**GOOD_DICT, "total_amount": "17500"}))
    res = svc.scan(tmp_png)
    assert res.status == "processed"
    assert res.total_amount == 17500


# ----------------------------------------------------------- 3 malformed JSON
def test_malformed_json_falls_back(monkeypatch, tmp_png):
    fake = FakeClient(post_resp=FakeResp(
        200, {"message": {"content": "sorry, cannot read the image"}}))
    monkeypatch.setattr(oa, "_client", lambda: fake)
    svc = oa.OllamaVisionReceiptScannerService()
    res = svc.scan(tmp_png)
    assert res.status == "failed"
    assert res.error == "bad_response"


# ----------------------------------------------------------- 4/5/6 infra failures
def test_unavailable_when_connection_refused(monkeypatch):
    monkeypatch.setattr(oa, "_client",
                        lambda: FakeClient(get_raises=httpx.ConnectError("refused")))
    ok, reason = oa.OllamaClient().ping()
    assert ok is False
    assert "connect_failed" in reason
    assert oa.probe_service() is None


def test_model_missing_from_tags(monkeypatch):
    fake = FakeClient(get_resp=FakeResp(200, {"models": [{"name": "llama3.2"}]}))
    monkeypatch.setattr(oa, "_client", lambda: fake)
    svc = oa.OllamaVisionReceiptScannerService()
    assert svc.available() is False
    assert oa.probe_service() is None


def test_model_present_probes_ok(monkeypatch):
    fake = FakeClient(get_resp=FakeResp(
        200, {"models": [{"name": "moondream:1.8b-v2-q4_K_S"}]}))
    monkeypatch.setattr(oa, "_client", lambda: fake)
    svc = oa.OllamaVisionReceiptScannerService()
    assert svc.available() is True
    assert oa.probe_service() is not None


def test_scan_timeout_falls_back(tmp_png):
    svc = oa.OllamaVisionReceiptScannerService(
        client=FakeOllamaClient(chat_raises=httpx.TimeoutException("t")))
    res = svc.scan(tmp_png)
    assert res.status == "failed"
    assert res.error == "timeout"


# ----------------------------------------------------------- 7/8 amount guards
def test_negative_amount_rejected(tmp_png):
    svc = oa.OllamaVisionReceiptScannerService(
        client=FakeOllamaClient(chat_result={"total_amount": -5000}))
    res = svc.scan(tmp_png)
    assert res.status == "failed"
    assert "total_amount" in (res.error or "")


def test_amount_over_max_rejected(tmp_png):
    svc = oa.OllamaVisionReceiptScannerService(
        client=FakeOllamaClient(chat_result={"total_amount": MAX_TX_AMOUNT + 1}))
    res = svc.scan(tmp_png)
    assert res.status == "failed"
    assert "MAX_TX_AMOUNT" in (res.error or "")


# ----------------------------------------------------------- 9 missing -> null
def test_missing_fields_stay_null(tmp_png):
    svc = oa.OllamaVisionReceiptScannerService(
        client=FakeOllamaClient(chat_result={}))
    res = svc.scan(tmp_png)
    assert res.status == "processed"
    assert res.merchant is None
    assert res.total_amount is None
    assert res.date is None
    assert res.items == []
    assert res.payment_method is None


def test_unknown_payment_method_not_invented(tmp_png):
    svc = oa.OllamaVisionReceiptScannerService(
        client=FakeOllamaClient(chat_result={"payment_method": "BITCOIN"}))
    res = svc.scan(tmp_png)
    # Non-whitelisted payment method is dropped to null, not stored blindly.
    assert res.payment_method is None


# ----------------------------------------------------------- app helpers
def _tx_count() -> int:
    db = TestingSessionLocal()
    try:
        return db.query(Transaction).count()
    finally:
        db.close()


def _acc_id(name: str) -> int:
    items = client.get("/api/v1/accounts").json()["items"]
    return next(a["id"] for a in items if a["name"] == name)


def _cat_id(name: str) -> int:
    items = client.get("/api/v1/categories").json()["items"]
    return next(c["id"] for c in items if c["name"] == name)


CONFIRM_PAYLOAD = {
    "type": "EXPENSE", "amount": 17500, "date": "2026-08-31",
    "merchant": "Indomaret",
}


# ----------------------------------------------------------- 13 fallback chain
def test_composite_falls_through_to_local_engine(tmp_png):
    """When the preferred (Ollama) engine fails at scan time the fallback
    composite must transparently try the next local engine."""

    class _Failed:
        def scan(self, image_path):
            return ReceiptScanResult(status="failed", error="transport")

    class _Local:
        def scan(self, image_path):
            return ReceiptScanResult(status="processed", merchant="Warung",
                                     total_amount=5000)

    svc = FallbackReceiptScannerService([_Failed(), _Local()])
    res = svc.scan(tmp_png)
    assert res.status == "processed"
    assert res.merchant == "Warung"


def test_composite_returns_failed_when_all_engines_fail(tmp_png):
    class _Failed:
        def scan(self, image_path):
            return ReceiptScanResult(status="failed", error="timeout")

    res = FallbackReceiptScannerService([_Failed()]).scan(tmp_png)
    assert res.status == "failed"
    assert res.error == "timeout"


# ----------------------------------------------------------- 11 AI never posts
def test_ai_scan_does_not_create_transaction(monkeypatch, client):
    before = _tx_count()
    with _mock_ollama(monkeypatch, GOOD_DICT):
        r = client.post("/api/v1/receipts",
                        files={"file": ("struk.png", PNG_BYTES, "image/png")})
        assert r.status_code == 201, r.text
        body = r.json()
        # The AI draft is stored and visible for REVIEW...
        assert body["status"] == "ready"
        assert body["transaction_id"] is None
        assert body["ocr"]["merchant"] == "Indomaret"
        assert body["ocr"]["total_amount"] == 17500
    # ...but OCR never auto-created a transaction.
    assert _tx_count() == before


# ----------------------------------------------------------- 12/15 confirm flow
def test_full_upload_review_confirm_creates_exactly_one_transaction(
        monkeypatch, client):
    with _mock_ollama(monkeypatch, GOOD_DICT):
        rid = client.post("/api/v1/receipts",
                          files={"file": ("struk.png", PNG_BYTES, "image/png")}
                          ).json()["receipt_id"]

    # Review: the draft is served to the OWNER only and is unlinked.
    got = client.get(f"/api/v1/receipts/{rid}")
    assert got.status_code == 200
    got = got.json()
    assert got["ocr"]["merchant"] == "Indomaret"
    assert got["transaction_id"] is None

    # Explicit human confirmation (values come from the request body).
    payload = {**CONFIRM_PAYLOAD,
               "account_id": _acc_id("BCA"), "category_id": _cat_id("Makan & Minum")}
    r = client.post(f"/api/v1/receipts/{rid}/confirm", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["ocr_status"] == "confirmed"
    assert r.json()["transaction_id"] is not None

    # Exactly one transaction exists and the receipt is linked to it.
    assert _tx_count() == 1
    db = TestingSessionLocal()
    try:
        tx = db.query(Transaction).filter_by(amount=17500).first()
        assert tx is not None and tx.merchant == "Indomaret"
        rec = db.query(Receipt).filter(Receipt.id == rid).first()
        assert rec.transaction_id == tx.id
    finally:
        db.close()

    # A second confirm is rejected -> never a second transaction.
    assert client.post(f"/api/v1/receipts/{rid}/confirm",
                       json=payload).status_code == 409
    assert _tx_count() == 1


# ----------------------------------------------------------- 14 duplicate detection
def test_duplicate_detection_still_works(monkeypatch, client):
    with _mock_ollama(monkeypatch, GOOD_DICT):
        rid1 = client.post("/api/v1/receipts",
                           files={"file": ("a.png", PNG_BYTES, "image/png")}
                           ).json()["receipt_id"]
        rid2 = client.post("/api/v1/receipts",
                           files={"file": ("b.png", PNG_BYTES, "image/png")}
                           ).json()["receipt_id"]
    assert rid1 != rid2
    db = TestingSessionLocal()
    try:
        r2 = db.query(Receipt).filter(Receipt.id == rid2).first()
        dup = receipts_service.duplicate_for(db, r2, default_user_id())
        assert dup is not None and dup.id == rid1
    finally:
        db.close()


# ----------------------------------------------------------- 10 ownership / IDOR
def test_idor_ownership_still_protected(monkeypatch, client):
    """Alice's AI-scanned receipt is invisible to Bob on read AND confirm."""
    from app.api.deps import get_current_user
    from app.main import app

    bob_id = default_user_id()
    db = TestingSessionLocal()
    try:
        alice_id = db.query(User).filter(User.username == DEFAULT_USER_2).first().id
    finally:
        db.close()

    app.dependency_overrides[get_current_user] = lambda: _default_user_ctx(alice_id)
    try:
        with _mock_ollama(monkeypatch, GOOD_DICT):
            r = client.post("/api/v1/receipts",
                            files={"file": ("alice.png", PNG_BYTES, "image/png")})
            assert r.status_code == 201, r.text
            rid = r.json()["receipt_id"]
    finally:
        app.dependency_overrides[get_current_user] = lambda: _default_user_ctx(bob_id)

    assert client.get(f"/api/v1/receipts/{rid}").status_code == 404
    payload = {**CONFIRM_PAYLOAD,
               "account_id": _acc_id("BCA"), "category_id": _cat_id("Makan & Minum")}
    assert client.post(f"/api/v1/receipts/{rid}/confirm",
                       json=payload).status_code == 404
    # And Alice's scan created no transaction either.
    assert _tx_count() == 0


# ----------------------------------------------------------- scanner selection
def test_build_scanner_prioritizes_ollama_when_enabled(monkeypatch):
    import app.services.receipt_ocr as ro
    monkeypatch.setattr(settings, "RECEIPT_AI_ENABLED", True)
    monkeypatch.setattr(settings, "RECEIPT_AI_PROVIDER", "ollama")
    monkeypatch.setattr(ro, "_tesseract_available", lambda: False)
    ro._scanner = None
    try:
        svc = ro.build_scanner()
    finally:
        ro._scanner = None
    # AI chains are wrapped in CrossCheckReceiptScannerService for the
    # hybrid Vision+OCR enrichment; unwrap to inspect the inner engine.
    inner = getattr(svc, "inner", svc)
    engines = inner.engines if isinstance(inner, FallbackReceiptScannerService) \
        else [inner]
    assert engines and isinstance(engines[0], oa.OllamaVisionReceiptScannerService)


def test_build_scanner_excludes_ollama_when_disabled(monkeypatch):
    import app.services.receipt_ocr as ro
    monkeypatch.setattr(settings, "RECEIPT_AI_ENABLED", False)
    monkeypatch.setattr(settings, "RECEIPT_AI_PROVIDER", "ollama")
    monkeypatch.setattr(ro, "_tesseract_available", lambda: False)
    ro._scanner = None
    try:
        svc = ro.build_scanner()
    finally:
        ro._scanner = None
    if isinstance(svc, FallbackReceiptScannerService):
        assert all(not isinstance(e, oa.OllamaVisionReceiptScannerService)
                   for e in svc.engines)
    else:
        assert not isinstance(svc, oa.OllamaVisionReceiptScannerService)


# ------------------------------------------------------- low-RAM phase 11
def test_vision_model_is_configurable(monkeypatch):
    """The model must come from settings/env, never be hardcoded in code."""
    monkeypatch.setattr(settings, "OLLAMA_VISION_MODEL", "moondream:1.8b-v2-q4_K_S")
    assert oa.OllamaClient().model == "moondream:1.8b-v2-q4_K_S"
    monkeypatch.setattr(settings, "OLLAMA_VISION_MODEL", "custom:vision-1")
    assert oa.OllamaClient().model == "custom:vision-1"


def test_image_resized_and_jpeg_encoded(tmp_path):
    """Large receipt -> downscaled JPEG, aspect ratio kept, original untouched."""
    import base64 as b64mod
    import io as iomod
    big = tmp_path / "big_receipt.png"
    Image.new("RGB", (2400, 1200), "white").save(big, format="PNG")
    b64 = oa._image_to_b64(str(big))
    raw = b64mod.b64decode(b64)
    assert raw.startswith(b"\xff\xd8")  # JPEG SOI
    with Image.open(iomod.BytesIO(raw)) as im:
        assert im.format == "JPEG"
        assert im.width == settings.RECEIPT_AI_MAX_IMAGE_WIDTH == 1280
        assert 590 <= im.height <= 650  # ~half of 1200 with ratio preserved
    # The ORIGINAL file is unchanged in size and format.
    with Image.open(str(big)) as orig:
        assert orig.size == (2400, 1200)


def test_jpeg_quality_setting_applied(monkeypatch, tmp_path):
    import base64 as b64mod
    p = tmp_path / "q.png"
    Image.new("RGB", (400, 200), "green").save(p, format="PNG")
    monkeypatch.setattr(settings, "RECEIPT_AI_JPEG_QUALITY", 10)
    raw = b64mod.b64decode(oa._image_to_b64(str(p)))
    assert raw.startswith(b"\xff\xd8")
    # Still decodable at the low quality setting.
    import io as iomod
    with Image.open(iomod.BytesIO(raw)) as im:
        assert im.size == (400, 200)


def test_one_inference_at_a_time_lock():
    """The process-wide lock serializes vision inference (even single-node)."""
    import threading as _t
    oa._reset_for_tests()
    try:
        outcome = {}
        lock_holder = oa._ollama_lock(timeout=5)

        def _second():
            try:
                with oa._ollama_lock(timeout=0.3):
                    outcome["acquired"] = True
            except TimeoutError:
                outcome["acquired"] = False

        with lock_holder:
            t = _t.Thread(target=_second)
            t.start()
            t.join()
            assert outcome.get("acquired") is False  # blocked while held

        # After the first inference released, a new one can acquire.
        with oa._ollama_lock(timeout=2):
            pass
    finally:
        oa._reset_for_tests()