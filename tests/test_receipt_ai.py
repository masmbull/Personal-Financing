"""Unit tests for the cloud AI-vision receipt scanner (OpenAI/Gemini).

These never touch a live cloud API - they verify the pure parsing and
encoding helpers plus the graceful-unavailable path. Provider injection is
used instead of HTTP mocks where possible.
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
    def test_money_coercion_none_bool_and_garbage(self):
        # Money fields go through parse_id_money: None/bools/garbage -> None
        # (never raises), and Indonesian thousands separators are honoured.
        out = ai._clean_items([{"name": "A", "quantity": True,
                                "unit_price": "25.000",
                                "total_price": "not-a-number"}])
        assert len(out) == 1
        assert out[0].quantity is None
        assert out[0].unit_price == 25000  # "25.000" == 25000 in IDR format
        assert out[0].total_price is None

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


class _FakeProvider:
    """Minimal vision provider: injectable so no HTTP mocking is needed."""

    def __init__(self, data, name="openai"):
        self._data = data
        self.name = name

    def extract(self, image_b64):
        return self._data


class TestScanResultCoercion:
    def test_scan_builds_receipt_scan_result(self, monkeypatch):
        fake = {"merchant": "Indomaret", "date": "2026-08-31",
                "time": "14:22", "total_amount": 17500, "subtotal": 17500,
                "tax": None, "discount": None, "payment_method": "DEBIT",
                "items": [{"name": "Susu", "quantity": 1,
                           "unit_price": 17500, "total_price": 17500}]}
        svc = ai.CloudReceiptScannerService(provider=_FakeProvider(fake))
        monkeypatch.setattr(
            ai, "_image_to_b64", lambda p: "data:image/jpeg;base64,xxx")

        res = svc.scan("some.jpg")
        assert isinstance(res, ReceiptScanResult)
        assert res.status == "processed"
        assert res.engine == "cloud-openai"
        assert res.merchant == "Indomaret"
        assert res.total_amount == 17500
        assert res.payment_method == "DEBIT"
        assert len(res.items) == 1
        assert res.items[0].name == "Susu"
        assert res.confidence in ("HIGH", "MEDIUM", "LOW")


class TestNever500OnBadModelData:
    def test_malformed_items_still_return_processed(self, monkeypatch):
        # Model returned garbage that compute_confidence would choke on; the
        # scanner must degrade (processed/LOW) and NEVER bubble a 500.
        fake = {"merchant": "X", "total_amount": 100,
                "items": [{"name": "A", "total_price": "not-a-number"}]}
        svc = ai.CloudReceiptScannerService(provider=_FakeProvider(fake))
        monkeypatch.setattr(ai, "_image_to_b64", lambda p: "data:x")
        # Force the result-build path to raise so the degrade branch is hit.
        monkeypatch.setattr(
            __import__("app.services.receipt_ocr", fromlist=["compute_confidence"]),
            "compute_confidence",
            lambda r: (_ for _ in ()).throw(RuntimeError("boom")))

        res = svc.scan("x.jpg")
        assert res.status == "processed"
        assert res.confidence == "LOW"
        assert res.merchant == "X"
        assert res.total_amount == 100


class TestUnavailable:
    def test_get_cloud_scanner_returns_none_without_key(self, monkeypatch):
        # Missing API key must degrade to "no cloud scanner", never raise.
        for provider, key in (("openai", "OPENAI_API_KEY"),
                              ("gemini", "GEMINI_API_KEY")):
            monkeypatch.setattr(ai.settings, "RECEIPT_AI_PROVIDER", provider)
            monkeypatch.setattr(ai.settings, key, "")
            assert ai.get_cloud_scanner() is None
