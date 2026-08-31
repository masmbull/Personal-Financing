"""Receipt upload + scanner abstraction.

Current state: images are validated and stored safely; OCR is a stub.

IMPORTANT RULE: OCR output must NEVER automatically create a financial
transaction. A human must confirm extracted data first - only then may a
transaction be created through the normal transaction API.
"""
import hashlib
import json
import re
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.models.models import Receipt, ReceiptStatus

ALLOWED_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
}


class ReceiptValidationError(ValueError):
    pass


class ReceiptScannerService(ABC):
    """Abstraction so an OCR engine can be plugged in later without touching
    routes or storage logic.

    Pipeline contract: image -> scan() -> structured receipt data.
    Implementations MUST NOT create transactions; they only return data for
    explicit user confirmation.
    """

    @abstractmethod
    def scan(self, image_path: str) -> dict:
        """Return structured receipt data or raise NotImplementedError."""


class StubReceiptScannerService(ReceiptScannerService):
    """Legacy placeholder - superseded by the engines in receipt_ocr.py."""

    def scan(self, image_path: str) -> dict:
        raise NotImplementedError("OCR is not implemented in this stub")


def get_scanner():
    """Return the current OCR engine (Tesseract when available, else offline)."""
    from app.services.receipt_ocr import get_scanner as _get
    return _get()


def set_scanner(scanner) -> None:
    """Swap the OCR engine - used by tests to inject deterministic scanners."""
    from app.services.receipt_ocr import set_scanner as _set
    _set(scanner)


class ReceiptNotFound(Exception):
    pass


class ReceiptAlreadyConfirmed(Exception):
    """One receipt maps to exactly one user-confirmed transaction."""


def _validate_image_bytes(mime: str, content: bytes) -> None:
    """Decode-validate JPEG/PNG/WebP. HEIC can't be decoded without a plugin,
    so it is accepted on signature + MIME trust (matches the allowed list)."""
    if mime == "image/heic":
        return
    try:
        from PIL import Image
        import io
        with Image.open(io.BytesIO(content)) as img:
            img.verify()
    except Exception:
        raise ReceiptValidationError("Berkas bukan gambar yang valid")


