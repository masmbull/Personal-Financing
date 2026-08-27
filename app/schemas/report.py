"""Report request/response schemas."""
from datetime import date as dt_date
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class DateRangeParams(BaseModel):
    date_from: Optional[date] = Field(None, description="Inclusive start (ISO)")
    date_to: Optional[date] = Field(None, description="Inclusive end (ISO)")


class CategoryTotal(BaseModel):
    category_id: int
    name: str
    icon: Optional[str] = None
    total: int
    percentage: float = Field(description="Share of the period grand total")


class CashFlowReport(BaseModel):
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    income: int
    expense: int
    net: int = Field(description="income - expense")


class ExpenseBreakdownReport(DateRangeParams):
    total: int
    by_category: list[CategoryTotal] = []


class IncomeExpenseMonth(BaseModel):
    year: int
    month: int
    label: str = Field(examples=["Aug 2026"])
    income: int
    expense: int
    net: int


class IncomeVsExpenseReport(BaseModel):
    months: list[IncomeExpenseMonth] = []


class NetWorthPoint(BaseModel):
    as_of: date
    net_worth: int
    total_assets: int
    total_liabilities: int


class NetWorthReport(BaseModel):
    current: NetWorthPoint
    note: str = (
        "Snapshot of current balances; historical time-series tracking "
        "is planned once periodic snapshots are stored."
    )


class NetWorthHistoryPoint(BaseModel):
    """One stored daily snapshot (see net_worth_snapshots table)."""
    date: dt_date = Field(description="Snapshot day")
    net_worth: int
    total_assets: int
    total_liabilities: int


class NetWorthHistoryReport(BaseModel):
    points: list[NetWorthHistoryPoint] = []
    count: int


class CategoriesReport(BaseModel):
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    type: str = Field(description="EXPENSE or INCOME")
    total: int
    by_category: list[CategoryTotal] = []
