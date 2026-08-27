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
    estimated_items: Optional[int] = None

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



# ----------------------------------------------------------- item extraction
# Structural right-to-left parser.
_NOISE_RE = re.compile(r"[^a-zA-Z0-9.,:;() @'’\t]+")
_SUMMARY_LINE_RE = re.compile(
    r'(?i)^.*'
    r'(total\s+belanja|grand\s+total|total\s+bayar|total\s+akhir|'
    r'sub\s*total|total\s+item|total\s+disc|'
    r'tunai|cash|kembali|bayar|belanja|hemat|'
    r'diskon|disc|ppn|pajak|pb1|dpp|'
    r'debit|kredit|qris|gopay|ovo|transfer|'
    r'payment|change|amount\s+tender|'
    r'no\.?\s*struk|nota|terima\s+kasih|struk\s+belanja|'
    r'harga\s+jual|harga\s+total|'
    r'ppn\s*dibebaskan|ppn\s*:)'
)
_NAME_SKIP_RE = re.compile(
    r'(?i)^(total|subtotal|sub\s*total|grand|disc|diskon|ppn|pajak|pb1|'
    r'tunai|cash|debit|kredit|kembali|bayar|belanja|hema|jumlah|qty|vo|'
    r'payment|change|dpp|no\s*struk)'
)
_SEP_LINE_RE = re.compile(r'^[\s.\-=*#~]+$')
_DATE_LINE_RE = re.compile(r'^[0-9][0-9.,/:-]*[0-9][.,/:-]+[0-9]')
_FINANCIAL_TOLERANCE = 0.05


def _is_financial_token(tok):
    t = tok.strip().strip('()')
    t = re.sub(r'^(Rp|rp|RP)', '', t)
    return bool(re.match(r'^\d[\d.,]*$', t))


def _parse_item_line(line):
    if not line or _DATE_LINE_RE.match(line.strip()):
        return None
    if not line or _SEP_LINE_RE.match(line) or _SUMMARY_LINE_RE.match(line):
        return None
    normalized = _NOISE_RE.sub(' ', line)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    if not normalized:
        return None
    tokens = normalized.split()
    if len(tokens) < 2:
        return None
    fin_indices = []
    for i in range(len(tokens) - 1, -1, -1):
        if _is_financial_token(tokens[i]):
            fin_indices.append(i)
        else:
            break
    if not fin_indices:
        return None
    fin_indices.reverse()
    qty_from_x = None
    first_fin = fin_indices[0]
    if first_fin > 0:
        prev = tokens[first_fin - 1].strip()
        xmatch = re.match(r'^(\d+)\s*[xX*]$', prev)
        if xmatch:
            qty_from_x = int(xmatch.group(1))
            name_tokens = tokens[:first_fin - 1]
        else:
            name_tokens = tokens[:first_fin]
    else:
        name_tokens = tokens[:first_fin]
    name_text = ' '.join(name_tokens).strip(' .-')
    if not name_text or _NAME_SKIP_RE.match(name_text):
        return None
    fin_count = len(fin_indices)

    def _val(idx):
        return parse_rupiah(tokens[idx])

    def _is_neg(idx):
        t = tokens[idx].strip()
        return t.startswith('(') and t.endswith(')')

    if _is_neg(fin_indices[-1]) and fin_count == 2:
        return None
    if fin_count >= 3:
        qty = _val(fin_indices[0])
        unit = _val(fin_indices[1])
        total = _val(fin_indices[-1])
        if qty and qty > 0 and unit and unit > 0 and total and total > 0:
            expected = qty * unit
            diff = abs(expected - total) / max(expected, total)
            if diff <= _FINANCIAL_TOLERANCE:
                return ReceiptItem(name=name_text, quantity=qty,
                                   unit_price=unit, total_price=total)
        a = _val(fin_indices[-2])
        b = _val(fin_indices[-1])
        if a and a > 0 and b and b > 0:
            return ReceiptItem(name=name_text, quantity=1,
                               unit_price=a, total_price=b)
    if qty_from_x is not None:
        if fin_count >= 2:
            unit = _val(fin_indices[0])
            total = _val(fin_indices[-1])
            if unit and unit > 0 and total and total > 0:
                expected = qty_from_x * unit
                diff = abs(expected - total) / max(expected, total)
                if diff <= _FINANCIAL_TOLERANCE:
                    return ReceiptItem(name=name_text, quantity=qty_from_x,
                                       unit_price=unit, total_price=total)
        if fin_count >= 1:
            total = _val(fin_indices[-1])
            if total and total > 0:
                return ReceiptItem(name=name_text, quantity=qty_from_x,
                                   unit_price=None, total_price=total)
    if fin_count == 2:
        a = _val(fin_indices[0])
        b = _val(fin_indices[1])
        if a and a > 0 and b and b > 0:
            return ReceiptItem(name=name_text, quantity=1,
                               unit_price=a, total_price=b)
    if fin_count == 1:
        total = _val(fin_indices[0])
        if total and total > 0:
            return ReceiptItem(name=name_text, quantity=1,
                               unit_price=total, total_price=total)
    return None


