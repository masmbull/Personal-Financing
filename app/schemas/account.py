"""Account request/response schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import AccountType


class AccountBase(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="Account name")
    type: AccountType = Field(description="One of the supported AccountType values")
    institution: Optional[str] = Field(None, max_length=100)
    account_number: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$", examples=["#3498DB"])
    icon: Optional[str] = Field(None, max_length=10, examples=["🏦"])
    # Credit-card specific
    credit_limit: Optional[int] = Field(None, ge=0, description="Credit limit in rupiah")
    statement_date: Optional[int] = Field(None, ge=1, le=28, description="Statement close day of month")
    payment_due_day: Optional[int] = Field(None, ge=1, le=28, description="Payment due day of month")
    interest_rate_pct: Optional[float] = Field(None, ge=0, description="Annual interest rate %")
    annual_fee: Optional[int] = Field(None, ge=0, description="Annual fee in rupiah")
    card_network: Optional[str] = Field(None, max_length=20)
    institution_id: Optional[int] = Field(None, description="FK to master financial_institution")


class AccountCreate(AccountBase):
    initial_balance: int = Field(0, description="Starting balance in rupiah")


class AccountUpdate(BaseModel):
    """Partial update - only provided fields are changed."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    type: Optional[AccountType] = None
    institution: Optional[str] = Field(None, max_length=100)
    account_number: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: Optional[str] = Field(None, max_length=10)
    initial_balance: Optional[int] = None
    credit_limit: Optional[int] = Field(None, ge=0)
    statement_date: Optional[int] = Field(None, ge=1, le=28)
    payment_due_day: Optional[int] = Field(None, ge=1, le=28)
    interest_rate_pct: Optional[float] = Field(None, ge=0)
    annual_fee: Optional[int] = Field(None, ge=0)
    card_network: Optional[str] = Field(None, max_length=20)
    institution_id: Optional[int] = None


class AccountResponse(AccountBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    initial_balance: int
    current_balance: int = Field(description="Calculated live balance")
    available_credit: Optional[int] = Field(
        None, description="Credit limit minus outstanding (credit cards only)")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AccountListResponse(BaseModel):
    items: list[AccountResponse]
    total: int
