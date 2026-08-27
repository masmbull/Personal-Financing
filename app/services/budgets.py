"""Budget service - monthly per-category budgets with spending status."""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import Budget, Category, Transaction, TransactionType
from app.schemas.budget import status_for_percentage


class BudgetNotFound(Exception):
    pass


def spent_for_category(db: Session, category_id: int,
                       year: int, month: int) -> int:
    """Expenses for one category within the given month. Shared calculation."""
    today = date.today()
    start = date(year, month, 1)
    end = today if (year, month) == (today.year, today.month) else _month_end(year, month)
    return db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.type == TransactionType.EXPENSE,
        Transaction.category_id == category_id,
        Transaction.date >= start,
        Transaction.date <= end,
    ).scalar()


def _month_end(year: int, month: int) -> date:
    import calendar
    return date(year, month, calendar.monthrange(year, month)[1])


def set_budget(db: Session, *, category_id: int, amount: int,
               month: int, year: int) -> Budget:
    """Create or update (upsert) a budget for category+month+year."""
    amount = int(amount)
    if amount <= 0:
        raise ValueError("Amount must be positive")
    existing = db.query(Budget).filter(
        Budget.category_id == int(category_id),
        Budget.month == month, Budget.year == year,
    ).first()
    if existing:
        existing.amount = amount
        db.commit()
        db.refresh(existing)
        return existing
    budget = Budget(category_id=int(category_id), amount=amount,
                    month=month, year=year)
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget


def list_with_spending(db: Session, year: int, month: int) -> list[dict]:
    """Budget rows enriched with spent/remaining/percentage/status."""
    budgets = (
        db.query(Budget)
        .filter(Budget.month == month, Budget.year == year)
        .order_by(Budget.id)
        .all()
    )
    rows = []
    for b in budgets:
        spent = spent_for_category(db, b.category_id, b.year, b.month)
        pct = round(spent * 100 / b.amount, 1) if b.amount > 0 else 0.0
        st = status_for_percentage(pct)
        rows.append({
            "budget": b,
            "spent": spent,
            "remaining": b.amount - spent,
            "percentage": pct,
            "status": st,
            "payload": row_payload(b, spent, pct, st),
        })
    return rows


def get_with_spending(db: Session, budget_id: int) -> dict:
    budget = db.query(Budget).filter(Budget.id == budget_id).first()
    if not budget:
        raise BudgetNotFound(f"Budget {budget_id} not found")
    return row_payload(
        budget, *spent_pct_status(db, budget)
    )


def spent_pct_status(db: Session, b: Budget):
    from app.models.models import Budget as _B  # noqa: F401
    spent = spent_for_category(db, b.category_id, b.year, b.month)
    pct = round(spent * 100 / b.amount, 1) if b.amount > 0 else 0.0
    return spent, pct, status_for_percentage(pct)


def row_payload(budget: Budget, spent: int, pct: float, status: str) -> dict:
    """Shared payload shape for the API and dashboard consumers."""
    cat = budget.category
    return {
        "id": budget.id,
        "category": {
            "id": cat.id, "name": cat.name, "type": cat.type.value,
            "group": cat.group, "icon": cat.icon, "is_default": cat.is_default,
        },
        "month": budget.month, "year": budget.year,
        "budget_amount": budget.amount, "spent": spent,
        "remaining": budget.amount - spent,
        "percentage": pct, "status": status,
    }


def update_budget(db: Session, budget_id: int, amount: int) -> Budget:
    budget = db.query(Budget).filter(Budget.id == budget_id).first()
    if not budget:
        raise BudgetNotFound(f"Budget {budget_id} not found")
    amount = int(amount)
    if amount <= 0:
        raise ValueError("Amount must be positive")
    budget.amount = amount
    db.commit()
    db.refresh(budget)
    return budget


def delete_budget(db: Session, budget_id: int) -> None:
    budget = db.query(Budget).filter(Budget.id == budget_id).first()
    if not budget:
        raise BudgetNotFound(f"Budget {budget_id} not found")
    db.delete(budget)
    db.commit()


def expense_categories(db: Session):
    return (
        db.query(Category)
        .filter(Category.type == TransactionType.EXPENSE)
        .order_by(Category.name)
        .all()
    )
