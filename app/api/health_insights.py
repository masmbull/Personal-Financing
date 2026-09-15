"""Health Score + Spending Insights API."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.database.db import get_db
from app.models.models import FinancialHealthSnapshot
from app.services.health_score import compute_health_score, snapshot_health
from app.services.insights import generate_insights

router = APIRouter(tags=["health-insights"])


@router.get("/health-score", summary="Financial health score")
def health_score(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return compute_health_score(db, user.id)


@router.get("/health-score/history", summary="Health score snapshots")
def health_score_history(
    days: int = Query(90, ge=7, le=365),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from_date = date.today() - timedelta(days=days)
    rows = (
        db.query(FinancialHealthSnapshot)
        .filter(
            FinancialHealthSnapshot.user_id == user.id,
            FinancialHealthSnapshot.snapshot_date >= from_date,
        )
        .order_by(FinancialHealthSnapshot.snapshot_date)
        .all()
    )
    return [
        {
            "date": r.snapshot_date.isoformat(),
            "score": r.score,
            "savings_rate": r.savings_rate,
            "debt_ratio": r.debt_ratio,
            "emergency_months": r.emergency_months,
            "budget_adherence": r.budget_adherence,
        }
        for r in rows
    ]


@router.post("/health-score/snapshot", summary="Save today's health snapshot")
def save_health_snapshot(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    snap = snapshot_health(db, user.id)
    return {"snapshot_date": snap.snapshot_date.isoformat(), "score": snap.score}


@router.get("/insights", summary="Spending insights and anomalies")
def insights(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return generate_insights(db, user.id)
