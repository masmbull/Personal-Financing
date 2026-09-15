"""Financial Health Score — composite metric (0-100) based on four pillars.

1. Savings rate (30 pts)
2. Debt ratio (25 pts)
3. Emergency fund (25 pts)
4. Budget adherence (20 pts)
"""
import json
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.models import FinancialHealthSnapshot
from app.services.accounts import compute_net_worth
from app.services.finance import expense_between, income_between


def _monthly_avg_expense(db: Session, user_id: int, months: int = 3) -> float:
    today = date.today()
    start = today - timedelta(days=months * 30)
    total = expense_between(db, start, today, user_id)
    return total / months if months else 0


def compute_health_score(db: Session, user_id: int) -> dict:
    nw = compute_net_worth(db, user_id)
    today = date.today()
    period_start = today - timedelta(days=89)
    income = income_between(db, period_start, today, user_id)
    expense = expense_between(db, period_start, today, user_id)
    avg_monthly = _monthly_avg_expense(db, user_id)
    total_assets = nw["total_assets"]
    total_liabilities = nw["total_liabilities"]
    available_cash = nw["available_cash"]
    insights: list[str] = []

    # 1. Savings rate (30 pts)
    savings_rate = max(0, (income - expense) / income * 100) if income > 0 else 0.0
    if savings_rate >= 30:
        s_sav = 30
    elif savings_rate >= 20:
        s_sav = 24; insights.append("Tingkat menabung 20-30%, naikkan sedikit!")
    elif savings_rate >= 10:
        s_sav = 15; insights.append("Tingkat menabung 10-20%, usahakan minimal 20%.")
    else:
        s_sav = max(0, int(savings_rate * 15 / 10))
        if expense > 0:
            insights.append("Tingkat menabung rendah. Kurangi pengeluaran bulanan.")

    # 2. Debt ratio (25 pts)
    debt_ratio = (total_liabilities / total_assets * 100) if total_assets > 0 else 0.0
    if debt_ratio <= 20:
        s_debt = 25
    elif debt_ratio <= 40:
        s_debt = 20; insights.append("Rasio utang 20-40%, masih aman.")
    elif debt_ratio <= 60:
        s_debt = 12; insights.append("Rasio utang tinggi (>40%). Prioritaskan lunasi utang.")
    else:
        s_debt = 5; insights.append("Rasio utang sangat tinggi (>60%)!")

    # 3. Emergency fund (25 pts)
    emerg = available_cash / avg_monthly if avg_monthly > 0 else 6.0
    if emerg >= 6:
        s_emerg = 25
    elif emerg >= 3:
        s_emerg = 18; insights.append(f"Dana darurat {emerg:.1f} bln, target 6 bln.")
    elif emerg >= 1:
        s_emerg = 10; insights.append(f"Dana darurat {emerg:.1f} bln. Min 3 bln.")
    else:
        s_emerg = max(0, int(emerg * 10)); insights.append("Dana darurat hampir nol!")

    # 4. Budget adherence (20 pts)
    from app.services.budgets import list_with_spending
    budgets = list_with_spending(db, today.year, today.month, user_id)
    if budgets:
        avg_pct = sum(b["percentage"] for b in budgets) / len(budgets)
        over = sum(1 for b in budgets if b["status"] == "EXCEEDED")
        if over == 0 and avg_pct <= 90:
            s_bud = 20
        elif over <= 1:
            s_bud = 15; insights.append(f"{over} kategori melebihi budget.")
        else:
            s_bud = 8; insights.append(f"{over} kategori melebihi budget!")
    else:
        avg_pct = 0.0; s_bud = 10
        insights.append("Belum ada budget. Buat budget untuk kontrol lebih baik.")

    total = max(0, min(100, s_sav + s_debt + s_emerg + s_bud))
    if total >= 80:
        grade = "A"
        if not insights:
            insights.append("Keuanganmu sangat sehat! Pertahankan.")
    elif total >= 60:
        grade = "B"
    elif total >= 40:
        grade = "C"
    else:
        grade = "D"

    return {
        "score": total, "grade": grade,
        "savings_rate": round(savings_rate, 1),
        "debt_ratio": round(debt_ratio, 1),
        "emergency_months": round(emerg, 1),
        "budget_adherence": round(avg_pct, 1),
        "sub_scores": {"savings": s_sav, "debt": s_debt, "emergency": s_emerg, "budget": s_bud},
        "insights": insights,
    }


def snapshot_health(db: Session, user_id: int) -> FinancialHealthSnapshot:
    """Compute and persist a health snapshot for today."""
    result = compute_health_score(db, user_id)
    today = date.today()
    existing = db.query(FinancialHealthSnapshot).filter(
        FinancialHealthSnapshot.user_id == user_id,
        FinancialHealthSnapshot.snapshot_date == today,
    ).first()
    data = {
        "score": result["score"], "savings_rate": result["savings_rate"],
        "debt_ratio": result["debt_ratio"],
        "emergency_months": result["emergency_months"],
        "budget_adherence": result["budget_adherence"],
        "insights_json": json.dumps(result["insights"], ensure_ascii=False),
    }
    if existing:
        for k, v in data.items():
            setattr(existing, k, v)
        db.commit(); db.refresh(existing)
        return existing
    snap = FinancialHealthSnapshot(user_id=user_id, snapshot_date=today, **data)
    db.add(snap); db.commit(); db.refresh(snap)
    return snap
