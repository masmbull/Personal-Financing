"""Optional AI-vision receipt scanner (Ollama / OpenAI-compatible endpoint).

Runs as the preferred OCR engine when a local Ollama instance is reachable
and serving the configured vision model. It reads the receipt image directly
(as a model with vision support), produces structured fields in one shot, and
is dramatically more accurate on rotated, noisy, small-print, or multi-line
Indonesian receipts than the Tesseract + regex pipeline.

Designed as a drop-in ``ReceiptScannerService``: ``scan()`` returns a
``ReceiptScanResult`` and NEVER creates a transaction. When the endpoint or
model is unavailable, resolution falls back to the Tesseract path (see
``receipt_ocr.build_scanner``).

Requires no new dependency: uses ``httpx`` (already in requirements).
"""
import base64
import io
import json
import re

import httpx

from app.config import settings


def _image_to_b64(image_path) -> str:
    """Read + downscale an image and return a base64 data-URI (JPEG)."""
    from PIL import Image
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        max_w = settings.RECEIPT_AI_MAX_IMAGE_WIDTH
        if img.width > max_w:
            r = max_w / img.width
            img = img.resize((max_w, int(img.height * r)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# One-shot structured receipt extraction prompt. Ask for the exact fields the
# rest of the app consumes (matching ReceiptScanResult) and strict JSON so the
# parser never needs to guess.
_SYSTEM_PROMPT = (
    "You are a precise Indonesian receipt (struk) data extractor. "
    "Read the receipt image and return ONLY valid JSON with no commentary and "
    "no markdown fences. Every monetary value is an integer in Indonesian "
    "Rupiah (remove '.' thousands separators, e.g. 25.000 -> 25000). "
    'Use this exact schema: {"merchant": string|null, "date": "YYYY-MM-DD"|null, '
    '"time": "HH:MM"|null, "total_amount": int|null, "subtotal": int|null, '
    '"tax": int|null, "discount": int|null, '
    '"payment_method": "TUNAI"|"DEBIT"|"KREDIT"|"QRIS"|null, '
    '"items": [{"name": string, "quantity": int|null, "unit_price": int|null, '
    '"total_price": int|null}]}. '
    "total_amount is the final amount paid. If a field is unreadable use null. "
    "Extract as many line items as are visible."
)


def _extract_json(reply: str):
    """Pull the first JSON object out of a model reply (strips fences/text)."""
    text = (reply or "").strip()
    # Drop markdown fences if the model wrapped the JSON anyway
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    # Try direct parse first (handles clean JSON replies)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    # Greedy fallback for mixed content
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON object in model reply")
    return json.loads(m.group(0))


def _clean_items(items):
    from app.services.receipt_ocr import ReceiptItem
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()
        if not name:
            continue
        out.append(ReceiptItem(
            name=name,
            quantity=it.get("quantity"),
            unit_price=it.get("unit_price"),
            total_price=it.get("total_price"),
        ))
    return out


class AIVisionReceiptScannerService:
    """ReceiptScannerService backed by an OpenAI-compatible vision endpoint."""

    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = (base_url or settings.RECEIPT_AI_BASE_URL).rstrip("/")
        self.model = model or settings.RECEIPT_AI_MODEL
        self.timeout = settings.RECEIPT_AI_TIMEOUT_SEC
        self._available = None  # lazily probed

    # ------------------------------------------------------- availability
    def available(self) -> bool:
        """True if the endpoint answers and the configured model exists."""
        if self._available is None:
            self._available = self._probe()
        return self._available

    def _probe(self) -> bool:
        try:
            r = httpx.get(
                f"{self.base_url}/models", timeout=min(self.timeout, 10))
            if r.status_code != 200:
                return False
            names = {m.get("id") for m in r.json().get("data", [])}
            return bool(names and (self.model in names or not names))
        except Exception:
            return False

    # ------------------------------------------------------- scanning
    def scan(self, image_path):
        from app.services.receipt_ocr import ReceiptScanResult, compute_confidence
        try:
            image_data = _image_to_b64(image_path)
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": [
                        {"type": "text",
                         "text": "Extract the receipt data from this image."},
                        {"type": "image_url",
                         "image_url": {"url": image_data}},
                    ]},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            }
            r = httpx.post(
                f"{self.base_url}/chat/completions",
                json=payload, timeout=self.timeout)
            r.raise_for_status()
            reply = r.json()["choices"][0]["message"]["content"]
            data = _extract_json(reply)
        except Exception:
            return ReceiptScanResult(status="failed")

        items = _clean_items(data.get("items"))
        result = ReceiptScanResult(
            merchant=_n(data.get("merchant")),
            date=_n(data.get("date")),
            time=_n(data.get("time")),
            total_amount=_int(data.get("total_amount")),
            subtotal=_int(data.get("subtotal")),
            tax=_int(data.get("tax")),
            discount=_int(data.get("discount")),
            payment_method=_n(data.get("payment_method")),
            items=items,
            raw_text=None,
            status="processed",
        )
        result.confidence = compute_confidence(result)
        return result


def _n(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _int(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _probe_service():
    """Return a ready AI vision service, or None if unavailable."""
    svc = AIVisionReceiptScannerService()
    return svc if svc.available() else None

