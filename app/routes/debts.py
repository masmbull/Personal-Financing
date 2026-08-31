from datetime import date

from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.models import DebtType, Account
from app.services import debts as debts_service
from app.utils import format_rupiah, today_str
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


@router.get("/debts", response_class=HTMLResponse)
def list_debts(request: Request, db: Session = Depends(get_db),
               user: CurrentUser = Depends(get_current_user)):
    receivables = debts_service.list_debts(db, DebtType.RECEIVABLE, user.id)
    payables = debts_service.list_debts(db, DebtType.PAYABLE, user.id)
    totals = debts_service.totals_for(db, user.id)
    return templates.TemplateResponse(request, "debts/list.html", { "receivables": receivables, "payables": payables,
        "total_receivable": totals["total_receivable"],
        "total_payable": totals["total_payable"],
        "format_rupiah": format_rupiah,
        "DebtType": DebtType, "DebtStatus": debts_service.DebtStatus,
    })


@router.get("/debts/create", response_class=HTMLResponse)
def create_debt_form(request: Request, debt_type: str = "PAYABLE",
                     db: Session = Depends(get_db),
                     user: CurrentUser = Depends(get_current_user)):
    accounts = db.query(Account).filter(
        (Account.user_id == user.id) | (Account.user_id.is_(None))
    ).order_by(Account.name).all()
    return templates.TemplateResponse(request, "debts/create.html", { "debt_type": debt_type, "accounts": accounts,
        "today": today_str(), "DebtType": DebtType,
    })


@router.post("/debts/create")
def create_debt(
    type: str = Form(...), person_name: str = Form(...),
    description: str = Form(""), principal_amount: str = Form(...),
    due_date: str = Form(""), installment_amount: str = Form(""),
    installment_count: str = Form(""), notes: str = Form(""),
    person_contact: str = Form(""), related_account_id: str = Form(""),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    try:
        due = date.fromisoformat(due_date) if due_date else None
        debts_service.create_debt(
            db, user_id=user.id, type=DebtType(type), person_name=person_name,
            description=description, principal_amount=int(principal_amount),
            due_date=due,
            installment_amount=int(installment_amount) if installment_amount else None,
            installment_count=int(installment_count) if installment_count else None,
            notes=notes, person_contact=person_contact,
            related_account_id=int(related_account_id) if related_account_id else None,
        )
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/debts", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/debts/pay/{debt_id}", response_class=HTMLResponse)
def pay_debt_form(debt_id: int, request: Request, db: Session = Depends(get_db),
                  user: CurrentUser = Depends(get_current_user)):
    try:
        debt = debts_service.get_debt(db, debt_id, user.id)
    except debts_service.DebtNotFound:
        raise HTTPException(status_code=404, detail="Debt not found")
    accounts = db.query(Account).filter(
        (Account.user_id == user.id) | (Account.user_id.is_(None))
    ).order_by(Account.name).all()
    return templates.TemplateResponse(request, "debts/pay.html", { "debt": debt, "accounts": accounts,
        "today": today_str(), "format_rupiah": format_rupiah,
    })


@router.post("/debts/pay/{debt_id}")
def pay_debt(
    debt_id: int, amount: str = Form(...), account_id: str = Form(""),
    notes: str = Form(""), date_val: str = Form(""),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    try:
        pay_date = date.fromisoformat(date_val) if date_val else None
        debts_service.pay_debt(
            db, debt_id, user.id, amount=int(amount),
            account_id=int(account_id) if account_id else None,
            payment_date=pay_date, notes=notes,
        )
    except debts_service.DebtNotFound:
        raise HTTPException(status_code=404, detail="Debt not found")
    except debts_service.PaymentError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid input")
    return RedirectResponse(url="/debts", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/debts/delete/{debt_id}")
def delete_debt(debt_id: int, db: Session = Depends(get_db),
                user: CurrentUser = Depends(get_current_user)):
    try:
        debts_service.delete_debt(db, debt_id, user.id)
    except debts_service.DebtNotFound:
        raise HTTPException(status_code=404, detail="Debt not found")
    return RedirectResponse(url="/debts", status_code=status.HTTP_303_SEE_OTHER)