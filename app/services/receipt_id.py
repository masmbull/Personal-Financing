"""Indonesian receipt understanding engine (deterministic, no AI).

Everything in this module is DETERMINISTIC post-processing applied after
OCR/vision extraction: normalization, classification, reconciliation and
confidence. It never calls a model and it never invents values.

Anti-hallucination policy:
- functions only normalize/annotate values that ALREADY exist upstream
  (Tesseract raw text or vision model output);
- unknown -> None + a warning, never a guess;
- product-name abbreviations are copied as printed ("INDM GY" stays "INDM GY");
- a QRIS logo is a payment METHOD, never a provider (provider only when the
  provider name is actually visible).

Reference policy (Indonesia only) - verified registry in
docs/RECEIPT_AI_ID.md: Bank Indonesia (QRIS/payment standard), OJK
(financial terminology), BPS (household consumption concepts), DJP
(PPN/tax terminology), official operator sites (Pertamina, PLN, ...).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

# ===========================================================================
# MONEY - Indonesian rupiah, integer only (existing app convention)
# ===========================================================================

def parse_id_money(value):
    """Strict integer Rupiah with Indonesian separator semantics.

    Dots are THOUSANDS separators in Indonesian receipts:
        "12.500" -> 12500, "125.000" -> 125000, "1.250.000" -> 1250000.
    Returns ``(amount, warning)``. Explicit decimals the integer schema
    cannot represent (e.g. "12.500,50") -> ``(None, MONEY_DECIMAL_UNSUPPORTED)``.
    Ambiguous groupings -> ``(None, MONEY_AMBIGUOUS_SEPARATOR)``. Never guesses.
    """
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, None
    if isinstance(value, int):
        return value, None
    if isinstance(value, float):
        if value == int(value):
            return int(value), None
        return None, "MONEY_DECIMAL_UNSUPPORTED"
    s = str(value).strip()
    if not s:
        return None, None
    neg = s.strip().startswith("-")
    s = s.lstrip("-").strip()
    s = re.sub(r"(?i)^rp\.?\s*", "", s)           # "Rp 12.500" / "Rp12.500"
    s = s.replace("\u00a0", "").replace(" ", "")
    s = re.sub(r"[^0-9.,]", "", s)
    if not s:
        return None, None
    if "." in s and "," in s:
        # Indonesian style: dots=thousands, comma=decimals ("12.500,00")
        intpart = s.replace(".", "").split(",")[0]
        decpart = s.split(",")[-1]
        if decpart and re.fullmatch(r"0+", decpart):
            n = int(intpart) if intpart else 0
            return (-n if neg else n), None
        return None, "MONEY_DECIMAL_UNSUPPORTED"
    if "," in s:
        parts = s.split(",")
        tail = parts[-1]
        if len(parts) > 1 and len(tail) == 3 and all(p.isdigit() for p in parts):
            n = int("".join(parts))                # 25,000 -> 25000
            return (-n if neg else n), None
        if len(tail) in (1, 2):
            return None, "MONEY_DECIMAL_UNSUPPORTED"   # "12,50"
        return None, "MONEY_AMBIGUOUS_SEPARATOR"
    if "." in s:
        parts = s.split(".")
        if all(p.isdigit() for p in parts) and all(len(p) == 3 for p in parts[1:]):
            n = int("".join(parts))                # 12.500 / 1.250.000
            return (-n if neg else n), None
        if len(parts) == 2 and len(parts[-1]) in (1, 2):
            return None, "MONEY_DECIMAL_UNSUPPORTED"   # "25.50"
        return None, "MONEY_AMBIGUOUS_SEPARATOR"
    if s.isdigit():
        n = int(s)
        return (-n if neg else n), None
    return None, "MONEY_AMBIGUOUS"


# ===========================================================================
# DATE / TIME - Indonesian receipt conventions
# ===========================================================================

_MONTHS = {
    "jan": 1, "januari": 1, "feb": 2, "februari": 2, "mar": 3, "maret": 3,
    "apr": 4, "april": 4, "mei": 5, "may": 5, "jun": 6, "juni": 6,
    "jul": 7, "juli": 7, "agu": 8, "agt": 8, "aug": 8, "agustus": 8,
    "sep": 9, "sept": 9, "september": 9, "okt": 10, "oct": 10, "oktober": 10,
    "nov": 11, "november": 11, "des": 12, "dec": 12, "desember": 12,
    "december": 12,
}

_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_DMY_RE = re.compile(r"^(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})$")
_NAME_DATE_RE = re.compile(r"^(\d{1,2})\s+([A-Za-z]+)\.?,?\s+(\d{4})$")


def normalize_id_date(value):
    """Normalize an Indonesian receipt date to ISO ``YYYY-MM-DD``.

    Supported: ISO, DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY, DD/MM/YY (Indonesian
    convention is day-first), "08 Sep 2026", "8 September 2026" (ID + EN
    month names). Returns ``(iso, warning)``; ambiguity never silently flips
    the visible date (MM/DD-looking input gets DATE_MDY_INTERPRETED).
    """
    if value is None:
        return None, None
    s = str(value).strip()
    if not s:
        return None, None
    m = _ISO_DATE_RE.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d).isoformat(), None
        except ValueError:
            return None, "DATE_INVALID"
    m = _DMY_RE.match(s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        if a > 12 and b <= 12:
            d, mo, warn = a, b, None              # unambiguous DD/MM
        elif a <= 12 and b > 12:
            d, mo, warn = b, a, "DATE_MDY_INTERPRETED"  # e.g. 09/23/2026
        elif a <= 12 and b <= 12:
            d, mo, warn = a, b, None              # DD/MM (Indonesian default)
        else:
            return None, "DATE_INVALID"
        try:
            return date(y, mo, d).isoformat(), warn
        except ValueError:
            return None, "DATE_INVALID"
    m = _NAME_DATE_RE.match(s)
    if m:
        mon = _MONTHS.get(m.group(2).lower()) or _MONTHS.get(m.group(2).lower()[:3])
        if mon:
            try:
                return date(int(m.group(3)), mon, int(m.group(1))).isoformat(), None
            except ValueError:
                return None, "DATE_INVALID"
    return None, "DATE_UNPARSED"


def normalize_id_time(value):
    """``HH:MM`` / ``HH:MM:SS`` (also dot-separated) -> canonical HH:MM[:SS]."""
    if value is None:
        return None, None
    s = str(value).strip()
    if not s:
        return None, None
    m = re.match(r"^(\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?$", s)
    if not m:
        return None, "TIME_UNPARSED"
    hh, mm, ss = int(m.group(1)), int(m.group(2)), m.group(3)
    if hh > 23 or mm > 59 or (ss and int(ss) > 59):
        return None, "TIME_INVALID"
    return (f"{hh:02d}:{mm:02d}" + (f":{ss}" if ss else "")), None


# ===========================================================================
# PAYMENT - method normalization + provider detection (BI QRIS policy:
# QRIS is a payment standard/method; a provider is only claimed when the
# provider name is actually visible on the receipt)
# ===========================================================================

CANONICAL_METHODS = ("TUNAI", "DEBIT", "KREDIT", "QRIS", "TRANSFER", "E_WALLET")

_PAYMENT_SYNONYMS = (
    ("TUNAI", ("tunai", "cash", "uang pas")),
    ("DEBIT", ("debit", "kartu debit", "debit card")),
    ("KREDIT", ("kredit", "kartu kredit", "credit card")),
    ("QRIS", ("qris",)),
    ("TRANSFER", ("transfer", "virtual account", "va number", "no. va")),
    ("E_WALLET", ("gopay", "ovo", "shopeepay", "linkaja", "e-wallet", "ewallet")),
)

# Case matters for short ambiguous names: receipts print providers in caps,
# and lowercase "dana" is a common Indonesian word (funds), not the provider.
_PROVIDER_PATTERNS = (
    ("GOPAY", re.compile(r"\bgopay\b", re.IGNORECASE)),
    ("OVO", re.compile(r"\bOVO\b")),
    ("DANA", re.compile(r"\bDANA\b")),
    ("SHOPEEPAY", re.compile(r"\bshopeepay\b", re.IGNORECASE)),
    ("LINKAJA", re.compile(r"\blinkaja\b", re.IGNORECASE)),
)


def normalize_payment_method(raw):
    """Map Indonesian payment terms to a canonical method, else None.

    Tunai/Cash -> TUNAI, Kartu Debit -> DEBIT, Kartu Kredit -> KREDIT,
    Virtual Account/Transfer -> TRANSFER, GoPay/OVO/DANA/... -> E_WALLET.
    Unknown values (e.g. "BITCOIN") -> None (never invented).
    """
    if raw is None:
        return None
    s = str(raw).strip().upper()
    if not s:
        return None
    if s in CANONICAL_METHODS:
        return s
    low = str(raw).lower()
    for canon, kws in _PAYMENT_SYNONYMS:
        if any(kw in low for kw in kws):
            return canon
    return None


def detect_payment_provider(text):
    """Return a provider name ONLY when it is actually visible in the text."""
    if not text:
        return None
    for name, pattern in _PROVIDER_PATTERNS:
        if pattern.search(text):
            return name
    return None


# ===========================================================================
# DOCUMENT CLASSIFICATION - informational only. Classification MUST NOT
# determine accounting treatment (the user picks the category).
# ===========================================================================

DOC_TYPES = (
    "RETAIL_RECEIPT", "RESTAURANT_RECEIPT", "CAFE_RECEIPT",
    "SUPERMARKET_RECEIPT", "MINIMARKET_RECEIPT", "FUEL_RECEIPT",
    "WORKSHOP_RECEIPT", "PHARMACY_RECEIPT", "HOSPITAL_RECEIPT",
    "HOTEL_RECEIPT", "PARKING_RECEIPT", "TOLL_RECEIPT", "TRANSPORT_RECEIPT",
    "UTILITY_RECEIPT", "TELCO_RECEIPT", "E_COMMERCE_RECEIPT",
    "DELIVERY_RECEIPT", "QRIS_PAYMENT_RECEIPT", "BANK_PAYMENT_RECEIPT",
    "E_WALLET_RECEIPT", "OTHER_RECEIPT", "UNKNOWN",
)

# Priority-ordered rules; the first match wins. Keep domains distinct:
# a minimarket receipt PAID with QRIS is still a MINIMARKET_RECEIPT with
# qris.detected=True - QRIS_PAYMENT_RECEIPT is for QRIS payment
# confirmations (no purchased items), not for any receipt showing QRIS.
_CLASSIFICATION_RULES = (
    ("FUEL_RECEIPT", ("spbu", "pertalite", "pertamax", "dexlite",
                      "pertamina dex", "biosolar", "bio solar", "ron 90",
                      "ron 92", "ron 95", "ron 98", "pertamina", "shell")),
    ("TOLL_RECEIPT", ("e-toll", "etoll", "e toll", "gerbang tol",
                      "jalan tol", "karcis tol")),
    ("PARKING_RECEIPT", ("karcis parkir", "parkir", "parking")),
    ("TELCO_RECEIPT", ("telkomsel", "indosat", "xl axiata", "smartfren",
                       "pulsa", "paket data", "byu ", "by.u")),
    ("UTILITY_RECEIPT", ("pln", "token listrik", "tagihan listrik", "pdam",
                         "tagihan air", "biaya air")),
    ("E_COMMERCE_RECEIPT", ("tokopedia", "shopee", "lazada", "bukalapak",
                            "blibli", "tiktok shop", "order id", "invoice")),
    ("DELIVERY_RECEIPT", ("gofood", "grabfood", "shopeefood", "ongkir",
                          "biaya pengiriman")),
    ("TRANSPORT_RECEIPT", ("go ride", "go-car", "grabcar", "transjakarta",
                           "mrt", "lrt", "kereta", "kai ", "damri", "ojek",
                           "bluebird", "taxi")),
    ("BANK_PAYMENT_RECEIPT", ("virtual account", "va number", "no. va",
                              "setoran", "atm", "bank")),
    ("E_WALLET_RECEIPT", ("top up", "topup", "isi saldo")),
    ("HOSPITAL_RECEIPT", ("rumah sakit", "puskesmas", "rawat inap",
                          "rawat jalan", "klinik")),
    ("PHARMACY_RECEIPT", ("apotek", "apotik", "kimia farma", "century",
                          "resep", "obat")),
    ("HOTEL_RECEIPT", ("hotel", "penginapan", "check-in", "menginap",
                       "per malam")),
    ("WORKSHOP_RECEIPT", ("bengkel", "ganti oli", "servis motor",
                          "service motor", "tune up", "spooring")),
    ("CAFE_RECEIPT", ("cafe", "kafe", "coffee", "kopi")),
    ("RESTAURANT_RECEIPT", ("restoran", "rumah makan", "warung", "warteg",
                            "padang", "sate", "bakso", "mie ayam",
                            "nasi goreng", "pesanan", "meja")),
    ("MINIMARKET_RECEIPT", ("indomaret", "alfamart", "alfamidi", "lawson",
                            "superindo")),
    ("SUPERMARKET_RECEIPT", ("supermarket", "hypermart", "transmart",
                             "carrefour", "lotte mart", "giant")),
    ("RETAIL_RECEIPT", ("toko", "struk belanja", "nota")),
)


def classify_document(text, result=None):
    """Classify the receipt document type from visible text (deterministic).

    Returns one of ``DOC_TYPES``. Empty text -> None (honest unknown).
    """
    low = (text or "").lower()
    if not low.strip():
        return None
    if "qris" in low and (result is None or not result.items):
        # A QRIS slip WITHOUT purchased items is a payment confirmation.
        return "QRIS_PAYMENT_RECEIPT"
    for doc_type, keywords in _CLASSIFICATION_RULES:
        if any(kw in low for kw in keywords):
            return doc_type
    return "UNKNOWN"

# ===========================================================================
# QRIS (Bank Indonesia terminology) - only visible fields, never inferred
# ===========================================================================

_NMID_RE = re.compile(r"\bNMID\s*[:#]?\s*([A-Za-z0-9]+)", re.IGNORECASE)
_REF_RE = re.compile(
    r"\bref(?:erence)?(?:\s*(?:no|number))?\s*\.?\s*[:#]?\s*([A-Za-z0-9\-/]{4,})",
    re.IGNORECASE)


def detect_qris(text, merchant=None):
    """QRIS sub-object. ``detected`` only when QRIS is actually mentioned;
    merchant_id/reference only when the printed pattern is present."""
    out = {"detected": False, "merchant_name": None, "merchant_id": None,
           "reference_number": None}
    low = (text or "").lower()
    if "qris" not in low:
        return out
    out["detected"] = True
    m = _NMID_RE.search(text or "")
    if m:
        out["merchant_id"] = m.group(1).upper()
    m = _REF_RE.search(text or "")
    if m:
        out["reference_number"] = m.group(1).upper()
    # The payee name is only claimed from the already-extracted merchant
    # field - never guessed from QRIS payload noise.
    if merchant:
        out["merchant_name"] = merchant
    return out


# ===========================================================================
# FUEL (SPBU) - Pertamina/Shell/BP/Vivo product taxonomy (official operator
# naming); prices are NEVER hardcoded - only visible values are extracted
# ===========================================================================

_FUEL_BRANDS = ("pertamina", "shell", "bp ", "vivo")
_FUEL_PRODUCTS = ("pertamax turbo", "pertamax", "pertalite", "pertamina dex",
                  "dexlite", "biosolar", "bio solar", "ron 98", "ron 95",
                  "ron 92", "ron 90")
_LITERS_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:liter|litre|ltr|l)\b",
                        re.IGNORECASE)
_PPL_RE = re.compile(
    r"(?:rp\.?\s*)?([\d.,]{3,})\s*(?:/|per|@)\s*(?:rp\.?\s*)?(?:liter|litre|ltr|l)\b",
    re.IGNORECASE)


def detect_fuel(text, total_amount=None):
    """Fuel sub-object for SPBU receipts. Liters are a quantity (float ok);
    money fields stay integer rupiah. Only visible values are returned."""
    out = {"detected": False, "brand": None, "product": None,
           "quantity_liters": None, "price_per_liter": None, "total": None}
    low = (text or "").lower()
    if not low:
        return out
    brand = next((b.strip().upper() for b in _FUEL_BRANDS if b in low), None)
    product = next((p.upper() for p in _FUEL_PRODUCTS if p in low), None)
    liters = None
    m = _LITERS_RE.search(low)
    if m:
        try:
            liters = round(float(m.group(1).replace(",", ".")), 3)
        except ValueError:
            liters = None
    price_per_liter = None
    m = _PPL_RE.search(low)
    if m:
        price_per_liter, _ = parse_id_money(m.group(1))
    detected = bool(brand or product or (liters is not None and price_per_liter))
    if not detected:
        return out
    out.update(detected=True, brand=brand, product=product,
               quantity_liters=liters, price_per_liter=price_per_liter,
               total=total_amount)
    return out

# ===========================================================================
# ITEMS - quantity / unit parsing ("2 x 5.000", "2 @ 5.000", "2PCS", "0.5KG")
# ===========================================================================

_QTY_MULTIPLIER_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:x|@|\*)\s*(?:rp\.?\s*)?([\d.,]+)", re.IGNORECASE)
_QTY_UNIT_RE = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(pcs|pack|btl|botol|kg|gr|gram|mgr|mg|ml|ltr|l)\b",
    re.IGNORECASE)


def parse_qty_unit(text):
    """``"2 x 5.000"`` / ``"2 @ 5.000"`` / ``"2PCS"`` / ``"0.5KG"`` ->
    ``(quantity, unit, unit_price)``. Deterministic; never assumes qty=1."""
    if not text:
        return None, None, None
    s = str(text).strip()
    m = _QTY_MULTIPLIER_RE.search(s)
    if m:
        try:
            qty = float(m.group(1).replace(",", "."))
        except ValueError:
            qty = None
        amt, _ = parse_id_money(m.group(2))
        return qty, None, amt
    m = _QTY_UNIT_RE.search(s)
    if m:
        try:
            qty = float(m.group(1).replace(",", "."))
        except ValueError:
            qty = None
        return qty, m.group(2).upper(), None
    return None, None, None


# ===========================================================================
# RECEIPT METADATA - struk/nota/invoice numbers, address, phone
# ===========================================================================

_RECEIPT_NO_RE = re.compile(
    r"\bno\.?\s*(?:struk|nota|transaksi|bukti|resi)\s*\.?\s*[:#]?\s*"
    r"([A-Za-z0-9][A-Za-z0-9\-/.]{2,})", re.IGNORECASE)
_INVOICE_NO_RE = re.compile(
    r"\binvoice\s*(?:no)?\.?\s*[:#]?\s*([A-Za-z0-9][A-Za-z0-9\-/.]{2,})",
    re.IGNORECASE)
_ADDRESS_RE = re.compile(r"^\s*(?:jl\.?|jalan)\s+(.{4,80})$", re.IGNORECASE)
_PHONE_RE = re.compile(
    r"\b(?:telp|tel|tlp|hp|wa|whatsapp)\s*\.?\s*[:#]?\s*(\+?\d[\d\-. ]{6,})",
    re.IGNORECASE)


def extract_receipt_metadata(text):
    """(receipt_number, invoice_number, merchant_address, merchant_phone).

    Deterministic label-based extraction; missing -> None (no invention).
    """
    receipt_no = invoice_no = address = phone = None
    for ln in _receipt_lines(text):
        if receipt_no is None:
            m = _RECEIPT_NO_RE.search(ln)
            if m:
                receipt_no = m.group(1).strip()
        if invoice_no is None:
            m = _INVOICE_NO_RE.search(ln)
            if m:
                invoice_no = m.group(1).strip()
        if address is None:
            m = _ADDRESS_RE.match(ln)
            if m:
                address = m.group(1).strip()
        if phone is None:
            m = _PHONE_RE.search(ln)
            if m:
                digits = re.sub(r"[^\d+]", "", m.group(1))
                phone = digits if len(re.sub(r"\D", "", digits)) >= 7 else None
    return receipt_no, invoice_no, address, phone


def _receipt_lines(text):
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


# ===========================================================================
# RECONCILIATION - never silently choose between conflicting numbers
# ===========================================================================

def reconcile(result, *, ocr_total=None):
    """Deterministic arithmetic reconciliation. Returns a warnings list.

    expected_total = subtotal - discount + tax + service_charge
                     + delivery_fee + shipping_fee + other_fee + rounding
    Only runs when the needed values are actually present (no guessing);
    tolerance allows small printed rounding differences.
    """
    warnings = []
    total = result.total_amount
    subtotal = result.subtotal
    parts = {
        "discount": result.discount, "tax": result.tax,
        "service_charge": result.service_charge,
        "delivery_fee": result.delivery_fee,
        "shipping_fee": result.shipping_fee,
        "rounding": result.rounding, "other_fee": result.other_fee,
    }
    if total and subtotal is not None:
        expected = subtotal - (parts["discount"] or 0) + (parts["tax"] or 0)
        expected += (parts["service_charge"] or 0) + (parts["delivery_fee"] or 0)
        expected += (parts["shipping_fee"] or 0) + (parts["other_fee"] or 0)
        expected += (parts["rounding"] or 0)
        tol = max(2, int(abs(total) * 0.005))
        if abs(expected - total) > tol:
            warnings.append("TOTAL_MISMATCH")
    if subtotal and result.items:
        item_sum = sum(i.total_price or 0 for i in result.items)
        if item_sum and abs(item_sum - subtotal) > 2:
            warnings.append("ITEM_SUM_MISMATCH")
    if ocr_total and total and ocr_total != total:
        warnings.append("TOTAL_CONFLICT")
    return warnings


# ===========================================================================
# CONFIDENCE - always computed server-side; the model never invents it
# ===========================================================================

_FIELD_WEIGHTS = {
    "total_amount": 3, "merchant": 2, "date": 2, "items": 2,
    "payment_method": 1, "subtotal": 1, "tax": 1, "discount": 1,
}


def compute_field_confidence(result, *, ocr_total=None):
    """Per-field 0..1 confidence from deterministic signals only:
    presence, format validity, arithmetic reconciliation, OCR agreement."""
    fc = {}
    warnings = set(result.warnings or [])

    fc["merchant"] = 0.0
    if result.merchant:
        fc["merchant"] = 0.7 + (0.2 if len(result.merchant) >= 4 else 0.0)
        fc["merchant"] += 0.1 if result.merchant == result.merchant.upper() else 0.0

    if result.date:
        fc["date"] = 0.85 + (0.15 if not any(
            w.startswith("DATE_") for w in warnings) else 0.0)
    else:
        fc["date"] = 0.0
    fc["time"] = 0.8 if result.time else 0.0

    total = result.total_amount
    if total:
        c = 0.7
        if "TOTAL_MISMATCH" not in warnings:
            c += 0.15
        if ocr_total is not None:
            c += 0.15 if ocr_total == total else -0.35
        fc["total_amount"] = max(0.05, min(1.0, c))
    else:
        fc["total_amount"] = 0.0

    item_sum = sum(i.total_price or 0 for i in (result.items or []))
    for key in ("subtotal", "tax", "discount"):
        val = getattr(result, key)
        if val is None:
            fc[key] = 0.0
        else:
            c = 0.7
            if key == "subtotal" and item_sum and abs(item_sum - val) <= 2:
                c += 0.2                       # item sums agree
            if "ITEM_SUM_MISMATCH" in warnings and key == "subtotal":
                c -= 0.2
            fc[key] = max(0.05, min(1.0, c))

    if result.payment_method:
        c = 0.75
        if result.payment_provider:
            c += 0.15
        fc["payment_method"] = min(1.0, c)
    else:
        fc["payment_method"] = 0.0

    n_items = len(result.items or [])
    fc["items"] = min(1.0, 0.5 + 0.1 * min(n_items, 5)) if n_items else 0.0

    return {k: round(v, 2) for k, v in fc.items()}


def confidence_score_from(field_confidence):
    """Weighted mean over the extracted core fields (0..1)."""
    num = den = 0.0
    for key, weight in _FIELD_WEIGHTS.items():
        v = field_confidence.get(key)
        if v is not None and v > 0:
            num += v * weight
            den += weight
    return round(num / den, 2) if den else 0.0

# ===========================================================================
# ENRICH - single entry point applied to every successful scan result
# ===========================================================================

def _empty_qris():
    return {"detected": False, "merchant_name": None, "merchant_id": None,
            "reference_number": None}


def _empty_fuel():
    return {"detected": False, "brand": None, "product": None,
            "quantity_liters": None, "price_per_liter": None, "total": None}


def enrich_scan_result(result, *, ocr_text=None, ocr_total=None):
    """Apply the deterministic Indonesian engine to a successful scan result.

    Mutates and returns ``result`` (backward compatible: all pre-existing
    fields keep their meaning; ``confidence`` string is preserved, only
    downgraded on arithmetic conflicts). Never invents values.
    """
    text = ocr_text or getattr(result, "raw_text", None) or ""
    warnings = list(getattr(result, "warnings", None) or [])

    # --- date/time: accept Indonesian formats, normalize deterministically
    if result.date:
        iso, warn = normalize_id_date(result.date)
        if iso:
            result.date = iso
            if warn:
                warnings.append(warn)
        else:
            warnings.append(warn or "DATE_UNPARSED")
            result.date = None
    if result.time:
        t, warn = normalize_id_time(result.time)
        if t:
            result.time = t
        else:
            warnings.append(warn or "TIME_UNPARSED")
            result.time = None

    # --- payment: canonical method + provider ONLY when visible
    if result.payment_method:
        method = normalize_payment_method(result.payment_method)
        if method:
            result.payment_method = method
        else:
            warnings.append("PAYMENT_METHOD_UNRECOGNIZED")
            result.payment_method = None
    provider = detect_payment_provider(text)
    if provider is None and result.payment_method != "QRIS":
        # Model-claimed provider accepted (whitelisted) for non-QRIS methods;
        # for QRIS the BI policy forbids QRIS->provider conversion unless the
        # provider name is actually visible in the receipt text.
        raw_provider = str(getattr(result, "payment_provider", None) or "").upper()
        known = {name for name, _ in _PROVIDER_PATTERNS}
        provider = raw_provider if raw_provider in known else None
    result.payment_provider = provider

    # --- document type: deterministic classifier wins when text exists
    doc_type = classify_document(text, result) if text else None
    if doc_type is None:
        model_dt = getattr(result, "document_type", None)
        doc_type = model_dt if model_dt in DOC_TYPES else None
    result.document_type = doc_type

    # --- deterministic sub-objects (never trusted from the model)
    result.qris = detect_qris(text, merchant=result.merchant) if text else _empty_qris()
    if not result.qris["detected"] and result.payment_method == "QRIS":
        result.qris = {"detected": True, "merchant_name": result.merchant,
                       "merchant_id": None, "reference_number": None}
    result.fuel = detect_fuel(text, total_amount=result.total_amount) if text \
        else _empty_fuel()

    # --- metadata: the deterministic text reading WINS over the model's
    # claim (text is the ground truth source; model strings are only a
    # fallback when no OCR text is available)
    if text:
        rno, inv, addr, phone = extract_receipt_metadata(text)
        result.receipt_number = rno or result.receipt_number
        result.invoice_number = inv or result.invoice_number
        result.merchant_address = addr or result.merchant_address
        result.merchant_phone = phone or result.merchant_phone

    # --- reconciliation + confidence
    warnings.extend(reconcile(result, ocr_total=ocr_total))
    seen, deduped = set(), []
    for w in warnings:
        if w and w not in seen:
            seen.add(w)
            deduped.append(w)
    result.warnings = deduped
    result.field_confidence = compute_field_confidence(result, ocr_total=ocr_total)
    result.confidence_score = confidence_score_from(result.field_confidence)
    if any(w in result.warnings for w in ("TOTAL_MISMATCH", "TOTAL_CONFLICT")):
        if result.confidence == "HIGH":
            result.confidence = "MEDIUM"
    return result

# ---CHUNK-END---