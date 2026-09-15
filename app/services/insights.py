"""Spending Insights — trend analysis, anomalies, and recommendations."""
import calendar
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import Category, Transaction, TransactionType
from app.services.finance import expense_between, income_between


def _month_range(d: date):
    first = d.replace(day=1)
    last = d.replace(day=calendar.monthrange(d.year, d.month)[1])
    return first, last


def _rp(amount: int) -> str:
    if amount < 0:
        return f"-Rp {abs(amount):,.0f}".replace(",", ".")
    return f"Rp {amount:,.0f}".replace(",", ".")


def spending_by_category(db, user_id, start, end):
    rows = (
        db.query(Transaction.category_id,
                 func.coalesce(func.sum(Transaction.amount), 0))
        .filter(Transaction.type == TransactionType.EXPENSE,
                Transaction.user_id == user_id,
                Transaction.date >= start, Transaction.date <= end)
        .group_by(Transaction.category_id).all()
    )
    return {cat_id: total for cat_id, total in rows}


def generate_insights(db: Session, user_id: int) -> dict:
    today = date.today()
    curr_start, curr_end = _month_range(today)
    prev_end = curr_start - timedelta(days=1)
    prev_start, _ = _month_range(prev_end)
    curr_income = income_between(db, curr_start, curr_end, user_id)
    curr_expense = expense_between(db, curr_start, curr_end, user_id)
    prev_income = income_between(db, prev_start, prev_end, user_id)
    prev_expense = expense_between(db, prev_start, prev_end, user_id)
    curr_cats = spending_by_category(db, user_id, curr_start, curr_end)
    prev_cats = spending_by_category(db, user_id, prev_start, prev_end)
    cat_ids = set(curr_cats.keys()) | set(prev_cats.keys())
    cat_names = {}
    if cat_ids:
        cats = db.query(Category).filter(Category.id.in_(cat_ids)).all()
        cat_names = {c.id: (c.name, c.icon) for c in cats}
    insights: list[dict] = []
    # 1. Overall spending change
    if prev_expense > 0:
        pct = (curr_expense - prev_expense) / prev_expense * 100
        if pct > 15:
            insights.append({"type": "warning", "icon": "⚠️", "title": "Pengeluaran naik",
                "detail": f"Naik {pct:.0f}% dari bulan lalu ({_rp(curr_expense)} vs {_rp(prev_expense)})."})
        elif pct < -15:
            insights.append({"type": "positive", "icon": "🎉", "title": "Pengeluaran turun",
                "detail": f"Turun {abs(pct):.0f}% dari bulan lalu. Bagus!"})
    # 2. Top category increases
    for cid, amt in sorted(curr_cats.items(), key=lambda x: -x[1])[:3]:
        prev_amt = prev_cats.get(cid, 0)
        name, icon = cat_names.get(cid, ("Lain", "📋"))
        if prev_amt > 0:
            diff_pct = (amt - prev_amt) / prev_amt * 100
            if diff_pct > 30 and (amt - prev_amt) > 50_000:
                insights.append({"type": "warning", "icon": icon,
                    "title": f"{name} naik {diff_pct:.0f}%",
                    "detail": f"Naik {_rp(amt - prev_amt)} dari bulan lalu."})
    # 3. Top spending category
    if curr_cats:
        top_id = max(curr_cats, key=curr_cats.get)
        top_name, top_icon = cat_names.get(top_id, ("Lain", "📋"))
        top_pct = curr_cats[top_id] / curr_expense * 100 if curr_expense else 0
        insights.append({"type": "info", "icon": top_icon,
            "title": f"Pengeluaran terbesar: {top_name}",
            "detail": f"{_rp(curr_cats[top_id])} ({top_pct:.0f}% dari total)."})
    # 4. Daily burn projection
    days_elapsed = (today - curr_start).days + 1
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    if days_elapsed > 0 and days_in_month > 0 and curr_income > 0:
        projected = (curr_expense / days_elapsed) * days_in_month
        if projected > curr_income:
            overshoot = projected - curr_income
            insights.append({"type": "danger", "icon": "🚨",
                "title": "Proyeksi melebihi pemasukan",
                "detail": f"Di ritme ini, kekurangan ~{_rp(int(overshoot))} di akhir bulan."})
    if not insights:
        insights.append({"type": "positive", "icon": "✅", "title": "Semua aman",
            "detail": "Tidak ada anomali signifikan bulan ini."})
    curr_rate = (curr_income - curr_expense) / curr_income * 100 if curr_income > 0 else 0
    return {"month": today.strftime("%B %Y"), "curr_expense": curr_expense,
            "prev_expense": prev_expense, "curr_income": curr_income,
            "prev_income": prev_income, "savings_rate": round(curr_rate, 1),
            "insights": insights}
