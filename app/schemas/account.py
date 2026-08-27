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


class AccountResponse(AccountBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    initial_balance: int
    current_balance: int = Field(description="Calculated live balance")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AccountListResponse(BaseModel):
    items: list[AccountResponse]
    total: int
