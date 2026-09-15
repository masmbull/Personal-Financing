"""CSV Import service — parse bank statement CSVs and batch-create transactions."""
import csv
import io
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import Account, TransactionType
from app.services.finance import create_transaction

_DATE_FORMATS = [
    "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y",
    "%d %b %Y", "%d %b %y", "%d %B %Y",
]
_DESCRIPTION_ALIASES = {"keterangan", "description", "deskripsi", "memo", "note", "catatan", "berita"}
_DATE_ALIASES = {"date", "tanggal", "tgl", "transaction date", "posting date"}
_AMOUNT_ALIASES = {"amount", "jumlah", "nominal", "debit", "kredit", "credit", "value"}
_TYPE_ALIASES = {"type", "jenis", "tipe", "tx_type"}


def _parse_date(raw: str) -> Optional[date]:
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(raw: str) -> Optional[int]:
    raw = raw.strip()
    if not raw:
        return None
    # Strip currency prefix first, then separators
    raw = raw.replace("IDR", "").replace("Rp.", "").replace("Rp", "").replace("rp", "").strip()
    negative = raw.startswith("-")
    if negative:
        raw = raw[1:].strip()
    # Remove thousand separators (dots in Indonesian format, commas in Western)
    raw = raw.replace(".", "").replace(",", "").strip()
    try:
        val = int(raw)
        return -val if negative else val
    except ValueError:
        return None


def _detect_columns(headers: list[str]) -> dict:
    mapping = {"description": None, "date": None, "amount": None, "type": None}
    lower = [h.lower().strip() for h in headers]
    for i, h in enumerate(lower):
        if h in _DESCRIPTION_ALIASES and mapping["description"] is None:
            mapping["description"] = i
        elif h in _DATE_ALIASES and mapping["date"] is None:
            mapping["date"] = i
        elif h in _AMOUNT_ALIASES and mapping["amount"] is None:
            mapping["amount"] = i
        elif h in _TYPE_ALIASES and mapping["type"] is None:
            mapping["type"] = i
    return mapping


def parse_csv(content: str, *, delimiter: str = ",",
               col_date: int | None = None,
               col_description: int | None = None,
               col_amount: int | None = None,
               col_type: int | None = None) -> dict:
    """Parse CSV string → {"headers", "rows", "errors", "column_map"}."""
    reader = csv.reader(io.StringIO(content), delimiter=delimiter)
    rows_raw = list(reader)
    if not rows_raw:
        return {"headers": [], "rows": [], "errors": ["Empty CSV"], "column_map": {}}
    header_idx = 0
    for i, row in enumerate(rows_raw):
        if any(cell.strip() for cell in row):
            header_idx = i
            break
    headers = [h.strip() for h in rows_raw[header_idx]]
    num_cols = len(headers)
    data_rows = rows_raw[header_idx + 1:]
    detected = _detect_columns(headers)
    col_map = {
        "date": col_date if col_date is not None else detected["date"],
        "description": col_description if col_description is not None else detected["description"],
        "amount": col_amount if col_amount is not None else detected["amount"],
        "type": col_type if col_type is not None else detected["type"],
    }
    result_rows = []
    errors = []
    for i, row in enumerate(data_rows):
        line_num = header_idx + 2 + i
        if not any(cell.strip() for cell in row):
            continue
        padded = row + [""] * (num_cols - len(row))
        desc = padded[col_map["description"]].strip() if col_map["description"] is not None else ""
        raw_date = padded[col_map["date"]].strip() if col_map["date"] is not None else ""
        raw_amount = padded[col_map["amount"]].strip() if col_map["amount"] is not None else ""
        raw_type = padded[col_map["type"]].strip().upper() if col_map["type"] is not None else ""
        parsed_date = _parse_date(raw_date) if raw_date else None
        parsed_amount = _parse_amount(raw_amount) if raw_amount else None
        if not parsed_date:
            errors.append(f"Baris {line_num}: tanggal tidak valid '{raw_date}'")
            continue
        if parsed_amount is None or parsed_amount == 0:
            errors.append(f"Baris {line_num}: jumlah tidak valid '{raw_amount}'")
            continue
        tx_type = "EXPENSE"
        if raw_type in ("INCOME", "PEMASUKAN", "CREDIT", "CR"):
            tx_type = "INCOME"
        elif raw_type in ("EXPENSE", "PENGELUARAN", "DEBIT", "DR"):
            tx_type = "EXPENSE"
        result_rows.append({
            "date": parsed_date.isoformat(),
            "description": desc,
            "amount": abs(parsed_amount),
            "type": tx_type,
        })
    return {"headers": headers, "rows": result_rows, "errors": errors, "column_map": detected}


def import_transactions(
    db: Session, *, user_id: int, account_id: int,
    rows: list[dict], default_category_id: int | None = None,
) -> dict:
    """Bulk-create transactions from parsed CSV rows."""
    account = db.query(Account).filter(
        Account.id == account_id, Account.user_id == user_id
    ).first()
    if not account:
        raise ValueError("Account not found")
    created = 0
    errors = []
    for i, row in enumerate(rows):
        try:
            tx_type = TransactionType(row.get("type", "EXPENSE").upper())
            amount = int(row["amount"])
            if amount <= 0:
                errors.append(f"Baris {i + 1}: jumlah harus positif")
                continue
            d = date.fromisoformat(row["date"]) if row.get("date") else date.today()
            create_transaction(
                db, user_id=user_id, type=tx_type, amount=amount,
                account_id=account_id, category_id=default_category_id,
                date_val=d, description=row.get("description", ""),
            )
            created += 1
        except Exception as e:
            errors.append(f"Baris {i + 1}: {e}")
    return {"created": created, "errors": errors}
