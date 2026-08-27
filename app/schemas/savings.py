"""Savings goal schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SavingsGoalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    target_amount: int = Field(gt=0)
    icon: Optional[str] = Field(None, max_length=10)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    notes: Optional[str] = None


class SavingsGoalUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    target_amount: Optional[int] = Field(None, gt=0)
    icon: Optional[str] = Field(None, max_length=10)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    notes: Optional[str] = None
    active: Optional[bool] = None


class SavingsGoalResponse(SavingsGoalCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    current_amount: int
    progress_percentage: float = Field(0, description="current / target * 100")
    active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SavingsGoalListResponse(BaseModel):
    items: list[SavingsGoalResponse]
    total: int


class SavingsOperationRequest(BaseModel):
    """Deposit / withdraw request. Money moves to/from the linked account only
    as an internal movement - never counted as income or expense."""
    amount: int = Field(gt=0)
    related_account_id: Optional[int] = Field(
        None, description="Optional account for reference tracking"
    )
    notes: Optional[str] = None
