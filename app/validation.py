"""Input validation helpers for forms and API.

Canonical parsers for Indonesian Rupiah (IDR) input. Every numeric field
that passes through form data should go through the appropriate parser
here BEFORE reaching service/domain code.
"""
import math
import re
from typing import Optional

MAX_MONEY = 10_000_000_000_000


def parse_idr_input(value, field_name: str = "Nominal") -> int:
    """Parse IDR-formatted value to canonical integer.

    Canonical accepted grammar (STRICT):

        optional-ws ["Rp"] optional-ws DIGITS ("." DIGITS{3})* optional-ws

    - Only the Indonesian dot thousands separator is supported.
    - "Rp" prefix (case-insensitive) followed by optional space is allowed.
    - Whitespace is normalized via strip.
    - Comma, fraction/decimal, and any other symbol or letter are REJECTED.
    - Negative values re rejected (all money fields are positive here).

    Examples ACCEPTED (-> canonical integer):
        10000      -> 10000
        10.000     -> 10000
        1.000.000  -> 1000000
        Rp 10.000  -> 10000

    Examples REJECTED (ValueError):
        10..000      malformed separator
        1.2.3.4      malformed grouping
        10abc000     embedded letters
        $10000       unsupported currency symbol
        25,000       comma grouping ambiguous
        10.000,50    fractional RUupiah
        1e5          scientific
        NaN / Infinity
        -10000       negative
        0            where gt=0 (enforced by caller semantics below)
        empty / None
    """
    if value is None:
        raise ValueError(f"{field_name} harus diisi")
    if isinstance(value, int):
        if value <= 0:
            raise ValueError(f"{field_name} harus lebih dari 0")
        if value > MAX_MONEY:
            raise ValueError(f"{field_name} terlalu besar")
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError(f"{field_name} tidak valid")
        if value != int(value):
            raise ValueError(f"{field_name} harus berupa angka bulat")
        return int(value)
    s = str(value).strip()
    if not s:
        raise ValueError(f"{field_name} harus diisi")
    # Optional "Rp" prefix (case-insensitive).
    s = re.sub(r"^[Rr][Pp]\s*", "", s)
    s = s.replace("\u00a0", " ").replace(" ", "")
    # Strict grammar: DIGITS ("." DIGITS{3})*  -- dot as the ONLY grouping char.
    if not re.match(r"^\d+(\.\d{3})*$", s):
        raise ValueError(
            f"{field_name} harus berupa angka bulat (contoh: 10000 atau 10.000)"
        )
    digits = s.replace(".", "")
    if not digits:
        raise ValueError(f"{field_name} harus berupa angka")
    try:
        val = int(digits)
    except (ValueError, OverflowError):
        raise ValueError(f"{field_name} tidak valid")
    if val <= 0:
        raise ValueError(f"{field_name} harus lebih dari 0")
    if val > MAX_MONEY:
        raise ValueError(f"{field_name} terlalu besar")
    return val


def parse_optional_idr(value, field_name: str = "Nominal") -> Optional[int]:
    """Like parse_idr_input but returns None for empty input."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return parse_idr_input(value, field_name)


def parse_int_input(value, field_name: str = "Nilai",
                     min_val: int = 0, max_val: int = 2**31) -> int:
    """Parse strict integer (day, month, year, count)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{field_name} harus diisi")
    if isinstance(value, int):
        if value < min_val or value > max_val:
            raise ValueError(f"{field_name} harus antara {min_val} dan {max_val}")
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value) or value != int(value):
            raise ValueError(f"{field_name} harus berupa angka bulat")
        return int(value)
    s = str(value).strip()
    if re.search(r"[eE.,]", s):
        raise ValueError(f"{field_name} harus berupa angka bulat")
    if not re.match(r"^-?\d+$", s):
        raise ValueError(f"{field_name} harus berupa angka")
    val = int(s)
    if val < min_val or val > max_val:
        raise ValueError(f"{field_name} harus antara {min_val} dan {max_val}")
    return val


def parse_float_input(value, field_name: str = "Nilai",
                       min_val: float = 0.0, max_val: float = 1e12,
                       allow_zero: bool = True) -> float:
    """Parse decimal/float field (quantity_liters, percentage)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{field_name} harus diisi")
    if isinstance(value, (int, float)):
        fval = float(value)
        if math.isnan(fval) or math.isinf(fval):
            raise ValueError(f"{field_name} tidak valid")
        if not allow_zero and fval <= min_val:
            raise ValueError(f"{field_name} harus lebih dari {min_val}")
        if fval < min_val or fval > max_val:
            raise ValueError(f"{field_name} di luar batas yang diizinkan")
        return fval
    s = str(value).strip()
    if re.search(r"[eE]", s):
        raise ValueError(f"{field_name} tidak valid")
    s = s.replace(",", ".")
    if not re.match(r"^-?\d+(\.\d+)?$", s):
        raise ValueError(f"{field_name} harus berupa angka")
    try:
        fval = float(s)
    except (ValueError, OverflowError):
        raise ValueError(f"{field_name} tidak valid")
    if math.isnan(fval) or math.isinf(fval):
        raise ValueError(f"{field_name} tidak valid")
    if not allow_zero and fval <= min_val:
        raise ValueError(f"{field_name} harus lebih dari {min_val}")
    if fval < min_val or fval > max_val:
        raise ValueError(f"{field_name} di luar batas yang diizinkan")
    return fval


# ----------------------------------------------------------- other validators

def validate_username(username: str) -> tuple[bool, str]:
    if not username:
        return False, "Username wajib diisi"
    username = username.strip()
    if len(username) < 3:
        return False, "Username minimal 3 karakter"
    if len(username) > 50:
        return False, "Username maksimal 50 karakter"
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        return False, "Username hanya boleh huruf, angka, dan underscore"
    return True, ""


def validate_password(password: str) -> tuple[bool, str]:
    if not password:
        return False, "Password wajib diisi"
    if len(password) < 8:
        return False, "Password minimal 8 karakter"
    if len(password) > 128:
        return False, "Password maksimal 128 karakter"
    return True, ""


def validate_amount(amount, error_as_str: bool = False):
    """Legacy: prefer parse_idr_input(). Returns (int, str) or (0, str)."""
    if amount is None or amount == "":
        return 0, ""
    try:
        val = parse_idr_input(amount)
    except (ValueError, TypeError) as e:
        return 0, str(e) if str(e) else "Jumlah harus berupa angka"
    return val, ""


def validate_account_name(name: str) -> tuple[bool, str]:
    if not name:
        return False, "Nama akun wajib diisi"
    name = name.strip()
    if len(name) < 1:
        return False, "Nama akun wajib diisi"
    if len(name) > 100:
        return False, "Nama akun maksimal 100 karakter"
    return True, ""


def validate_date(date_str) -> tuple[Optional[str], str]:
    if not date_str:
        return None, ""
    date_str = date_str.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return None, "Format tanggal harus YYYY-MM-DD"
    try:
        from datetime import datetime
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None, "Tanggal tidak valid"
    return date_str, ""


def sanitize_string(value, max_length: int = 255) -> str:
    if not value:
        return ""
    value = value.strip()
    return value[:max_length]
