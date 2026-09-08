"""Native Ollama vision receipt scanner (moondream:1.8b-v2-q4_K_S on 127.0.0.1:11434).

Drop-in ``ReceiptScannerService``: ``scan(image_path)`` returns a
``ReceiptScanResult`` and NEVER creates a transaction.

Design notes (production, CPU-only, ~3.6 GB RAM, no GPU):

* Talks to Ollama's native HTTP API at ``/api/chat`` with the
  ``messages[].images`` field (the documented vision contract). We do
  NOT use Ollama's ``/v1`` OpenAI-compat shim - the native path handles
  image payloads most reliably across model releases.
* A persistent ``httpx.Client`` is reused across requests so we don't
  pay TCP/TLS setup per scan.
* Concurrency is capped at 1 inference process-wide via an ``fcntl``
  advisory file lock on Linux (production systemd runs ``--workers 2``,
  so an in-process lock alone is insufficient). On Windows / platforms
  without ``fcntl`` we transparently fall back to a ``threading.Lock``
  (still serializes threads within the test worker).
* Image is downscaled and re-encoded to JPEG by the same helper used by
  the OpenAI-compat scanner; we never log the base64 payload.
* Server-side validation rejects model output that violates the app's
  schema or the ``MAX_TX_AMOUNT`` ceiling. On any failure ``scan()``
  returns ``ReceiptScanResult(status="failed", error=...)`` so the
  fallback composite (Tesseract) takes over.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import httpx

from app.config import settings
from app.services.receipt_id import (
    DOC_TYPES, CANONICAL_METHODS, normalize_id_date, normalize_id_time,
    normalize_payment_method, _PROVIDER_PATTERNS,
)

log = logging.getLogger(__name__)

# Canonical payment-method whitelist (see app/services/receipt_id.py):
# anything outside it is dropped to None, never stored blindly.
_ALLOWED_PM = set(CANONICAL_METHODS)
_KNOWN_PROVIDERS = {name for name, _ in _PROVIDER_PATTERNS}


# ------------------------------------------------------- file-lock guard
# Advisory file lock (fcntl) caps concurrent Ollama inferences to 1 across
# worker processes. On platforms without fcntl (Windows test env) we fall
# back to a per-process threading lock. Both keep the test suite green
# and are still correct within a single process.
try:
    import fcntl  # type: ignore[import-not-found]
    _HAS_FCNTL = True
except ImportError:  # pragma: no cover - exercised implicitly on Windows
    fcntl = None  # type: ignore[assignment]
    _HAS_FCNTL = False


class _ProcessLock:
    """Cross-process exclusive lock backed by an OS file; in-process fallback."""

    def __init__(self, path: Path):
        self._path = path
        self._thread_lock = threading.Lock()
        self._fd = None

    def _ensure_fd(self):
        if self._fd is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._fd = open(self._path, "w+")

    def acquire(self, timeout: float = 10.0) -> bool:
        if not _HAS_FCNTL:
            return self._thread_lock.acquire(timeout=timeout)
        self._ensure_fd()
        deadline = time.monotonic() + timeout
        if not self._thread_lock.acquire(timeout=timeout):
            return False
        try:
            while True:
                try:
                    fcntl.flock(self._fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return True
                except (BlockingIOError, OSError):
                    if time.monotonic() >= deadline:
                        self._thread_lock.release()
                        return False
                    time.sleep(0.1)
        except Exception:
            self._thread_lock.release()
            raise

    def release(self) -> None:
        if not _HAS_FCNTL:
            try:
                self._thread_lock.release()
            except RuntimeError:
                pass
            return
        try:
            fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            self._thread_lock.release()
        except RuntimeError:
            pass


# Module-level singleton so all scanners / workers share the same lock file.
_LOCK_SINGLETON: _ProcessLock | None = None
_LOCK_SINGLETON_LOCK = threading.Lock()


def _get_lock() -> _ProcessLock:
    global _LOCK_SINGLETON
    if _LOCK_SINGLETON is None:
        with _LOCK_SINGLETON_LOCK:
            if _LOCK_SINGLETON is None:
                _LOCK_SINGLETON = _ProcessLock(
                    Path(settings.RECEIPT_UPLOAD_DIR) / ".ollama.lock")
    return _LOCK_SINGLETON


@contextmanager
def _ollama_lock(timeout: float = 10.0):
    lock = _get_lock()
    got = lock.acquire(timeout=timeout)
    if not got:
        raise TimeoutError("Ollama inference busy (lock not acquired)")
    try:
        yield
    finally:
        lock.release()


# ------------------------------------------------------- HTTP client
# One persistent client per process. Connections are reused; the client is
# process-local and lives for the worker lifetime.
_CLIENT: httpx.Client | None = None
_CLIENT_LOCK = threading.Lock()


def _client() -> httpx.Client:
    global _CLIENT
    if _CLIENT is None:
        with _CLIENT_LOCK:
            if _CLIENT is None:
                # Cap connections so a misbehaving scanner cannot open a
                # parallel socket while one is in-flight.
                limits = httpx.Limits(max_connections=2, max_keepalive_connections=1)
                _CLIENT = httpx.Client(
                    timeout=settings.OLLAMA_TIMEOUT_SECONDS,
                    limits=limits,
                    headers={"User-Agent": "PersonalFinancing/1 (receipt-ocr)"},
                )
    return _CLIENT
# ------------------------------------------------------- image prep
def _image_to_b64(image_path) -> str:
    """Downscale + JPEG-encode an image; return PURE base64 (no data URI).

    The ORIGINAL uploaded file is never touched: ``image_path`` is always the
    stored receipt, and this function only produces a temporary in-memory
    JPEG derived from it (nothing is written to disk and nothing is logged).

    Memory-safety: capped pixel dimensions prevent decompression bombs from
    exhausting the 3.6 GB server RAM.
    """
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = 25_000_000  # ~5000x5000, hard cap
    with Image.open(image_path) as img:
        # 1) EXIF orientation (phone photos), 2) downscale, 3) JPEG encode.
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        max_w = settings.RECEIPT_AI_MAX_IMAGE_WIDTH
        if img.width > max_w:
            r = max_w / img.width
            img = img.resize((max_w, int(img.height * r)), Image.LANCZOS)
        # Extra safety: cap height for extremely tall receipt images.
        max_h = max_w * 4  # reasonable max for receipts (~4:1 aspect)
        if img.height > max_h:
            img = img.crop((0, 0, img.width, max_h))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=settings.RECEIPT_AI_JPEG_QUALITY)
        data = buf.getvalue()
    if len(data) > settings.OLLAMA_MAX_IMAGE_BYTES:
        raise ValueError(
            f"image too large for Ollama ({len(data)} > "
            f"{settings.OLLAMA_MAX_IMAGE_BYTES})")
    return base64.b64encode(data).decode("ascii")


# ------------------------------------------------------- validation
_ALLOWED_PM = {"TUNAI", "DEBIT", "KREDIT", "QRIS", "CASH", "CARD", "TRANSFER", ""}


def _n(v):
    """Trim a string-or-None to a non-empty string or None."""
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _int(v):
    """Strict integer coercion. Rejects bool, floats-as-strings like '25.000',
    and anything that can't be parsed by int(). Returns None for nullish input."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):  # NaN / inf
            return None
        if v != int(v):  # reject 25000.5
            return None
        return int(v)
    s = str(v).strip()
    if not s:
        return None
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def _money(v, *, allow_zero: bool = False):
    """Integer Rupiah with positive + ceiling enforcement.

    Coerces via the Indonesian money parser so model-emitted thousands
    separators are understood ("12.500" -> 12500, "Rp 12.500", "1.250.000").
    Returns ``(int_value, None)`` on success, ``(None, error_str)`` on failure.
    """
    from app.services.receipt_id import parse_id_money
    n, warn = parse_id_money(v)
    if n is None:
        return None, warn or None
    if not allow_zero and n <= 0:
        return None, "negative or zero amount"
    # Import lazily so config is fully loaded before finance is touched.
    from app.services.finance import MAX_TX_AMOUNT
    if n > MAX_TX_AMOUNT:
        return None, f"amount exceeds MAX_TX_AMOUNT ({MAX_TX_AMOUNT})"
    return n, None


