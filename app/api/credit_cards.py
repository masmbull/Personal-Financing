"""Credit card statement API."""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, CurrentUser
from app.database.db import get_db
from app.services import accounts as acc_svc
from app.services.credit_card import calculate_statement, statement_period_for

router = APIRouter(prefix="/credit-cards", tags=["credit-cards"])


@router.get("/{account_id}/statement")
def get_statement(account_id: int,
                  ref: date | None = Query(None, description="Reference date (default today)"),
                  db: Session = Depends(get_db),
                  user: CurrentUser = Depends(get_current_user)):
    from app.api.errors import ApiError
    acc = acc_svc.get_own_account(db, account_id, user.id)
    if not acc:
        raise ApiError(404, "NOT_FOUND", "Credit card not found")
    try:
        period = calculate_statement(db, acc, ref or date.today(), user.id)
    except ValueError as e:
        raise ApiError(400, "INVALID_REQUEST", str(e))
    return {
        "account_id": account_id,
        "period_start": period.period_start,
        "closing_date": period.closing_date,
        "due_date": period.due_date,
        "statement_balance": period.statement_balance,
        "minimum_payment": period.minimum_payment,
        "payment_status": period.payment_status,
        "available_credit": acc_svc.get_available_credit(acc),
    }
