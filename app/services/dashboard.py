"""Dashboard service - one consolidated payload for web/PWA/mobile."""
from datetime import date, timedelta

from sqlalchemy.orm import Session, joinedload

from app.models.models import Transaction
from app.services import budgets as budgets_service
from app.services import bills as bills_service
from app.services.accounts import compute_net_worth
from app.services.finance import expense_between, income_between
from app.services.transactions import list_transactions


def build_dashboard(db: Session, *, bills_days_ahead: int = 7,
                    recent_limit: int = 10) -> dict:
    today = date.today()
    month_start = today.replace(day=1)

    nw = compute_net_worth(db)
    monthly_income = income_between(db, month_start, today)
    monthly_expense = expense_between(db, month_start, today)

    budget_rows = budgets_service.list_with_spending(db, today.year, today.month)

    upcoming = []
    for entry in bills_service.with_next_due(db, today):
        nd = entry["next_due"]
        if not nd:
            continue
        delta = (nd - today).days
        if delta <= bills_days_ahead:
            b = entry["bill"]
            upcoming.append({
                "bill_id": b.id, "name": b.name, "amount": b.amount,
                "next_due_date": nd, "days_until_due": delta,
            })
    upcoming.sort(key=lambda x: x["next_due_date"] or date.max)

    items, _total, _p, _ps = list_transactions(
        db, page=1, page_size=recent_limit
    )

    return {
        "net_worth": nw["net_worth"],
        "total_assets": nw["total_assets"],
        "total_liabilities": nw["total_liabilities"],
        "available_cash": nw["available_cash"],
        "monthly_income": monthly_income,
        "monthly_expense": monthly_expense,
        "monthly_cashflow": monthly_income - monthly_expense,
        "total_debt": nw["total_debt"],
        "total_receivables": nw["total_receivables"],
        "budget_summary": [r["payload"] for r in budget_rows],
        "upcoming_bills": upcoming,
        "recent_transactions": items[:recent_limit],
    }
