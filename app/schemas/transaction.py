"""Transaction request/response schemas."""
from datetime import date as dt_date
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.models import TransactionType

TransactionTypeInput = TransactionType  # EXPENSE | INCOME | TRANSFER


def _strip_merchant(v):
    return v.strip() if isinstance(v, str) else v


def _norm_type(v):
    """Accept income/expense/transfer in any case (spec: 'income / expense')."""
    if isinstance(v, str):
        return v.upper()
    return v


class TransactionCreate(BaseModel):
    type: TransactionTypeInput = Field(description="EXPENSE or INCOME")
    amount: int = Field(gt=0, description="Amount in rupiah")
    account_id: int
    category_id: Optional[int] = Field(
        None, description="Required for income/expense, ignored for transfers"
    )
    merchant: Optional[str] = Field(None, max_length=200)
    merchant_id: Optional[int] = Field(None, description="Canonical merchant entity id")
    payment_method_id: Optional[int] = Field(None, description="Payment method id")
    fuel_product_id: Optional[int] = Field(None, description="Fuel product reference id")
    quantity_liters: Optional[float] = Field(None, gt=0, description="Fuel quantity (liters)")
    price_per_liter: Optional[int] = Field(None, ge=0, description="Fuel unit price (IDR/liter) snapshot")
    description: Optional[str] = None
    notes: Optional[str] = None
    date: Optional[dt_date] = Field(None, description="Defaults to today (ISO)")

    @field_validator("type", mode="before")
    @classmethod
    def _norm_type(cls, v):
        return _norm_type(v)

    @field_validator("merchant")
    @classmethod
    def _norm_merchant(cls, v):
        return _strip_merchant(v)


class TransactionUpdate(BaseModel):
    """Partial update - only provided fields are changed."""
    type: Optional[TransactionTypeInput] = None
    amount: Optional[int] = Field(None, gt=0)
    account_id: Optional[int] = None
    category_id: Optional[int] = None
    merchant: Optional[str] = Field(None, max_length=200)
    merchant_id: Optional[int] = None
    payment_method_id: Optional[int] = None
    fuel_product_id: Optional[int] = None
    quantity_liters: Optional[float] = Field(None, gt=0)
    price_per_liter: Optional[int] = Field(None, ge=0)
    description: Optional[str] = None
    notes: Optional[str] = None
    date: Optional[dt_date] = None
    transfer_to_account_id: Optional[int] = None

    @field_validator("type", mode="before")
    @classmethod
    def _norm_type(cls, v):
        return _norm_type(v)


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str = Field(description="EXPENSE | INCOME | TRANSFER")
    amount: int
    account_id: int
    account_name: Optional[str] = None
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    transfer_to_account_id: Optional[int] = None
    merchant: Optional[str] = None
    merchant_id: Optional[int] = None
    merchant_name: Optional[str] = None
    payment_method_id: Optional[int] = None
    fuel_product_id: Optional[int] = None
    quantity_liters: Optional[float] = None
    price_per_liter: Optional[int] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    date: dt_date
    created_at: Optional[datetime] = None


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    total: int
    page: int
    page_size: int