def save_receipt(db: Session, upload: UploadFile, user_id: int) -> Receipt:
    """Validate MIME type + size + image bytes, store the file safely,
    compute the duplicate-detection hash, persist metadata."""
    mime = (upload.content_type or "").lower()
    ext = ALLOWED_MIME_TYPES.get(mime)
    if not ext:
        raise ReceiptValidationError(
            f"Unsupported file type '{mime}'. Allowed: "
            + ", ".join(sorted(ALLOWED_MIME_TYPES))
        )

    max_bytes = settings.RECEIPT_MAX_SIZE_MB * 1024 * 1024
    content = upload.file.read()
    size = len(content)
    if size == 0:
        raise ReceiptValidationError("Empty file")
    if size > max_bytes:
        raise ReceiptValidationError(
            f"File too large ({size} bytes); max {settings.RECEIPT_MAX_SIZE_MB} MB"
        )
    _validate_image_bytes(mime, content)

    file_hash = hashlib.sha256(content).hexdigest()

    now = datetime.utcnow()
    rel_dir = Path(settings.RECEIPT_UPLOAD_DIR) / f"{now:%Y}" / f"{now:%m}"
    rel_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    stored_path = rel_dir / filename
    stored_path.write_bytes(content)

    receipt = Receipt(
        user_id=user_id,
        original_filename=upload.filename,
        stored_path=str(stored_path),
        mime_type=mime,
        size_bytes=size,
        file_hash=file_hash,
        ocr_status=ReceiptStatus.PENDING,
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return receipt


def duplicate_for(db: Session, receipt: Receipt, user_id: int) -> Optional[Receipt]:
    """Return an earlier receipt with the same file hash (same user), or None."""
    if not receipt.file_hash:
        return None
    return (
        db.query(Receipt)
        .filter(Receipt.file_hash == receipt.file_hash,
                Receipt.user_id == user_id,
                Receipt.id != receipt.id)
        .order_by(Receipt.id)
        .first()
    )


def get_receipt(db: Session, receipt_id: int, user_id: int) -> Receipt:
    receipt = db.query(Receipt).filter(
        Receipt.id == receipt_id, Receipt.user_id == user_id
    ).first()
    if not receipt:
        raise ReceiptNotFound(f"Receipt {receipt_id} not found")
    return receipt


def list_receipts(db: Session, user_id: int, limit: int = 50, offset: int = 0):
    return (
        db.query(Receipt)
        .filter(Receipt.user_id == user_id)
        .order_by(Receipt.created_at.desc())
        .offset(offset)
        .limit(min(limit, 200))
        .all()
    )


def confirm_receipt(db: Session, receipt_id: int, user_id: int, *, type, amount: int,
                    account_id: int, category_id: int | None,
                    tx_date, description: str | None = None,
                    merchant: str | None = None,
                    notes: str | None = None):
    """Turn a receipt into a real transaction - ONLY via explicit user action.

    The transaction values come from the request body (the human's decision),
    never from stored OCR output.
    """
    from app.services.finance import create_transaction

    receipt = get_receipt(db, receipt_id, user_id)
    if receipt.transaction_id is not None:
        raise ReceiptAlreadyConfirmed(
            f"Receipt {receipt_id} already confirmed as transaction "
            f"{receipt.transaction_id}"
        )
    tx = create_transaction(
        db=db, user_id=user_id, type=type, amount=amount, account_id=account_id,
        category_id=category_id, date_val=tx_date,
        description=description, merchant=merchant, notes=notes,
    )
    receipt.transaction_id = tx.id
    receipt.ocr_status = ReceiptStatus.CONFIRMED
    db.commit()
    db.refresh(receipt)
    return receipt, tx


# --------------------------------------------------------------- OCR running


def mark_processing(db: Session, receipt_id: int, user_id: int) -> Receipt:
    """Explicit UPLOADED -> PROCESSING transition (observable for tests/UI)."""
    receipt = get_receipt(db, receipt_id, user_id)
    if receipt.transaction_id is not None:
        return receipt
    receipt.ocr_status = ReceiptStatus.PROCESSING
    db.commit()
    db.refresh(receipt)
    return receipt


def run_ocr(db: Session, receipt_id: int, user_id: int,
            scanner=None) -> Receipt:
    """UPLOADED -> PROCESSING -> READY (PROCESSED) or FAILED.

    Runs the configured OCR engine and stores its structured output in
    ocr_data. NEVER creates a transaction - that requires explicit
    confirmation. Idempotent for already-confirmed receipts.
    """
    from app.services.receipt_ocr import ReceiptScanResult

    receipt = get_receipt(db, receipt_id, user_id)
    if receipt.transaction_id is not None:
        return receipt
    receipt.ocr_status = ReceiptStatus.PROCESSING
    db.commit()

    engine = scanner or get_scanner()
    try:
        result = engine.scan(receipt.stored_path)
        if not isinstance(result, ReceiptScanResult):
            if isinstance(result, dict):
                result = ReceiptScanResult(**result)
            else:
                result = ReceiptScanResult(status="processed")
        receipt.ocr_data = json.dumps(result.to_dict())
        receipt.ocr_status = ReceiptStatus.PROCESSED
    except Exception as e:  # noqa: BLE001 - OCR failure is a normal outcome
        receipt.ocr_data = json.dumps({"status": "failed", "error": str(e)})
        receipt.ocr_status = ReceiptStatus.FAILED
    db.commit()
    db.refresh(receipt)
    return receipt


def delete_receipt(db: Session, receipt_id: int, user_id: int,
                   *, remove_file: bool = False) -> None:
    """Delete receipt metadata; optionally the stored file, but ONLY if it
    lives inside the configured upload directory (never arbitrary paths)."""
    receipt = get_receipt(db, receipt_id, user_id)
    stored = Path(receipt.stored_path).resolve()
    db.delete(receipt)
    db.commit()
    if not remove_file:
        return
    allowed_root = Path(settings.RECEIPT_UPLOAD_DIR).resolve()
    if allowed_root in stored.parents and stored.is_file():
        try:
            stored.unlink()
        except OSError:
            pass


def read_receipt_file(db: Session, receipt_id: int, user_id: int):
    """Return a Path to the stored image for safe serving, or None.

    Containment is enforced against the configured upload directory so a
    tampered DB path can never expose arbitrary filesystem content.
    """
    receipt = get_receipt(db, receipt_id, user_id)
    try:
        stored = Path(receipt.stored_path).resolve()
    except (OSError, ValueError):
        return None
    allowed_root = Path(settings.RECEIPT_UPLOAD_DIR).resolve()
    if allowed_root not in stored.parents or not stored.is_file():
        return None
    return stored


_STATUS_SHAPE = {
    ReceiptStatus.PENDING: ("uploaded", "pending"),
    ReceiptStatus.PROCESSING: ("processing", "processing"),
    ReceiptStatus.PROCESSED: ("ready", "processed"),
    ReceiptStatus.CONFIRMED: ("confirmed", "confirmed"),
    ReceiptStatus.FAILED: ("failed", "failed"),
}
_OCR_FIELDS = ("merchant", "date", "time", "total_amount", "subtotal", "tax",
               "discount", "payment_method", "items", "confidence")


def _parse_ocr_data(blob):
    """Parse OCR JSON blob → namespace (attribute access safe for Jinja2).

    Returns a ``types.SimpleNamespace`` so that template dot-access never
    collides with ``dict`` built-in methods (``items``, ``keys``, …).
    Returns ``None`` when there is no usable data.
    """
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    # Recursively convert dicts to namespaces so nested objects (items list
    # entries are dicts too) also support attribute access.
    from types import SimpleNamespace

    def _to_ns(obj):
        if isinstance(obj, dict):
            return SimpleNamespace(**{k: _to_ns(v) for k, v in obj.items()})
        if isinstance(obj, list):
            return [_to_ns(i) for i in obj]
        return obj

    return _to_ns(data)


def to_response_dict(receipt: Receipt) -> dict:
    status, ocr_status = _STATUS_SHAPE.get(
        receipt.ocr_status, ("uploaded", "pending"))
    data = _parse_ocr_data(receipt.ocr_data)

    if status == "failed":
        err = getattr(data, "error", None) if data else None
        ocr = {"error": err or "OCR processing failed"}
    elif data:
        ocr = {k: getattr(data, k, None) for k in _OCR_FIELDS}
    else:
        ocr = None

    return {
        "receipt_id": receipt.id,
        "id": receipt.id,
        "status": status,
        "ocr_status": ocr_status,
        "original_filename": receipt.original_filename,
        "mime_type": receipt.mime_type,
        "size_bytes": receipt.size_bytes,
        "file_hash": receipt.file_hash,
        "transaction_id": receipt.transaction_id,
        "ocr": ocr,
        "created_at": receipt.created_at,
    }
