from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, CurrentUser
from app.database.db import get_db
from app.schemas.dashboard import DashboardSummary, UpcomingBillItem
from app.schemas.transaction import TransactionResponse
from app.services.dashboard import build_dashboard

router = APIRouter(tags=["dashboard"])


@router.get(
    "/dashboard",
    response_model=DashboardSummary,
    summary="Consolidated dashboard",
    description=(
        "Single call returning net worth, cash position, this month's "
        "cashflow, debt/receivable totals, budget statuses, upcoming bills "
        "and recent transactions - designed so a mobile client can render "
        "its whole home screen from this one response. "
        "net_worth = total_assets - total_liabilities."
    ),
    responses={200: {"description": "Current snapshot"}},
)
def dashboard(
    bills_days_ahead: int = Query(7, ge=0, le=60),
    recent_limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _user: CurrentUser = Depends(get_current_user),
):
    payload = build_dashboard(
        db, bills_days_ahead=bills_days_ahead, recent_limit=recent_limit
    )
    core = {
        k: v for k, v in payload.items()
        if k not in ("upcoming_bills", "recent_transactions")
    }
    return DashboardSummary(
        **core,
        upcoming_bills=[UpcomingBillItem(**b) for b in payload["upcoming_bills"]],
        recent_transactions=[
            TransactionResponse(**t) for t in payload["recent_transactions"]
        ],
    )