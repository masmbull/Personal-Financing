from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, status as http_status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, CurrentUser
from app.database.db import get_db
from app.models.models import TransactionType
from app.schemas.report import (
    CashFlowReport, CategoriesReport, CategoryTotal, ExpenseBreakdownReport,
    IncomeExpenseMonth, IncomeVsExpenseReport, NetWorthHistoryPoint,
    NetWorthHistoryReport, NetWorthReport, NetWorthPoint,
)
from app.services import reports as reports_service

router = APIRouter(prefix="/reports", tags=["reports"])

DateFrom = Query(None, description="Inclusive start date (ISO), defaults to first day of current month")
DateTo = Query(None, description="Inclusive end date (ISO), defaults to today")


@router.get(
    "/cash-flow", response_model=CashFlowReport,
    summary="Cash flow for a period",
    description="Income minus expense over an inclusive date range.",
)
def cash_flow(date_from: Optional[date] = DateFrom,
              date_to: Optional[date] = DateTo,
              db: Session = Depends(get_db),
              user: CurrentUser = Depends(get_current_user)):
    return CashFlowReport(**reports_service.cash_flow(db, user.id, date_from, date_to))


@router.get(
    "/expenses", response_model=ExpenseBreakdownReport,
    summary="Expense breakdown by category",
)
def expenses(date_from: Optional[date] = DateFrom,
             date_to: Optional[date] = DateTo,
             db: Session = Depends(get_db),
             user: CurrentUser = Depends(get_current_user)):
    data = reports_service.category_breakdown(
        db, TransactionType.EXPENSE, date_from, date_to,
        user_id=user.id,
    )
    return ExpenseBreakdownReport(
        date_from=data["date_from"], date_to=data["date_to"],
        total=data["total"],
        by_category=[CategoryTotal(**c) for c in data["by_category"]],
    )


@router.get(
    "/income-vs-expense", response_model=IncomeVsExpenseReport,
    summary="Monthly income vs expense series",
    description="Defaults to the trailing 6 months including the current one; "
                "pass date_from/date_to for a custom monthly window.",
)
def income_vs_expense(
    months: int = Query(6, ge=1, le=24),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    series = reports_service.monthly_series(db, months, date_from, date_to, user.id)
    return IncomeVsExpenseReport(months=[IncomeExpenseMonth(**m) for m in series])


@router.get(
    "/net-worth", response_model=NetWorthReport,
    summary="Current net worth",
    description=(
        "net_worth = total_assets - total_liabilities where assets are "
        "asset-side account balances + physical assets + investments and "
        "liabilities are negative liability-account balances + unpaid debts."
    ),
)
def net_worth(db: Session = Depends(get_db),
              user: CurrentUser = Depends(get_current_user)):
    return NetWorthReport(current=NetWorthPoint(**reports_service.net_worth_snapshot(db, user.id)))


@router.get(
    "/net-worth/history", response_model=NetWorthHistoryReport,
    summary="Net worth over time",
    description="Stored daily snapshots. A point for today is recorded "
                "automatically at app startup; use the snapshot endpoint to "
                "refresh mid-day.",
)
def net_worth_history(date_from: Optional[date] = Query(None),
                      date_to: Optional[date] = Query(None),
                      db: Session = Depends(get_db),
                      user: CurrentUser = Depends(get_current_user)):
    points = reports_service.net_worth_history(db, user.id, date_from, date_to)
    return NetWorthHistoryReport(
        points=[NetWorthHistoryPoint(**p) for p in points], count=len(points),
    )


@router.post(
    "/net-worth/snapshot", response_model=NetWorthHistoryPoint,
    status_code=http_status.HTTP_201_CREATED,
    summary="Record/refresh today's net-worth snapshot",
    description="Upserts a single row per day with the current values.",
)
def record_net_worth_snapshot(db: Session = Depends(get_db),
                              user: CurrentUser = Depends(get_current_user)):
    from app.schemas.report import NetWorthHistoryPoint
    row = reports_service.record_daily_snapshot(db, user.id)
    return NetWorthHistoryPoint(
        date=row.snapshot_date,
        net_worth=row.net_worth,
        total_assets=row.total_assets,
        total_liabilities=row.total_liabilities,
    )


@router.get(
    "/categories", response_model=CategoriesReport,
    summary="Category totals for a period",
    description="Totals per category for EXPENSE or INCOME within the range.",
)
def categories_report(
    type: TransactionType = Query(TransactionType.EXPENSE, description="EXPENSE | INCOME"),
    date_from: Optional[date] = DateFrom,
    date_to: Optional[date] = DateTo,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    data = reports_service.category_breakdown(db, type, date_from, date_to,
                                              user_id=user.id)
    return CategoriesReport(
        date_from=data["date_from"], date_to=data["date_to"],
        type=data["type"], total=data["total"],
        by_category=[CategoryTotal(**c) for c in data["by_category"]],
    )