def _validate_date(v):
    """Accept ISO or Indonesian date formats; normalize to ISO.

    Returns (iso, warning) - impossible calendar dates and unparseable
    strings yield (None, warning) rather than a guessed value.
    """
    return normalize_id_date(v)


def _money_signed(v):
    """Integer rupiah allowing negatives (e.g. 'Pembulatan' rounding lines)."""
    from app.services.receipt_id import parse_id_money
    n, warn = parse_id_money(v)
    if n is None:
        return None, warn or None
    from app.services.finance import MAX_TX_AMOUNT
    if abs(n) > MAX_TX_AMOUNT:
        return None, f"amount exceeds MAX_TX_AMOUNT ({MAX_TX_AMOUNT})"
    return n, None


def _validate_time(v):
    """Accept HH:MM / HH:MM:SS (also dot-separated) -> canonical or warning."""
    return normalize_id_time(v)


def _clean_items(raw):
    from app.services.receipt_ocr import ReceiptItem
    out = []
    for it in raw or []:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()
        if not name:
            continue
        qty, _ = _money(it.get("quantity"), allow_zero=True)
        if qty is not None and qty < 1:
            qty = None
        # Accept both the task spec's "unit_price"/"total" keys and the app's
        # existing "unit_price"/"total_price" naming - models are inconsistent.
        unit, _ = _money(
            it.get("unit_price") if it.get("unit_price") is not None
            else it.get("price"), allow_zero=True)
        tot, _ = _money(
            it.get("total_price") if it.get("total_price") is not None
            else it.get("total"), allow_zero=True)
        # Reject negative totals that slipped through (defence-in-depth).
        if unit is not None and unit < 0:
            unit = None
        if tot is not None and tot < 0:
            tot = None
        item_discount, _ = _money(it.get("discount"), allow_zero=True)
        out.append(ReceiptItem(
            name=name[:200],  # cap to keep DB row reasonable
            quantity=qty,
            unit_price=unit,
            total_price=tot,
            unit=(str(it.get("unit") or "").strip()[:12] or None),
            sku=(str(it.get("sku") or "").strip()[:64] or None),
            discount=item_discount,
        ))
    return out


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


