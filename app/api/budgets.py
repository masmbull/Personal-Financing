from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status as http_status
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.schemas.budget import (
    BudgetCreate, BudgetListResponse, BudgetResponse, BudgetUpdate,
)
from app.services import budgets as budgets_service

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _row_out(row_or_payload: dict) -> BudgetResponse:
    return BudgetResponse(**row_or_payload)


@router.get(
    "", response_model=BudgetListResponse,
    summary="List monthly budgets with spending",
    description=(
        "Returns each budget with calculated spent / remaining / percentage "
        "and status SAFE (<80%), WARNING (80-100%) or EXCEEDED (>100%)."
    ),
)
def list_budgets(
    year: int = Query(None, ge=2000, le=2100, description="Defaults to current year"),
    month: int = Query(None, ge=1, le=12, description="Defaults to current month"),
    db: Session = Depends(get_db),
):
    today = date.today()
    year = year or today.year
    month = month or today.month
    rows = [_row_out(r["payload"]) for r in budgets_service.list_with_spending(db, year, month)]
    return BudgetListResponse(items=rows, total=len(rows))


@router.post(
    "", response_model=BudgetResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Create a budget",
    description="Upserts per category+month+year: re-POST with the same keys updates the amount.",
    responses={400: {"description": "Invalid input"}},
)
def create_budget(payload: BudgetCreate, db: Session = Depends(get_db)):
    budget = budgets_service.set_budget(
        db, category_id=payload.category_id, amount=payload.amount,
        month=payload.month, year=payload.year,
    )
    return _row_out(budgets_service.get_with_spending(db, budget.id))


@router.get(
    "/{budget_id}", response_model=BudgetResponse,
    summary="Get one budget with spending", responses={404: {"description": "Not found"}},
)
def get_budget(budget_id: int, db: Session = Depends(get_db)):
    return _row_out(budgets_service.get_with_spending(db, budget_id))


@router.put(
    "/{budget_id}", response_model=BudgetResponse,
    summary="Change budget amount",
    responses={404: {"description": "Not found"}},
)
def update_budget(budget_id: int, payload: BudgetUpdate,
                  db: Session = Depends(get_db)):
    budgets_service.update_budget(db, budget_id, payload.amount)
    return _row_out(budgets_service.get_with_spending(db, budget_id))


@router.delete(
    "/{budget_id}", status_code=http_status.HTTP_204_NO_CONTENT,
    summary="Delete a budget",
    responses={404: {"description": "Not found"}},
)
def delete_budget(budget_id: int, db: Session = Depends(get_db)):
    budgets_service.delete_budget(db, budget_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)