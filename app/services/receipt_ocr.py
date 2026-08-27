"""Local receipt OCR pipeline.

* Receipt parsing is PURE PYTHON and fully offline (no network/cloud).
* The vision engine is pluggable behind the existing ReceiptScannerService
  abstraction: Tesseract (local, CPU-only) is selected when the binary is
  available; otherwise an OfflineReceiptScannerService keeps the lifecycle
  (upload -> review -> confirm -> transaction) working with manual entry.

OCR NEVER creates a transaction. Only the explicit confirmation endpoint may
do that, and the values used are always the user-edited form values.
"""
import json
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.services.receipts import ReceiptScannerService


# ------------------------------------------------------------ result model


@dataclass
class ReceiptItem:
    name: Optional[str] = None
    quantity: Optional[int] = None
    unit_price: Optional[int] = None
    total_price: Optional[int] = None

    def to_dict(self) -> dict:
        return {"name": self.name, "quantity": self.quantity,
                "unit_price": self.unit_price, "total_price": self.total_price}


@dataclass
class ReceiptScanResult:
    merchant: Optional[str] = None
    date: Optional[str] = None          # ISO yyyy-mm-dd or None
    time: Optional[str] = None
    total_amount: Optional[int] = None
    subtotal: Optional[int] = None
    tax: Optional[int] = None
    discount: Optional[int] = None
    payment_method: Optional[str] = None
    items: list = field(default_factory=list)
    raw_text: Optional[str] = None
    confidence: str = "LOW"
    status: str = "processed"           # processed | failed
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "merchant": self.merchant, "date": self.date, "time": self.time,
            "total_amount": self.total_amount, "subtotal": self.subtotal,
            "tax": self.tax, "discount": self.discount,
            "payment_method": self.payment_method,
            "items": [i.to_dict() if isinstance(i, ReceiptItem) else i
                      for i in self.items],
            "raw_text": self.raw_text, "confidence": self.confidence,
            "status": self.status, "error": self.error,
        }


# ----------------------------------------------------- money parsing


def parse_rupiah(value) -> Optional[int]:
    """Parse Indonesian money text into integer rupiah.

    25.000 | 25,000 | 25.000,00 | 25000 | Rp 125.000 | 1.250.000
    '25.000' is 25 thousand; '25' is twenty-five.
    """
    if value is None:
        return None
    s = str(value).replace("Rp", "").replace("rp", "")
    s = s.replace("\u00a0", " ").replace(" ", "")
    s = re.sub(r"[^\d.,]", "", s)
    if not s:
        return None
    if "." in s and "," in s:
        s = s.replace(".", "").split(",")[0]      # 25.000,00 -> 25000
    elif "," in s:
        parts = s.split(",")
        tail = parts[-1]
        if len(tail) == 3 and tail.isdigit() and len(parts) > 1:
            s = s.replace(",", "")                # 1,000 / 25,000
        elif len(tail) in (1, 2) and tail.isdigit() and len(parts[0]) <= 7:
            s = parts[0]                          # 25,50 -> 25
        else:
            s = "".join(parts)
    elif "." in s:
        parts = s.split(".")
        if (len(parts[-1]) == 2 and parts[-1].isdigit()
                and len(parts) <= 3 and all(len(p) <= 3 for p in parts[:-1])):
            s = "".join(parts[:-1])               # 25.50 -> 25
        else:
            s = s.replace(".", "")                # 25.000 -> 25000
    digits = re.sub(r"[^\d]", "", s)
    try:
        return int(digits) if digits else None
    except ValueError:
        return None


def _lines(text) -> list:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def line_amount(line: str) -> Optional[int]:
    m = re.search(r"\d[\d.,]*", line)
    return parse_rupiah(m.group(0)) if m else None


def line_amount_priority(line: str) -> Optional[int]:
    """Extract an amount from a line, preferring 'Rp' prefixed values.

    This handles OCR lines where a label like 'PPN (11%)' has the percentage
    before the actual Rupiah amount: 'PPN (11%)   Rp 500' -> 500, not 11.
    """
    # First try to find Rp-prefixed amount
    m = re.search(r"Rp\s*(\d[\d.,]*)", line, re.IGNORECASE)
    if m:
        return parse_rupiah(m.group(1))
    # Fall back to first number
    return line_amount(line)


