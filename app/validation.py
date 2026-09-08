"""Input validation helpers for forms and API."""
import re
from typing import Optional


def validate_username(username: str) -> tuple[bool, str]:
    """Validate username. Returns (is_valid, error_message)."""
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
    """Validate password. Returns (is_valid, error_message)."""
    if not password:
        return False, "Password wajib diisi"
    if len(password) < 8:
        return False, "Password minimal 8 karakter"
    if len(password) > 128:
        return False, "Password maksimal 128 karakter"
    return True, ""


def validate_amount(amount: str | int | None) -> tuple[int, str]:
    """Validate monetary amount. Returns (amount_in_rupiah, error_message)."""
    if amount is None or amount == "":
        return 0, ""
    try:
        val = int(amount)
    except (ValueError, TypeError):
        return 0, "Jumlah harus berupa angka"
    if val < 0:
        return 0, "Jumlah tidak boleh negatif"
    if val > 10_000_000_000_000:  # 10 trillion cap
        return 0, "Jumlah terlalu besar (maks 10 triliun)"
    return val, ""


def validate_account_name(name: str) -> tuple[bool, str]:
    """Validate account name. Returns (is_valid, error_message)."""
    if not name:
        return False, "Nama akun wajib diisi"
    name = name.strip()
    if len(name) < 1:
        return False, "Nama akun wajib diisi"
    if len(name) > 100:
        return False, "Nama akun maksimal 100 karakter"
    return True, ""


def validate_date(date_str: str | None) -> tuple[Optional[str], str]:
    """Validate date string (YYYY-MM-DD). Returns (date_str, error_message)."""
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


def sanitize_string(value: str | None, max_length: int = 255) -> str:
    """Sanitize a string input."""
    if not value:
        return ""
    value = value.strip()
    return value[:max_length]