def extract_items(text):
    all_lines = _lines(text)
    items = []
    in_item_section = False
    for ln in all_lines:
        if in_item_section and _SUMMARY_LINE_RE.match(ln):
            break
        norm = _NOISE_RE.sub(' ', ln)
        norm = re.sub(r'\s+', ' ', norm).strip()
        if not in_item_section:
            toks = norm.split()
            fc = sum(1 for t in toks if _is_financial_token(t))
            if fc < 2:
                continue
            in_item_section = True
        item = _parse_item_line(ln)
        if item is not None:
            items.append(item)
    return items


def _estimate_item_lines(text):
    count = 0
    in_section = False
    for ln in _lines(text):
        if in_section and _SUMMARY_LINE_RE.match(ln):
            break
        norm = _NOISE_RE.sub(' ', ln)
        norm = re.sub(r'\s+', ' ', norm).strip()
        toks = norm.split()
        fn = sum(1 for t in toks if _is_financial_token(t))
        if fn >= 2:
            in_section = True
            if not _SUMMARY_LINE_RE.match(ln):
                count += 1
    return count

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


def compute_confidence(result):
    score = 0
    max_score = 0
    max_score += 25
    if result.merchant:
        score += 7
    if result.date:
        score += 7
    if result.total_amount:
        score += 6
    if result.payment_method:
        score += 3
    if result.raw_text and len(result.raw_text) > 50:
        score += 2
    max_score += 40
    est = result.estimated_items or 0
    n = len(result.items) if result.items else 0
    if est > 0:
        recall = min(n / est, 1.0)
        score += int(recall * 35)
        if n >= est:
            score += 5
    elif n > 0:
        score += 20
    max_score += 20
    if result.items and result.total_amount:
        item_sum = sum(i.total_price for i in result.items if i.total_price)
        if item_sum > 0:
            ratio = min(item_sum, result.total_amount) / max(item_sum, result.total_amount)
            score += int(ratio * 20)
    elif result.total_amount:
        score += 10
    max_score += 15
    if result.raw_text:
        low = result.raw_text.lower()
        if any(kw in low for kw in ('total belanja', 'grand total', 'total bayar')):
            score += 8
        if any(kw in low for kw in ('tunai', 'kembali', 'debit', 'qris', 'bayar')):
            score += 7
    pct = score / max_score if max_score else 0
    if pct >= 0.70:
        return "HIGH"
    if pct >= 0.40:
        return "MEDIUM"
    return "LOW"


def parse_receipt_text(raw_text):
    text = (raw_text or "").strip()
    items = extract_items(text)
    est = _estimate_item_lines(text)
    result = ReceiptScanResult(
        merchant=extract_merchant(text), date=extract_date(text),
        time=extract_time(text), total_amount=extract_total(text),
        subtotal=extract_subtotal(text), tax=extract_tax(text),
        discount=extract_discount(text),
        payment_method=extract_payment_method(text),
        items=items, raw_text=text, estimated_items=est)
    result.confidence = compute_confidence(result)
    return result


# ------------------------------------------------------------ preprocessing

_MAX_OCR_WIDTH = 2200


