"""Budget schemas with calculated spending status."""
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.category import CategoryResponse


class BudgetStatus:
    SAFE = "SAFE"          # < 80% used
    WARNING = "WARNING"    # 80% - 100% used
    EXCEEDED = "EXCEEDED"  # > 100% used


def status_for_percentage(pct: float) -> str:
    if pct > 100:
        return BudgetStatus.EXCEEDED
    if pct >= 80:
        return BudgetStatus.WARNING
    return BudgetStatus.SAFE


class BudgetCreate(BaseModel):
    category_id: int
    amount: int = Field(gt=0, description="Monthly budget in rupiah")
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2100)


class BudgetUpdate(BaseModel):
    amount: Optional[int] = Field(None, gt=0)


class BudgetResponse(BaseModel):
    id: int
    category: CategoryResponse
    month: int
    year: int
    budget_amount: int
    spent: int = Field(description="Expenses in that category for the month")
    remaining: int
    percentage: float = Field(description="spent / budget_amount * 100")
    status: str = Field(description="SAFE | WARNING | EXCEEDED")


class BudgetListResponse(BaseModel):
    items: list[BudgetResponse]
    total: int
