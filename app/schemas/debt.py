"""Debt & payment schemas."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import DebtStatus, DebtType


class DebtCreate(BaseModel):
    type: DebtType = Field(description="PAYABLE (you owe) or RECEIVABLE (owed to you)")
    person_name: str = Field(min_length=1, max_length=100)
    principal_amount: int = Field(gt=0)
    description: Optional[str] = None
    due_date: Optional[date] = None
    installment_amount: Optional[int] = Field(None, ge=0)
    installment_count: Optional[int] = Field(None, ge=0)
    interest_rate: Optional[float] = Field(None, ge=0)
    person_contact: Optional[str] = Field(None, max_length=100)
    related_account_id: Optional[int] = None
    notes: Optional[str] = None


class DebtUpdate(BaseModel):
    """Partial update of editable debt fields."""
    person_name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    due_date: Optional[date] = None
    installment_amount: Optional[int] = Field(None, ge=0)
    installment_count: Optional[int] = Field(None, ge=0)
    interest_rate: Optional[float] = Field(None, ge=0)
    person_contact: Optional[str] = Field(None, max_length=100)
    related_account_id: Optional[int] = None
    notes: Optional[str] = None


class DebtPaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: int
    payment_date: date
    notes: Optional[str] = None
    transaction_id: Optional[int] = None
    created_at: Optional[datetime] = None


class DebtPaymentCreate(BaseModel):
    amount: int = Field(gt=0)
    account_id: Optional[int] = Field(
        None,
        description="When provided, a real income/expense transaction is created",
    )
    payment_date: Optional[date] = None
    notes: Optional[str] = None


class DebtResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: DebtType
    person_name: str
    person_contact: Optional[str] = None
    description: Optional[str] = None
    principal_amount: int
    remaining_amount: int = Field(description="Outstanding amount")
    interest_rate: Optional[float] = None
    start_date: date
    due_date: Optional[date] = None
    installment_amount: Optional[int] = None
    installment_count: Optional[int] = None
    status: DebtStatus
    related_account_id: Optional[int] = None
    notes: Optional[str] = None
    payments: list[DebtPaymentResponse] = []


class DebtListResponse(BaseModel):
    items: list[DebtResponse]
    total: int
