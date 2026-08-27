"""Investment schemas."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class InvestmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    investment_type: str = Field(max_length=50, examples=["Saham", "Emas", "Crypto"])
    amount_invested: int = Field(gt=0)
    current_value: int = Field(ge=0)
    purchase_date: Optional[date] = None
    icon: Optional[str] = Field(None, max_length=10)
    notes: Optional[str] = None


class InvestmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    investment_type: Optional[str] = Field(None, max_length=50)
    amount_invested: Optional[int] = Field(None, gt=0)
    current_value: Optional[int] = Field(None, ge=0)
    purchase_date: Optional[date] = None
    icon: Optional[str] = Field(None, max_length=10)
    notes: Optional[str] = None


class InvestmentResponse(InvestmentCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    gain_loss: int = Field(description="current_value - amount_invested")
    return_percentage: float = Field(
        description="gain_loss / amount_invested * 100, rounded to 2 decimals"
    )
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class InvestmentListResponse(BaseModel):
    items: list[InvestmentResponse]
    total: int
    total_invested: int
    total_current_value: int
    total_gain_loss: int
