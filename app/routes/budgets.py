from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.services import budgets as budgets_service
from app.utils import format_rupiah
from datetime import date
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


@router.get("/budgets", response_class=HTMLResponse)
def list_budgets(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    budget_data = budgets_service.list_with_spending(db, today.year, today.month)
    expense_cats = budgets_service.expense_categories(db)
    return templates.TemplateResponse(request, "budgets/list.html", { "budget_data": budget_data,
        "format_rupiah": format_rupiah, "expense_cats": expense_cats,
        "month": today.month, "year": today.year,
    })


@router.post("/budgets/create")
def create_budget(
    category_id: str = Form(...), amount: str = Form(...),
    month: str = Form(...), year: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        budgets_service.set_budget(
            db, category_id=int(category_id), amount=int(amount),
            month=int(month), year=int(year),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/budgets", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/budgets/delete/{budget_id}")
def delete_budget(budget_id: int, db: Session = Depends(get_db)):
    try:
        budgets_service.delete_budget(db, budget_id)
    except budgets_service.BudgetNotFound:
        raise HTTPException(status_code=404, detail="Budget not found")
    return RedirectResponse(url="/budgets", status_code=status.HTTP_303_SEE_OTHER)