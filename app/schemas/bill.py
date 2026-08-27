"""Bill schemas."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import BillFrequency


class BillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    amount: int = Field(gt=0)
    frequency: BillFrequency = BillFrequency.MONTHLY
    category_id: Optional[int] = None
    account_id: Optional[int] = Field(
        None, description="Default account used when paying this bill"
    )
    due_day: Optional[int] = Field(
        None, ge=1, le=31,
        description="Day of period the bill is due (day of month for MONTHLY/YEARLY, weekday 0-6 for WEEKLY)",
    )
    auto_create: bool = Field(False, description="Reserved for future auto-transaction creation")
    notes: Optional[str] = None


class BillUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    amount: Optional[int] = Field(None, gt=0)
    frequency: Optional[BillFrequency] = None
    category_id: Optional[int] = None
    account_id: Optional[int] = None
    due_day: Optional[int] = Field(None, ge=1, le=31)
    active: Optional[bool] = None
    notes: Optional[str] = None


class BillResponse(BillCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    active: bool = True
    next_due_date: Optional[date] = Field(
        None, description="Calculated next occurrence from today"
    )
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BillPayRequest(BaseModel):
    amount: Optional[int] = Field(
        None, gt=0, description="Defaults to the bill amount"
    )
    account_id: Optional[int] = Field(
        None, description="When provided, a real expense transaction is created"
    )
    pay_date: Optional[date] = None


class BillPaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bill_id: int
    amount: int
    paid_date: date
    transaction_id: Optional[int] = None


class BillListResponse(BaseModel):
    items: list[BillResponse]
    total: int
