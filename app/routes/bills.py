from datetime import date

from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.models.models import BillFrequency, Category, Account, TransactionType
from app.services import bills as bills_service
from app.utils import format_rupiah, today_str
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


@router.get("/bills", response_class=HTMLResponse)
def list_bills(request: Request, db: Session = Depends(get_db)):
    upcoming = bills_service.with_next_due(db)
    return templates.TemplateResponse("bills/list.html", {
        "request": request, "upcoming": upcoming,
        "format_rupiah": format_rupiah, "BillFrequency": BillFrequency,
        "today": date.today(),
    })


@router.get("/bills/create", response_class=HTMLResponse)
def create_bill_form(request: Request, db: Session = Depends(get_db)):
    categories = (
        db.query(Category)
        .filter(Category.type == TransactionType.EXPENSE)
        .order_by(Category.name).all()
    )
    accounts = db.query(Account).order_by(Account.name).all()
    return templates.TemplateResponse("bills/create.html", {
        "request": request, "categories": categories, "accounts": accounts,
        "BillFrequency": BillFrequency,
    })


@router.post("/bills/create")
def create_bill(
    name: str = Form(...), amount: str = Form(...),
    frequency: str = Form("MONTHLY"), due_day: str = Form(""),
    category_id: str = Form(""), account_id: str = Form(""),
    notes: str = Form(""), db: Session = Depends(get_db),
):
    try:
        bills_service.create_bill(
            db, name=name, amount=int(amount), frequency=BillFrequency(frequency),
            due_day=int(due_day) if due_day else None,
            category_id=int(category_id) if category_id else None,
            account_id=int(account_id) if account_id else None,
            notes=notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/bills", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/bills/pay/{bill_id}")
def mark_bill_paid(
    bill_id: int, amount: str = Form(""), account_id: str = Form(""),
    date_val: str = Form(""), db: Session = Depends(get_db),
):
    try:
        bills_service.pay_bill(
            db, bill_id,
            amount=int(amount) if amount else None,
            account_id=int(account_id) if account_id else None,
            pay_date=date.fromisoformat(date_val) if date_val else None,
        )
    except bills_service.BillNotFound:
        raise HTTPException(status_code=404, detail="Bill not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/bills", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/bills/delete/{bill_id}")
def delete_bill(bill_id: int, db: Session = Depends(get_db)):
    try:
        bills_service.delete_bill(db, bill_id)
    except bills_service.BillNotFound:
        raise HTTPException(status_code=404, detail="Bill not found")
    return RedirectResponse(url="/bills", status_code=status.HTTP_303_SEE_OTHER)