# ------------------------------------------------------- prompt
# Kept intentionally short and task-specific (small low-RAM model, 2K ctx):
# no reasoning, no explanations, no prose - only one small JSON object out.
_SYSTEM_PROMPT = (
    "Extract receipt data as STRICT JSON only. No explanations, no markdown. "
    "Money = integer Indonesian Rupiah (IDR); dots are thousands separators "
    "(25.000 -> 25000). Unknown = null. Never invent or expand values; copy "
    "product names exactly as printed. Date as printed (YYYY-MM-DD or "
    "DD/MM/YYYY). "
    'Fields: {"document_type": "RETAIL_RECEIPT"|"RESTAURANT_RECEIPT"|'
    '"CAFE_RECEIPT"|"SUPERMARKET_RECEIPT"|"MINIMARKET_RECEIPT"|'
    '"FUEL_RECEIPT"|"WORKSHOP_RECEIPT"|"PHARMACY_RECEIPT"|"HOSPITAL_RECEIPT"|'
    '"HOTEL_RECEIPT"|"PARKING_RECEIPT"|"TOLL_RECEIPT"|"TRANSPORT_RECEIPT"|'
    '"UTILITY_RECEIPT"|"TELCO_RECEIPT"|"E_COMMERCE_RECEIPT"|'
    '"DELIVERY_RECEIPT"|"QRIS_PAYMENT_RECEIPT"|"BANK_PAYMENT_RECEIPT"|'
    '"E_WALLET_RECEIPT"|"OTHER_RECEIPT"|"UNKNOWN"|null, '
    '"merchant": string|null, "merchant_address": string|null, '
    '"merchant_phone": string|null, "receipt_number": string|null, '
    '"invoice_number": string|null, "date": null|string, "time": null|string, '
    '"currency": "IDR", "subtotal": int|null, "discount": int|null, '
    '"tax": int|null, "service_charge": int|null, "delivery_fee": int|null, '
    '"shipping_fee": int|null, "rounding": int|null, "other_fee": int|null, '
    '"total_amount": int|null, '
    '"payment_method": "TUNAI"|"DEBIT"|"KREDIT"|"QRIS"|"TRANSFER"|'
    '"E_WALLET"|null, '
    '"payment_provider": "GOPAY"|"OVO"|"DANA"|"SHOPEEPAY"|"LINKAJA"|null, '
    '"items": [{"name": string, "quantity": int|null, "unit": string|null, '
    '"unit_price": int|null, "discount": int|null, "total_price": int|null}], '
    '"confidence": number}. total_amount = final paid. Reply JSON only.'
)
# ------------------------------------------------------- client + scanner
class OllamaClient:
    """Tiny wrapper around the Ollama native HTTP API."""

    def __init__(self, base_url: str | None = None, model: str | None = None,
                 timeout: float | None = None, num_ctx: int | None = None):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_VISION_MODEL
        self.timeout = timeout if timeout is not None else settings.OLLAMA_TIMEOUT_SECONDS
        self.num_ctx = num_ctx if num_ctx is not None else settings.OLLAMA_NUM_CTX

    # ---- probe
    def ping(self) -> tuple[bool, str]:
        """Return (available, reason). Checks /api/tags + model presence."""
        url = f"{self.base_url}/api/tags"
        try:
            r = _client().get(url, timeout=min(self.timeout, 10))
        except httpx.HTTPError as e:
            return False, f"connect_failed:{type(e).__name__}"
        if r.status_code != 200:
            return False, f"http_{r.status_code}"
        try:
            data = r.json()
        except (json.JSONDecodeError, ValueError):
            return False, "bad_json"
        names = {m.get("name") for m in (data.get("models") or [])}
        if not names:
            return False, "no_models"
        if self.model not in names:
            return False, f"model_missing:{self.model}"
        return True, "ok"

    # ---- chat (vision)
    def chat(self, image_b64: str) -> dict:
        """Send the image + prompt; return the parsed JSON object the model emitted."""
        import time
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": "Extract the receipt data from "
                                            "this image.",
                 "images": [image_b64]},
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0,
                "num_ctx": self.num_ctx,
            },
        }
        t0 = time.monotonic()
        log.info("ollama vision request started model=%s timeout=%s", self.model, self.timeout)
        r = _client().post(url, json=payload, timeout=self.timeout)
        elapsed = time.monotonic() - t0
        log.info("ollama vision request completed model=%s elapsed=%.1fs status=%d",
                 self.model, elapsed, r.status_code)
        if r.status_code != 200:
            raise RuntimeError(f"ollama http {r.status_code}")
        try:
            data = r.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise RuntimeError(f"ollama bad json: {e}") from e
        content = (data.get("message") or {}).get("content")
        if not isinstance(content, str):
            raise RuntimeError("ollama reply missing content")
        return _extract_json(content)
