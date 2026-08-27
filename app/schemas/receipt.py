"""Receipt upload schemas (OCR pipeline)."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.transaction import TransactionCreate


class ReceiptItemResponse(BaseModel):
    name: Optional[str] = None
    quantity: Optional[int] = None
    unit_price: Optional[int] = None
    total_price: Optional[int] = None


class OcrResultResponse(BaseModel):
    """Structured OCR output (draft only - never auto-posted)."""
    merchant: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    total_amount: Optional[int] = None
    subtotal: Optional[int] = None
    tax: Optional[int] = None
    discount: Optional[int] = None
    payment_method: Optional[str] = None
    items: list[ReceiptItemResponse] = []
    confidence: str = "LOW"
    error: Optional[str] = Field(
        None, description="Present only when OCR failed")


class ReceiptResponse(BaseModel):
    receipt_id: int
    id: int
    status: str = Field(
        description="uploaded | processing | ready | confirmed | failed")
    ocr_status: str = Field(
        description="pending | processing | processed | confirmed | failed")
    original_filename: Optional[str] = None
    mime_type: str
    size_bytes: int
    file_hash: Optional[str] = Field(
        None, description="SHA-256 of original upload (duplicate detection)")
    transaction_id: Optional[int] = Field(
        None, description="Set once the user confirmed this receipt as a transaction")
    ocr: Optional[OcrResultResponse] = Field(
        None, description="Extracted draft. OCR never auto-creates transactions.")
    created_at: Optional[datetime] = None


class ReceiptConfirmRequest(TransactionCreate):
    """Explicit user confirmation turning a receipt into a real transaction.

    The body is a full valid transaction payload - nothing is inferred from
    OCR without the user sending these exact values.
    """
