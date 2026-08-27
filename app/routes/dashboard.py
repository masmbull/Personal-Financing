from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.models.models import AccountType, TransactionType
from app.services import accounts as accounts_service
from app.utils import format_rupiah
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    """Consolidated dashboard page - one call into the SAME service that
    powers GET /api/v1/dashboard, so numbers never diverge between UI/API."""
    from types import SimpleNamespace as NS

    from app.services import reports as reports_service
    from app.services import savings as savings_service
    from app.services.dashboard import build_dashboard
    from datetime import date as _date

    payload = build_dashboard(db)

    recent = []
    for t in payload["recent_transactions"]:
        row = dict(t)
        row["type"] = NS(value=t["type"])
        if t.get("transfer_to_account_id"):
            row["category_display"] = "Transfer"
        else:
            row["category_display"] = t.get("category_name") or t["type"].title()
        recent.append(NS(**row))

    budgets = []
    for b in payload["budget_summary"]:
        bb = dict(b)
        bb["category"] = NS(**bb["category"])
        budgets.append(NS(**bb))

    upcoming = [NS(**u) for u in payload["upcoming_bills"]]

    data = NS(
        available_cash=payload["available_cash"],
        total_assets=payload["total_assets"],
        total_liabilities=payload["total_liabilities"],
        net_worth=payload["net_worth"],
        monthly_income=payload["monthly_income"],
        monthly_expense=payload["monthly_expense"],
        monthly_cashflow=payload["monthly_cashflow"],
        total_debt=payload["total_debt"],
        total_receivables=payload["total_receivables"],
        budget_summary=budgets,
        upcoming_bills=upcoming,
        recent_transactions=recent,
    )

    today = _date.today()
    breakdown = reports_service.category_breakdown(
        db, TransactionType.EXPENSE, today.replace(day=1), today
    )
    goals = [
        {"goal": g,
         "percentage": round(g.current_amount * 100 / g.target_amount, 1)
         if g.target_amount > 0 else 0}
        for g in savings_service.list_goals(db)
    ]

    return templates.TemplateResponse(request, "dashboard.html", {
        "data": data,
        "expense_breakdown": breakdown["by_category"][:5],
        "expense_total": breakdown["total"],
        "savings_goals": goals[:3],
        "format_rupiah": format_rupiah,
    })


@router.get("/accounts", response_class=HTMLResponse)
def list_accounts(request: Request, db: Session = Depends(get_db)):
    groups = accounts_service.list_accounts_grouped(db)
    return templates.TemplateResponse(request, "accounts/list.html", {
        "groups": groups,
        "account_types": AccountType,
        "format_rupiah": format_rupiah,
    })


@router.get("/accounts/create", response_class=HTMLResponse)
def create_account_form(request: Request):
    return templates.TemplateResponse(request, "accounts/create.html", {
        "account_types": AccountType,
    })


@router.post("/accounts/create")
def create_account(
    name: str = Form(...),
    type: str = Form(...),
    initial_balance: str = Form("0"),
    icon: str = Form(""),
    db: Session = Depends(get_db)
):
    try:
        init_bal = int(initial_balance) if initial_balance else 0
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid initial balance")
    try:
        accounts_service.create_account(
            db, name=name, type_=AccountType(type), initial_balance=init_bal,
            icon=icon or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/accounts", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/accounts/edit/{account_id}", response_class=HTMLResponse)
def edit_account_form(account_id: int, request: Request, db: Session = Depends(get_db)):
    account = accounts_service.get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return templates.TemplateResponse(request, "accounts/edit.html", { "account": account, "account_types": AccountType,
    })


@router.post("/accounts/edit/{account_id}")
def edit_account(account_id: int, name: str = Form(...), type: str = Form(...),
                 initial_balance: str = Form("0"), icon: str = Form(""),
                 db: Session = Depends(get_db)):
    try:
        init_bal = int(initial_balance) if initial_balance else 0
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid initial balance")
    try:
        accounts_service.update_account(
            db, account_id, name=name.strip(), type=AccountType(type),
            initial_balance=init_bal, icon=icon or None,
        )
    except accounts_service.AccountNotFound:
        raise HTTPException(status_code=404, detail="Account not found")
    return RedirectResponse(url="/accounts", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/accounts/delete/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    try:
        accounts_service.delete_account(db, account_id)
    except accounts_service.AccountNotFound:
        raise HTTPException(status_code=404, detail="Account not found")
    except ValueError:
        raise HTTPException(status_code=400, detail="Account masih dipakai transaksi")
    return RedirectResponse(url="/accounts", status_code=status.HTTP_303_SEE_OTHER)
