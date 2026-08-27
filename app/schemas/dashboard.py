"""Consolidated dashboard response.

One call gives a mobile/PWA client everything needed for the home screen.
"""
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.budget import BudgetResponse
from app.schemas.bill import BillResponse
from app.schemas.transaction import TransactionResponse


class UpcomingBillItem(BaseModel):
    bill_id: int
    name: str
    amount: int
    next_due_date: Optional[date] = None
    days_until_due: Optional[int] = Field(
        None, description="Negative means overdue"
    )


class DashboardSummary(BaseModel):
    """Net worth = total_assets - total_liabilities.

    total_assets      = liquid accounts (CASH/BANK/E_WALLET/SAVINGS/INVESTMENT)
                        + asset records + investments
    total_liabilities = negative balances on CREDIT_CARD/LOAN/LIABILITY accounts
                        + remaining PAYABLE debts
    """
    net_worth: int
    total_assets: int
    total_liabilities: int
    available_cash: int = Field(description="Liquid money (cash, bank, e-wallet, savings)")
    monthly_income: int
    monthly_expense: int
    monthly_cashflow: int = Field(description="monthly_income - monthly_expense")
    total_debt: int = Field(description="Remaining PAYABLE debts")
    total_receivables: int = Field(description="Remaining RECEIVABLE debts")
    budget_summary: list[BudgetResponse] = []
    upcoming_bills: list[UpcomingBillItem] = []
    recent_transactions: list[TransactionResponse] = []
