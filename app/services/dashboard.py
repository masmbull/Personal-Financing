"""Dashboard service - one consolidated payload for web/PWA/mobile."""
from datetime import date, timedelta

from sqlalchemy.orm import Session, joinedload

from app.models.models import Transaction
from app.services import budgets as budgets_service
from app.services import bills as bills_service
from app.services.accounts import compute_net_worth
from app.services.finance import expense_between, income_between
from app.services.transactions import list_transactions


def _period_range(period: str, today: date) -> tuple[date, date]:
    """Return (start, end) for a named dashboard period. End is inclusive."""
    if period == "week":
        return today - timedelta(days=6), today
    if period == "prev_month":
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if period == "year":
        return today.replace(month=1, day=1), today
    return today.replace(day=1), today


PERIOD_LABELS = {
    "week": "7 hari terakhir",
    "month": "bulan ini",
    "prev_month": "bulan lalu",
    "year": "tahun ini",
}


def build_dashboard(db: Session, *, user_id: int,
                    bills_days_ahead: int = 7,
                    recent_limit: int = 10,
                    period: str = "month") -> dict:
    today = date.today()
    period_start, period_end = _period_range(period, today)

    nw = compute_net_worth(db, user_id)
    income = income_between(db, period_start, period_end, user_id)
    expense = expense_between(db, period_start, period_end, user_id)

    budget_rows = budgets_service.list_with_spending(
        db, today.year, today.month, user_id
    )

    upcoming = []
    for entry in bills_service.with_next_due(db, user_id, today):
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
        db, user_id=user_id, page=1, page_size=recent_limit
    )

    return {
        "net_worth": nw["net_worth"],
        "total_assets": nw["total_assets"],
        "total_liabilities": nw["total_liabilities"],
        "available_cash": nw["available_cash"],
        "period_start": period_start,
        "period_end": period_end,
        "period": period,
        "period_label": PERIOD_LABELS.get(period, "bulan ini"),
        "income": income,
        "expense": expense,
        "cashflow": income - expense,
        "savings_rate": round((income - expense) * 100 / income) if income > 0 else 0,
        # Backward-compatible aliases used by /api/v1/dashboard contract.
        "monthly_income": income,
        "monthly_expense": expense,
        "monthly_cashflow": income - expense,
        "total_debt": nw["total_debt"],
        "total_receivables": nw["total_receivables"],
        "budget_summary": [r["payload"] for r in budget_rows],
        "upcoming_bills": upcoming,
        "recent_transactions": items[:recent_limit],
    }
