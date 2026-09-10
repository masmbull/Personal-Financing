"""Cloud vision receipt providers for Personal-Financing.

Provider abstraction over OpenAI- and Gemini-compatible vision endpoints, plus a
thin scanner-service adapter so the app is agnostic to which cloud provider is
configured. The cloud model provides semantic extraction only; every result is
fed to the deterministic Indonesian post-processor in app/services/receipt_id.py.

Security: API keys from env only; never logged/returned. Images downscaled before
they leave the machine. Dependency: httpx (already in requirements.txt).
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
from abc import ABC, abstractmethod

import httpx

from app.config import settings

log = logging.getLogger(__name__)

class ProviderError(Exception):
    """Base class for cloud-provider failures (timeout, auth, transport)."""


class ProviderNotConfigured(ProviderError):
    """Raised when the provider is enabled but its API key is missing."""


def _image_to_b64(image_path) -> str:
    """Read + downscale + JPEG-encode an image; return a data-URI."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = 25_000_000
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        max_w = settings.RECEIPT_AI_MAX_IMAGE_WIDTH
        if img.width > max_w:
            r = max_w / img.width
            img = img.resize((max_w, int(img.height * r)), Image.LANCZOS)
        max_h = max_w * 4
        if img.height > max_h:
            img = img.crop((0, 0, img.width, max_h))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=settings.RECEIPT_AI_JPEG_QUALITY)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

def _extract_json(reply: str):
    """Pull the first JSON object out of a model reply (strips fences/text)."""
    text = (reply or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON object in model reply")
    return json.loads(m.group(0))

def _n(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _clean_items(raw):
    from app.services.receipt_ocr import ReceiptItem
    out = []
    for it in raw or []:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()
        if not name:
            continue
        def money(k):
            from app.services.receipt_id import parse_id_money
            n, _ = parse_id_money(it.get(k))
            return n
        out.append(ReceiptItem(
            name=name,
            quantity=money("quantity"),
            unit_price=money("unit_price"),
            total_price=money("total_price"),
            unit=str(it.get("unit") or "").strip()[:12] or None,
            sku=str(it.get("sku") or "").strip()[:64] or None,
            discount=money("discount"),
        ))
    return out

_SYSTEM_PROMPT = (
    "You are a precise Indonesian receipt (struk / nota) data extractor. "
    "Read the receipt image and return ONLY valid JSON, no commentary, no markdown. \n\n"
    "### Anti-hallucination rules (MANDATORY):\n"
    "- Extract ONLY information clearly visible in the image.\n"
    "- If a field is not visible/unreadable, return null. NEVER invent, infer, or guess.\n"
    "- NEVER invent merchant name, receipt number, date, price, line item, or payment method.\n"
    "- Copy product names exactly as printed; do not expand abbreviations.\n"
    "- QRIS is a payment METHOD. Do NOT infer GoPay/OVO/DANA from a QR code alone.\n"
    "- Set payment_provider ONLY if that provider name is explicitly visible.\n"
    "- Preserve uncertainty: faint/partial text -> null + rely on warnings.\n\n"
    "### Indonesian receipt terms to recognize:\n"
    "TOTAL, TOTAL BAYAR, BAYAR, SUBTOTAL, SUB TOTAL, JUMLAH, KEMBALI, KEMBALIAN, "
    "TUNAI, CASH, QRIS, DEBIT, KREDIT, KARTU, TRANSFER, "
    "GOPAY, OVO, DANA, SHOPEEPAY, LINKAJA, BCA, BRI, BNI, MANDIRI, "
    "PPN, PAJAK, SERVICE, SERVICE CHARGE, BIAYA LAYANAN, DISKON, PROMO, "
    "ONGKIR, DELIVERY, NO STRUK, NOTA, INVOICE, FAKTUR, QTY, HARGA, SATUAN.\n"
    "Dots are thousands separators in Rupiah: 25.000 -> 25000, 1.250.000 -> 1250000.\n"
    "All money = INTEGER Rupiah (no decimals, no Rp prefix).\n\n"
    "### Output JSON schema (use these exact keys):\n"
    "receipt_type: RETAIL_RECEIPT|RESTAURANT_RECEIPT|CAFE_RECEIPT|"
    "SUPERMARKET_RECEIPT|MINIMARKET_RECEIPT|FUEL_RECEIPT|WORKSHOP_RECEIPT|"
    "PHARMACY_RECEIPT|HOSPITAL_RECEIPT|HOTEL_RECEIPT|PARKING_RECEIPT|"
    "TOLL_RECEIPT|TRANSPORT_RECEIPT|UTILITY_RECEIPT|TELCO_RECEIPT|"
    "E_COMMERCE_RECEIPT|DELIVERY_RECEIPT|QRIS_PAYMENT_RECEIPT|"
    "BANK_PAYMENT_RECEIPT|E_WALLET_RECEIPT|OTHER_RECEIPT|UNKNOWN|null\n"
    "merchant: string|null\n"
    "merchant_address: string|null\nmerchant_phone: string|null\n"
    "receipt_number: string|null\ndate: YYYY-MM-DD|null\ntime: HH:MM|null\n"
    "currency: IDR\n"
    "subtotal, discount, tax, service_charge, delivery_fee, shipping_fee, "
    "rounding, other_fee, total_amount: int|null\n"
    "payment_method: TUNAI|DEBIT|KREDIT|QRIS|TRANSFER|E_WALLET|null\n"
    "payment_provider: GOPAY|OVO|DANA|SHOPEEPAY|LINKAJA|null\n"
    "qris: {is_qris: bool, merchant_name: string|null, merchant_id: string|null, "
    "reference_number: string|null, amount: int|null}\n"
    "fuel: {is_fuel: bool, product_name: string|null, quantity_liters: number|null, "
    "price_per_liter: int|null, total: int|null}\n"
    "line_items: [{name: string, sku: string|null, quantity: number|null, "
    "unit: string|null, unit_price: int|null, discount: int|null, tax: int|null, "
    "total: int|null}]\nwarnings: [string]\n\n"
    "total_amount is the FINAL paid amount. Extract as many line items as visible. "
    "If unsure about a value, return null instead of guessing."
)

def _build_payload(image_b64: str, model: str) -> dict:
    """OpenAI-vision chat-completions payload shared by OpenAI and Gemini."""
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": "Extract the receipt data from this image."},
                {"type": "image_url", "image_url": {"url": image_b64}},
            ]},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }

