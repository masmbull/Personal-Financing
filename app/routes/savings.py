from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.services import savings as savings_service
from app.utils import format_rupiah
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


@router.get("/savings", response_class=HTMLResponse)
def list_savings(request: Request, db: Session = Depends(get_db)):
    goals = savings_service.list_goals(db)
    total_target = sum(g.target_amount for g in goals)
    total_saved = sum(g.current_amount for g in goals)
    return templates.TemplateResponse(request, "savings/list.html", { "goals": goals,
        "format_rupiah": format_rupiah,
        "total_target": total_target, "total_saved": total_saved,
    })


@router.get("/savings/create", response_class=HTMLResponse)
def create_savings_form(request: Request):
    return templates.TemplateResponse("savings/create.html", {"request": request})


@router.post("/savings/create")
def create_savings(
    name: str = Form(...), target_amount: str = Form(...),
    icon: str = Form(""), notes: str = Form(""),
    db: Session = Depends(get_db),
):
    try:
        savings_service.create_goal(
            db, name=name, target_amount=target_amount,
            icon=icon, notes=notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/savings", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/savings/deposit/{goal_id}")
def deposit_savings(
    goal_id: int, amount: str = Form(...), notes: str = Form(""),
    related_account_id: str = Form(""), db: Session = Depends(get_db),
):
    try:
        savings_service.deposit(
            db, goal_id, amount=int(amount),
            related_account_id=int(related_account_id) if related_account_id else None,
            notes=notes,
        )
    except savings_service.GoalNotFound:
        raise HTTPException(status_code=404, detail="Goal not found")
    except savings_service.SavingsOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/savings", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/savings/withdraw/{goal_id}")
def withdraw_savings(
    goal_id: int, amount: str = Form(...), notes: str = Form(""),
    related_account_id: str = Form(""), db: Session = Depends(get_db),
):
    try:
        savings_service.withdraw(
            db, goal_id, amount=int(amount),
            related_account_id=int(related_account_id) if related_account_id else None,
            notes=notes,
        )
    except savings_service.GoalNotFound:
        raise HTTPException(status_code=404, detail="Goal not found")
    except savings_service.SavingsOperationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/savings", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/savings/delete/{goal_id}")
def delete_savings(goal_id: int, db: Session = Depends(get_db)):
    try:
        savings_service.delete_goal(db, goal_id)
    except savings_service.GoalNotFound:
        raise HTTPException(status_code=404, detail="Goal not found")
    return RedirectResponse(url="/savings", status_code=status.HTTP_303_SEE_OTHER)