"""Unit tests for the optional AI-vision receipt scanner.

These never touch a live Ollama instance - they verify the pure parsing and
encoding helpers plus the graceful-unavailable path. Live endpoint tests are
left to test_real.py against a running Ollama.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.services import receipt_ai as ai
from app.services.receipt_ocr import ReceiptScanResult


class TestExtractJson:
    def test_plain_object(self):
        assert ai._extract_json('{"total_amount": 25000}') == {"total_amount": 25000}

    def test_markdown_fence(self):
        assert ai._extract_json(
            '```json\n{"merchant": "Indomaret"}\n```') == {"merchant": "Indomaret"}

    def test_text_before_and_after(self):
        assert ai._extract_json(
            'Here you go: {"date": "2026-08-31"} hope that helps') == {
                "date": "2026-08-31"}

    def test_no_json_raises(self):
        with pytest.raises(ValueError):
            ai._extract_json("sorry, could not read the image")


class TestCoercion:
    def test_int_none_and_bool(self):
        assert ai._int(None) is None
        assert ai._int(True) is None
        assert ai._int("25000") == 25000
        assert ai._int("25.000") is None  # not a valid int string

    def test_n_strips_whitespace(self):
        assert ai._n("  Indomaret  ") == "Indomaret"
        assert ai._n("") is None
        assert ai._n(None) is None

    def test_clean_items_filters_empty_names(self):
        items = [{"name": "Air Mineral", "quantity": 2, "unit_price": 3000,
                  "total_price": 6000},
                 {"name": "  ", "quantity": 1, "unit_price": 100, "total_price": 100},
                 "not-a-dict"]
        out = ai._clean_items(items)
        assert len(out) == 1
        assert out[0].name == "Air Mineral"
        assert out[0].total_price == 6000


class TestScanResultCoercion:
    def test_scan_builds_receipt_scan_result(self, monkeypatch):
        svc = ai.AIVisionReceiptScannerService(
            base_url="http://test.invalid/v1", model="m")
        svc._available = True  # bypass probing

        fake = {"merchant": "Indomaret", "date": "2026-08-31",
                "time": "14:22", "total_amount": 17500, "subtotal": 17500,
                "tax": None, "discount": None, "payment_method": "DEBIT",
                "items": [{"name": "Susu", "quantity": 1,
                           "unit_price": 17500, "total_price": 17500}]}
        monkeypatch.setattr(
            ai.httpx, "post",
            lambda *a, json=None, timeout=None, **k: _FakeResp(200, {
                "choices": [{"message": {"content": '{"merchant": '
                                                    '"Indomaret","date": "2026-08-31",'
                                                    '"time": "14:22","total_amount": 17500,'
                                                    '"subtotal": 17500,"tax": null,'
                                                    '"discount": null,"payment_method": "DEBIT",'
                                                    '"items": [{"name": "Susu","quantity": 1,'
                                                    '"unit_price": 17500,"total_price": 17500}]}'}}]}))
        monkeypatch.setattr(ai, "_image_to_b64", lambda p: "data:image/jpeg;base64,xxx")

        res = svc.scan("some.jpg")
        assert isinstance(res, ReceiptScanResult)
        assert res.status == "processed"
        assert res.merchant == "Indomaret"
        assert res.total_amount == 17500
        assert res.payment_method == "DEBIT"
        assert len(res.items) == 1
        assert res.items[0].name == "Susu"
        assert res.confidence in ("HIGH", "MEDIUM", "LOW")


class _FakeResp:
    def __init__(self, status, body):
        self._b = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._b


class TestUnavailable:
    def test_probe_service_returns_none_when_offline(self):
        # No Ollama on this machine -> probe quickly fails -> None.
        assert ai._probe_service() is None