class OllamaVisionReceiptScannerService:
    """``ReceiptScannerService`` backed by native Ollama /api/chat."""

    name = "ollama"

    def __init__(self, client: OllamaClient | None = None):
        self.client = client or OllamaClient()
        self._available: bool | None = None

    def available(self) -> bool:
        if self._available is None:
            ok, _ = self.client.ping()
            self._available = bool(ok)
        return self._available

    def scan(self, image_path):
        from app.services.receipt_ocr import (
            ReceiptScanResult, compute_confidence,
        )
        import time
        t_scan = time.monotonic()
        log.info("ollama scan started path=%s", str(image_path)[:80])
        try:
            b64 = _image_to_b64(image_path)
        except Exception as e:
            log.info("ollama image prep failed: %s", type(e).__name__)
            return ReceiptScanResult(status="failed", error="image_unreadable")

        try:
            with _ollama_lock(timeout=10.0):
                data = self.client.chat(b64)
        except TimeoutError:
            log.info("ollama busy; scan treated as failure")
            return ReceiptScanResult(status="failed", error="busy")
        except httpx.TimeoutException:
            log.info("ollama timeout")
            return ReceiptScanResult(status="failed", error="timeout")
        except httpx.HTTPError as e:
            log.info("ollama transport error: %s", type(e).__name__)
            return ReceiptScanResult(status="failed", error="transport")
        except Exception as e:
            # Model returned garbage / bad JSON / missing keys etc.
            log.info("ollama decode failed: %s", type(e).__name__)
            return ReceiptScanResult(status="failed", error="bad_response")

        if not isinstance(data, dict):
            return ReceiptScanResult(status="failed", error="bad_response")

        # ---- field validation (server-side, never trust the model)
        merchant = _n(data.get("merchant"))
        date_val, date_err = _validate_date(data.get("date"))
        time_val, time_err = _validate_time(data.get("time"))
        total, total_err = _money(data.get("total_amount"))
        subtotal, _ = _money(data.get("subtotal"), allow_zero=True)
        tax, _ = _money(data.get("tax"), allow_zero=True)
        discount, _ = _money(data.get("discount"), allow_zero=True)
        service_charge, _ = _money(data.get("service_charge"), allow_zero=True)
        delivery_fee, _ = _money(data.get("delivery_fee"), allow_zero=True)
        shipping_fee, _ = _money(data.get("shipping_fee"), allow_zero=True)
        rounding, _ = _money_signed(data.get("rounding"))
        other_fee, _ = _money(data.get("other_fee"), allow_zero=True)
        # Payment: canonical normalization (Tunai/Cash -> TUNAI, Kartu Debit
        # -> DEBIT, ...); unknown -> None. Provider only via known whitelist.
        payment_method = normalize_payment_method(data.get("payment_method"))
        provider_raw = (_n(data.get("payment_provider")) or "").upper()
        payment_provider = provider_raw if provider_raw in _KNOWN_PROVIDERS else None
        # Currency/document_type: whitelist-validated, else honest default.
        currency = (_n(data.get("currency")) or "IDR").upper()[:3]
        doc_raw = _n(data.get("document_type"))
        document_type = doc_raw if doc_raw in DOC_TYPES else None
        merchant_address = _n(data.get("merchant_address"))
        merchant_phone = _n(data.get("merchant_phone"))
        receipt_number = _n(data.get("receipt_number"))
        invoice_number = _n(data.get("invoice_number"))
        items = _clean_items(data.get("items"))

        # Critical-field errors collapse the whole result to "failed" so the
        # fallback composite tries Tesseract. Non-critical issues (e.g. bad
        # date format on an otherwise-valid reply) still let the user review
        # the draft manually.
        critical = None
        if total_err and data.get("total_amount") is not None:
            critical = f"total_amount {total_err}"
        elif total is not None and total <= 0:
            critical = "total_amount must be positive"

        if critical is not None:
            log.info("ollama validation rejected: %s", critical)
            return ReceiptScanResult(
                status="failed", error=critical,
                merchant=merchant, date=date_val, items=items,
            )

        result = ReceiptScanResult(
            merchant=merchant,
            date=date_val,
            time=time_val,
            total_amount=total,
            subtotal=subtotal,
            tax=tax,
            discount=discount,
            service_charge=service_charge,
            delivery_fee=delivery_fee,
            shipping_fee=shipping_fee,
            rounding=rounding,
            other_fee=other_fee,
            payment_method=payment_method,
            payment_provider=payment_provider,
            currency=currency,
            document_type=document_type,
            merchant_address=merchant_address,
            merchant_phone=merchant_phone,
            receipt_number=receipt_number,
            invoice_number=invoice_number,
            items=items,
            raw_text=None,
            status="processed",
        )
        # Surface validation issues as a warning string without failing the
        # whole scan (user can still correct values in the review form).
        warnings = []
        if date_err:
            warnings.append(f"date:{date_err}")
        if time_err:
            warnings.append(f"time:{time_err}")
        try:
            result.confidence = compute_confidence(result)
        except Exception:
            result.confidence = "LOW"
        if warnings:
            result.error = "; ".join(warnings)
        return result


def probe_service() -> OllamaVisionReceiptScannerService | None:
    """Return a ready Ollama scanner if the endpoint serves the model, else None."""
    svc = OllamaVisionReceiptScannerService()
    return svc if svc.available() else None


# Test hook: reset module-level singletons between tests.
def _reset_for_tests() -> None:
    global _CLIENT, _LOCK_SINGLETON
    with _CLIENT_LOCK:
        if _CLIENT is not None:
            try:
                _CLIENT.close()
            except Exception:
                pass
        _CLIENT = None
    with _LOCK_SINGLETON_LOCK:
        _LOCK_SINGLETON = None