def preprocess_image(image_path, out_dir=None, mode='standard'):
    try:
        from PIL import Image, ImageFilter, ImageOps
    except ImportError:
        return Path(image_path)
    out_dir = out_dir or Path(image_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / (Path(image_path).stem + '_proc_' + mode + '.png')
    with Image.open(image_path) as img:
        img = ImageOps.exif_transpose(img)
        if mode == 'binary':
            img = img.convert("L")
            img = ImageOps.autocontrast(img, cutoff=5)
            if img.width > _MAX_OCR_WIDTH:
                r = _MAX_OCR_WIDTH / img.width
                img = img.resize((_MAX_OCR_WIDTH, int(img.height * r)), Image.LANCZOS)
            img = img.point(lambda p: 255 if p > 140 else 0)
        elif mode == 'adaptive':
            img = img.convert("L")
            img = ImageOps.autocontrast(img, cutoff=3)
            if img.width > _MAX_OCR_WIDTH:
                r = _MAX_OCR_WIDTH / img.width
                img = img.resize((_MAX_OCR_WIDTH, int(img.height * r)), Image.LANCZOS)
            img = img.filter(ImageFilter.SHARPEN)
            img = img.filter(ImageFilter.SHARPEN)
        else:
            img = img.convert("L")
            img = ImageOps.autocontrast(img, cutoff=1)
            if img.width > _MAX_OCR_WIDTH:
                r = _MAX_OCR_WIDTH / img.width
                img = img.resize((_MAX_OCR_WIDTH, int(img.height * r)), Image.LANCZOS)
            img = img.filter(ImageFilter.SHARPEN)
        img.save(out_path, "PNG")
    return out_path


def _score_ocr_text(text):
    if not text or not text.strip():
        return 0
    lines = _lines(text)
    score = 0
    score += any('total' in ln.lower() for ln in lines) * 4
    score += (extract_date(text) is not None) * 2
    score += min(_estimate_item_lines(text), 10)
    score += any(kw in ln.lower() for ln in lines
                 for kw in ('tunai', 'kembali', 'debit', 'qris', 'bayar')) * 3
    avg_len = sum(len(ln) for ln in lines) / max(len(lines), 1)
    if avg_len > 5:
        score += 2
    return score


# ---------------------------------------------------------------- engines


def _get_pytesseract():
    import pytesseract
    from app.config import settings
    if settings.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
    return pytesseract


def _tesseract_available():
    try:
        _get_pytesseract().get_tesseract_version()
        return True
    except Exception:
        return False


def _available_langs():
    import pytesseract
    from app.config import settings
    if settings.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
    try:
        data = pytesseract.get_languages(config="")
        langs = data.splitlines() if isinstance(data, str) else data
    except Exception:
        langs = []
    pref = settings.RECEIPT_OCR_LANG.split("+")
    ordered = [l for l in pref if l in langs]
    return ordered if ordered else (["eng"] if "eng" in langs else [])


class TesseractReceiptScannerService(ReceiptScannerService):
    def __init__(self):
        self._pytesseract = _get_pytesseract()
        self._langs = _available_langs()

    def scan(self, image_path):
        path = Path(image_path)
        proc_dir = path.parent
        lang_str = "+".join(self._langs) if self._langs else ""
        lang_kwargs = {"lang": lang_str} if lang_str else {}
        passes = [("standard", "6"), ("binary", "4"), ("adaptive", "3")]
        best_text = ""
        best_score = -1
        processed_paths = []
        for mode, psm in passes:
            try:
                proc = preprocess_image(path, out_dir=proc_dir, mode=mode)
                processed_paths.append(proc)
                text = self._pytesseract.image_to_string(
                    str(proc), config=f"--psm {psm}", **lang_kwargs)
                sc = _score_ocr_text(text)
                if sc > best_score:
                    best_score = sc
                    best_text = text
            except Exception:
                continue
        for pp in processed_paths:
            if pp != path and pp.exists():
                try:
                    pp.unlink()
                except OSError:
                    pass
        result = parse_receipt_text(best_text)
        result.status = "processed"
        return result


class OfflineReceiptScannerService(ReceiptScannerService):
    def scan(self, image_path):
        return ReceiptScanResult(status="failed", raw_text=None)


# ---------------------------------------------------------------- factory

_scanner = None


def build_scanner():
    if _tesseract_available():
        return TesseractReceiptScannerService()
    return OfflineReceiptScannerService()


def get_scanner():
    global _scanner
    if _scanner is None:
        _scanner = build_scanner()
    return _scanner


def set_scanner(scanner):
    global _scanner
    _scanner = scanner