# ------------------------------------------------------------- date / time

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "may": 5, "jun": 6,
    "jul": 7, "agu": 8, "aug": 8, "sep": 9, "okt": 10, "nov": 11,
    "des": 12, "dec": 12,
}
_DATE_RE = re.compile(r"\b(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})\b")
_DATE_MONTH_RE = re.compile(
    r"\b(\d{1,2})\s+(jan|feb|mar|apr|mei|may|jun|jul|agu|aug|sep|okt|nov|des|dec)[a-z]*\.?\s+(\d{4})\b",
    re.IGNORECASE,
)
_TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")


def extract_date(text) -> Optional[str]:
    """ISO yyyy-mm-dd or None. Supports dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy,
    dd/mm/yy and yyyy-mm-dd, plus Indonesian month names."""
    if not text:
        return None
    m = _DATE_MONTH_RE.search(text)
    if m:
        day, mon, yr = int(m.group(1)), _MONTH_MAP.get(m.group(2).lower()[:3]), m.group(3)
        if mon:
            try:
                return datetime(int(yr) if int(yr) >= 100 else 2000 + int(yr),
                                mon, day).date().isoformat()
            except ValueError:
                return None
    m = _DATE_RE.search(text)
    if m:
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            if c >= 1000:
                if a >= 1000:
                    return datetime(a, b, c).date().isoformat()
                return datetime(c, b, a).date().isoformat()
            return datetime(2000 + c, b, a).date().isoformat()  # dd/mm/yy
        except ValueError:
            return None
    return None


def extract_time(text) -> Optional[str]:
    if not text:
        return None
    m = _TIME_RE.search(text)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


# ------------------------------------------------------------- labeled sums

def _amount_for_label(lines, labels):
    for i, ln in enumerate(lines):
        low = ln.lower()
        if any(l in low for l in labels):
            amt = line_amount(ln)
            if amt is None and i + 1 < len(lines):
                amt = line_amount(lines[i + 1])
            return amt
    return None


def _line_amount_last(line: str) -> Optional[int]:
    """Extract the last monetary value from a line, preferring Rp-prefixed.

    Handles lines like ``Total Item     1        10.900`` where the FIRST
    number is a quantity (1) but the actual amount is the LAST (10.900).
    Also handles ``PPN (11%)   Rp 500`` where the percentage must be ignored.
    """
    m = re.search(r'Rp\s*(\d[\d.,]*)', line, re.IGNORECASE)
    if m:
        return parse_rupiah(m.group(1))
    numbers = list(re.finditer(r'\d[\d.,]*', line))
    if numbers:
        return parse_rupiah(numbers[-1].group(0))
    return None


def _amount_for_label_priority(lines, labels):
    """Like _amount_for_label but extracts the LAST number on the line.

    This prevents ``Total Item     1        10.900`` from returning 1.
    """
    for i, ln in enumerate(lines):
        low = ln.lower()
        if any(l in low for l in labels):
            amt = _line_amount_last(ln)
            if amt is None and i + 1 < len(lines):
                amt = _line_amount_last(lines[i + 1])
            return amt
    return None


# ---------------------------------------------------------------- merchant

_MERCHANT_BAD = re.compile(
    r"(total|sub ?total|grand|ppn|pajak|pb1|telp|tlp|alamat|cashier|kasir|"
    r"kembali|tunai|debit|qris|no\.? |nota|waktu|operat|terima\s+kasih|"
    r"petugas|jakarta|bandung|surabaya|medan|dpk|no\b|jl\b|jalan|"
    r"^[A-Z]{1,2}\s|^\d+$|^\d{5,}$)",
    re.IGNORECASE,
)


def extract_merchant(text) -> Optional[str]:
    """Upper-section merchant name. Returns None when uncertain (no guessing)."""
    lines = _lines(text)
    for ln in lines:
        if len(ln) < 3 or re.match(r"^[\d.:#\-]+$", ln):
            continue
        if _MERCHANT_BAD.search(ln):
            continue
        # Take only the first good line - subsequent lines are usually address/phone
        merchant = ln.strip()
        # Strip trailing phone-like patterns
        merchant = re.sub(r"\b(telp|telepon|\d{5,})\b.*$", "", merchant, flags=re.IGNORECASE)
        return merchant if len(merchant) >= 3 else None
    return None