class BaseReceiptVisionProvider(ABC):
    """Abstract cloud vision provider."""
    name: str = "base"

    @abstractmethod
    def extract(self, image_b64: str) -> dict:
        """Send the image; return the parsed JSON dict from the model."""

    def _headers(self, api_key: str) -> dict:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "PersonalFinancing/1 (receipt-ocr)",
        }

class GeminiVisionProvider(BaseReceiptVisionProvider):
    """Gemini / Google AI Studio via an OpenAI-compatible endpoint."""
    name = "gemini"

    def __init__(self, api_key=None, model=None, base_url=None, timeout=None):
        key = api_key if api_key is not None else settings.GEMINI_API_KEY
        if not key:
            raise ProviderNotConfigured(
                "GEMINI_API_KEY is not set; cannot use Gemini vision provider")
        self.api_key = key
        self.model = model if model is not None else settings.GEMINI_MODEL
        self.base_url = (base_url if base_url is not None else settings.GEMINI_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.GEMINI_TIMEOUT_SECONDS

    def extract(self, image_b64: str) -> dict:
        url = f"{self.base_url}/chat/completions"
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(url, json=_build_payload(image_b64, self.model),
                           headers=self._headers(self.api_key))
        except httpx.TimeoutException as e:
            raise ProviderError(f"gemini timeout: {e}") from e
        except httpx.HTTPError as e:
            raise ProviderError(f"gemini transport error: {e}") from e
        if r.status_code in (401, 403):
            raise ProviderError("gemini auth failed (invalid API key)")
        if r.status_code == 429:
            raise ProviderError("gemini rate limited")
        if r.status_code != 200:
            raise ProviderError(f"gemini http {r.status_code}")
        try:
            reply = r.json()["choices"][0]["message"]["content"]
            return _extract_json(reply)
        except Exception as e:
            raise ProviderError(f"gemini bad response: {e}") from e

class OpenAIVisionProvider(BaseReceiptVisionProvider):
    """OpenAI vision API (gpt-4o / gpt-4o-mini / ...)."""
    name = "openai"

    def __init__(self, api_key=None, model=None, base_url=None, timeout=None):
        key = api_key if api_key is not None else settings.OPENAI_API_KEY
        if not key:
            raise ProviderNotConfigured(
                "OPENAI_API_KEY is not set; cannot use OpenAI vision provider")
        self.api_key = key
        self.model = model if model is not None else settings.OPENAI_MODEL
        self.base_url = (base_url if base_url is not None else settings.OPENAI_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.OPENAI_TIMEOUT_SECONDS

    def extract(self, image_b64: str) -> dict:
        url = f"{self.base_url}/chat/completions"
        try:
            with httpx.Client(timeout=self.timeout) as c:
                r = c.post(url, json=_build_payload(image_b64, self.model),
                           headers=self._headers(self.api_key))
        except httpx.TimeoutException as e:
            raise ProviderError(f"openai timeout: {e}") from e
        except httpx.HTTPError as e:
            raise ProviderError(f"openai transport error: {e}") from e
        if r.status_code in (401, 403):
            raise ProviderError("openai auth failed (invalid API key)")
        if r.status_code == 429:
            raise ProviderError("openai rate limited")
        if r.status_code != 200:
            raise ProviderError(f"openai http {r.status_code}")
        try:
            reply = r.json()["choices"][0]["message"]["content"]
            return _extract_json(reply)
        except Exception as e:
            raise ProviderError(f"openai bad response: {e}") from e

class CloudReceiptScannerService:
    """Wraps any BaseReceiptVisionProvider as a ReceiptScannerService."""

    def __init__(self, provider=None):
        if provider is None:
            provider = _default_provider()
        self.provider = provider
        self.name = f"cloud-{provider.name}"
        self._available = None

    def available(self) -> bool:
        if self._available is None:
            try:
                _ = self.provider
                self._available = True
            except ProviderNotConfigured:
                self._available = False
        return self._available

    def scan(self, image_path):
        from app.services.receipt_ocr import ReceiptScanResult, compute_confidence
        try:
            image_b64 = _image_to_b64(image_path)
        except Exception as e:
            log.info("cloud image prep failed: %s", type(e).__name__)
            return ReceiptScanResult(status="failed", error="image_unreadable",
                                     engine=self.name)
        try:
            data = self.provider.extract(image_b64)
        except ProviderNotConfigured as e:
            log.info("cloud provider not configured: %s", e)
            return ReceiptScanResult(status="failed", error="provider_not_configured",
                                     engine=self.name)
        except ProviderError as e:
            log.info("cloud provider failed: %s", e)
            return ReceiptScanResult(status="failed", error="provider_failed",
                                     engine=self.name)

        items = _clean_items(data.get("line_items") or data.get("items"))
        from app.services.receipt_id import parse_id_money
        def m(key):
            n, _ = parse_id_money(data.get(key))
            return n

        try:
            result = ReceiptScanResult(
                merchant=_n(data.get("merchant")),
                date=_n(data.get("date")),
                time=_n(data.get("time")),
                total_amount=m("total_amount"),
                subtotal=m("subtotal"),
                tax=m("tax"),
                discount=m("discount"),
                service_charge=m("service_charge"),
                delivery_fee=m("delivery_fee"),
                shipping_fee=m("shipping_fee"),
                rounding=m("rounding"),
                other_fee=m("other_fee"),
                payment_method=_n(data.get("payment_method")),
                items=items,
                raw_text=None,
                status="processed",
                engine=self.name,
            )
            result.confidence = compute_confidence(result)
            return result
        except Exception:
            return ReceiptScanResult(
                merchant=_n(data.get("merchant")),
                date=_n(data.get("date")),
                total_amount=m("total_amount"),
                items=items, raw_text=None, status="processed",
                confidence="LOW", engine=self.name,
            )

def _default_provider():
    """Instantiate the cloud provider named in RECEIPT_AI_PROVIDER."""
    provider = settings.RECEIPT_AI_PROVIDER
    if provider == "openai":
        return OpenAIVisionProvider()
    if provider == "gemini":
        return GeminiVisionProvider()
    raise ProviderNotConfigured(
        f"RECEIPT_AI_PROVIDER={provider!r} is not a supported cloud provider")


def get_cloud_scanner():
    """Return a ready cloud scanner, or None if no cloud provider is usable."""
    try:
        return CloudReceiptScannerService()
    except ProviderNotConfigured:
        return None