_TOTAL_LABELS = ["grand total", "total belanja", "total bayar", "total akhir",
                 "*total", "total", "ttl"]
_TOTAL_EXCLUDE = ["kembali", "uang kembali", "tunai", "cash", "discount",
                  "diskon", "ppn", "pajak", "sub ", "total item", "total disc"]


def extract_total(text) -> Optional[int]:
    """Most important field - prefers a *TOTAL-labeled* amount, then the
    largest plausible amount in the bottom half, excluding change / cash /
    discount / tax / subtotal."""
    lines = _lines(text)
    labeled = []
    for i, ln in enumerate(lines):
        low = ln.lower()
        if any(l in low for l in _TOTAL_LABELS) and not any(
                ex in low for ex in _TOTAL_EXCLUDE):
            amt = line_amount(ln)
            if amt is None and i + 1 < len(lines):
                amt = line_amount(lines[i + 1])
            if amt:
                labeled.append((i, amt))
    if labeled:
        return max(amt for _, amt in labeled)

    bottom = lines[len(lines) // 2:]
    best = None
    for ln in bottom:
        low = ln.lower()
        if any(ex in low for ex in ("kembal", "tunai", "discount", "diskon",
                                    "ppn", "pajak", "sub")):
            continue
        amt = line_amount(ln)
        if amt and amt > 0 and (best is None or amt > best):
            best = amt
    return best


def extract_subtotal(text) -> Optional[int]:
    return _amount_for_label_priority(_lines(text), ["subtotal", "sub total", "total item"])


def extract_tax(text) -> Optional[int]:
    """Extract tax amount (not percentage). PPN, Pajak lines often have
    'PPN (11%)' next to the amount - we need the Rupiah value."""
    lines = _lines(text)
    for i, ln in enumerate(lines):
        low = ln.lower()
        if any(l in low for l in ["ppn", "pajak", "pb1"]):
            # Look for amount on this line first (prefer Rp-prefixed)
            amt = line_amount_priority(ln)
            if amt:
                return amt
            # If not found, check next line
            if i + 1 < len(lines):
                amt = line_amount_priority(lines[i + 1])
                if amt:
                    return amt
    return None


def extract_discount(text) -> Optional[int]:
    return _amount_for_label_priority(_lines(text), ["diskon", "disc"])


def extract_payment_method(text) -> Optional[str]:
    low = (text or "").lower()
    for kw in ("qris", "debit", "kredit", "kartu", "cash", "tunai", "gopay",
               "ovo", "e-wallet"):
        if kw in low:
            return kw.upper()
    return None


# ---------------------------------------------------------------- items

_ITEM_RE_COLS = re.compile(
    r"^(?P<name>.+?)\s+(?P<qty>-?\d+)\s+(?P<unit>\d[\d.,]*)\s+(?P<total>\d[\d.,]*)\s*$"
)
_ITEM_RE_X = re.compile(
    r"^(?P<name>.+?)\s+(?P<qty>\d+)\s*[xX*]\s+(?P<unit>\d[\d.,]*)\s+(?P<total>\d[\d.,]*)\s*$"
)
_ITEM_RE_SIMPLE = re.compile(
    r"^(?P<name>.+?)\s+(?P<unit>\d[\d.,]*)\s+(?P<total>\d[\d.,]*)\s*$"
)
_ITEM_SKIP = re.compile(
    r"(?i)(total|subtotal|grand|disc|diskon|ppn|pajak|tunai|debit|cash|"
    r"kembali|bayar|belanja|jumlah|qty)",
)


def extract_items(text) -> list:
    """Best-effort line-item extraction.

    Supports three receipt formats:
    1. ``NAME  QTY  UNIT_PRICE  TOTAL_PRICE``  (4-column Indonesian cashier)
    2. ``NAME  QTYx  UNIT_PRICE  TOTAL_PRICE`` (qty-x format)
    3. ``NAME  UNIT_PRICE  TOTAL_PRICE``        (simple 2-number)

    Negative-quantity / negative-total lines (returns/discounts) are skipped.
    Summary lines (total, discount, PPN etc.) are never treated as items.
    """
    items = []
    for ln in _lines(text):
        m = _ITEM_RE_COLS.match(ln)
        if m:
            qty = int(m.group("qty"))
            if qty < 0:
                continue
            unit = parse_rupiah(m.group("unit"))
            total = parse_rupiah(m.group("total"))
            if total is not None and total < 0:
                continue
            if not unit or not total:
                continue
            name = re.sub(r"\s+", " ", m.group("name")).strip(" .-")
            if not name or _ITEM_SKIP.search(name):
                continue
            items.append(ReceiptItem(name=name, quantity=qty,
                                     unit_price=unit, total_price=total))
            continue
        m = _ITEM_RE_X.match(ln)
        if m:
            unit = parse_rupiah(m.group("unit"))
            total = parse_rupiah(m.group("total"))
            if not unit or not total:
                continue
            name = re.sub(r"\s+", " ", m.group("name")).strip(" .-")
            if not name or _ITEM_SKIP.search(name):
                continue
            items.append(ReceiptItem(name=name, quantity=int(m.group("qty")),
                                     unit_price=unit, total_price=total))
            continue
        m = _ITEM_RE_SIMPLE.match(ln)
        if m:
            unit = parse_rupiah(m.group("unit"))
            total = parse_rupiah(m.group("total"))
            if not unit or not total:
                continue
            name = re.sub(r"\s+", " ", m.group("name")).strip(" .-")
            if not name or _ITEM_SKIP.search(name):
                continue
            items.append(ReceiptItem(name=name, quantity=1,
                                     unit_price=unit, total_price=total))
    return items


# ---------------------------------------------------------------- category

_CATEGORY_KEYWORDS = {
    "Belanja": ["indomaret", "alfamart", "superindo", "hypermart", "transmart",
                "guardian", "minimarket", "dunia", "sour sally", "elektronik",
                "baju", "celana", "sepatu", "tas", "fashion"],
    "Transportasi": ["grab", "gojek", "pertamina", "shell", "spbu", "bensin",
                     "parkir", "tol", "go-car", "go ride"],
    "Makan & Minum": ["mcdonald", "kfc", "burger", "warung", "bakso", "mie ",
                      "mie", "nasi goreng", "restoran", "kopi", "star bucks",
                      "starbucks", "kedai", "ayam", "sate", "gorengan",
                      "bebek", "cafe"],
    "Hiburan": ["netflix", "spotify", "disney", "youtube", "bioskop", "cinema",
                "game", "playstore"],
    "Tagihan": ["token listrik", "pdam", "telkom", "indihome", "wifi", "bi ",
                "pln", "pulsa", "xl", "telkomsel"],
    "Kesehatan": ["apotek", "kimia farma", "klinik", "dokter", "obat"],
}


def suggest_category(merchant) -> Optional[str]:
    if not merchant:
        return None
    low = merchant.lower()
    best = None
    for cat, kws in _CATEGORY_KEYWORDS.items():
        if any(k in low for k in kws):
            best = cat  # later keys override earlier ones (intentional)
    return best


# ------------------------------------------------------------ confidence

def compute_confidence(total, date_t, merchant) -> str:
    got = sum(1 for v in (total, date_t, merchant) if v is not None)
    if got >= 3:
        return "HIGH"
    if got >= 2:
        return "MEDIUM"
    return "LOW"


def parse_receipt_text(raw_text: str) -> ReceiptScanResult:
    """Orchestrator: raw OCR text -> structured result (pure, offline)."""
    text = (raw_text or "").strip()
    total = extract_total(text)
    date_t = extract_date(text)
    merchant = extract_merchant(text)
    result = ReceiptScanResult(
        merchant=merchant, date=date_t, time=extract_time(text),
        total_amount=total, subtotal=extract_subtotal(text),
        tax=extract_tax(text), discount=extract_discount(text),
        payment_method=extract_payment_method(text),
        items=extract_items(text), raw_text=text,
    )
    result.confidence = compute_confidence(total, date_t, merchant)
    return result


# ------------------------------------------------------------ preprocessing

_MAX_OCR_WIDTH = 2200  # cap huge phone photos before OCR


def preprocess_image(image_path: Path, out_dir: Path | None = None) -> Path:
    """EXIF orientation + grayscale + contrast + downsizing + sharpening.

    Keeps the ORIGINAL upload untouched; returns the path of a processed copy.
    Falls back to the original when Pillow is unavailable.
    """
    try:
        from PIL import Image, ImageFilter, ImageOps
    except ImportError:
        return Path(image_path)

    out_dir = out_dir or Path(image_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / (Path(image_path).stem + "_proc.png")

    with Image.open(image_path) as img:
        img = ImageOps.exif_transpose(img)          # correct camera rotation
        img = img.convert("L")                      # grayscale
        img = ImageOps.autocontrast(img, cutoff=1)  # contrast enhancement
        if img.width > _MAX_OCR_WIDTH:
            ratio = _MAX_OCR_WIDTH / img.width
            img = img.resize((_MAX_OCR_WIDTH, int(img.height * ratio)),
                             Image.LANCZOS)
        img = img.filter(ImageFilter.SHARPEN)       # sharpen edges for OCR
        img.save(out_path, "PNG")
    return out_path


# ---------------------------------------------------------------- engines


def _get_pytesseract():
    """Lazy-import pytesseract and configure the binary path from settings.

    On Windows the UB-Mannheim package installs to
    ``C:\\Program Files\\Tesseract-OCR\\tesseract.exe`` which is NOT on PATH by
    default, so pytesseract cannot locate it without an explicit tesseract_cmd.
    """
    import pytesseract
    from app.config import settings
    if settings.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
    return pytesseract


def _tesseract_available() -> bool:
    try:
        _get_pytesseract().get_tesseract_version()
        return True
    except Exception:
        return False


def _available_langs() -> list:
    """Return available OCR languages following the configured preference list.

    Preference order: ind+eng if both exist; eng if only eng exists;
    empty list if Tesseract has no usable language files.
    """
    import pytesseract
    from app.config import settings
    if settings.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
    try:
        data = pytesseract.get_languages(config="")
        langs = data.splitlines() if isinstance(data, str) else data
    except Exception:
        langs = []
    # Build fallback chain from configured preference
    pref = settings.RECEIPT_OCR_LANG.split("+")
    ordered = [l for l in pref if l in langs]
    if ordered:
        return ordered
    return ["eng"] if "eng" in langs else []


class TesseractReceiptScannerService(ReceiptScannerService):
    """Tesseract vision + pure-python receipt parsing (local, CPU-only)."""

    def __init__(self):
        self._pytesseract = _get_pytesseract()
        self._langs = _available_langs()

    def scan(self, image_path) -> ReceiptScanResult:
        path = Path(image_path)
        processed = preprocess_image(path)
        try:
            kwargs = {"lang": "+".join(self._langs)} if self._langs else {}
            text = self._pytesseract.image_to_string(str(processed), **kwargs)
        finally:
            if processed != Path(image_path) and processed.exists():
                try:
                    processed.unlink()
                except OSError:
                    pass
        result = parse_receipt_text(text)
        result.status = "processed"
        return result


# ---------------------------------------------------------------- fallback


class OfflineReceiptScannerService(ReceiptScannerService):
    """Fallback when Tesseract is unavailable. Returns failed status so the
    manual-entry flow stays intact (no OCR, no transaction)."""

    def scan(self, image_path) -> ReceiptScanResult:
        return ReceiptScanResult(status="failed", raw_text=None)


# ---------------------------------------------------------------- factory

_scanner = None


def build_scanner() -> ReceiptScannerService:
    """Pick the best local engine. Never requires a cloud service."""
    if _tesseract_available():
        return TesseractReceiptScannerService()
    return OfflineReceiptScannerService()


def get_scanner() -> ReceiptScannerService:
    global _scanner
    if _scanner is None:
        _scanner = build_scanner()
    return _scanner


def set_scanner(scanner) -> None:
    global _scanner
    _scanner = scanner