from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database.db import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.models import Account, AccountType, TransactionType
from app.services import accounts as accounts_service
from app.utils import format_rupiah
from app.validation import parse_idr_input
from app.account_icons import ACCOUNT_ICON_POOLS, bank_brand
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


def _user_has_accounts(db: Session, user_id: int) -> bool:
    """Gate: user must own at least one account before seeing the dashboard."""
    return db.query(Account.id).filter(Account.user_id == user_id).first() is not None


def _account_balance_total(db: Session, user_id: int) -> int:
    """Sum of current_balance across own accounts (sidebar indicator)."""
    return db.query(func.coalesce(func.sum(Account.current_balance), 0)).filter(
        Account.user_id == user_id
    ).scalar() or 0


def _parse_balance(raw: str) -> int:
    """Balance input parser: blank/0 -> 0, else strict IDR (20.000 -> 20000)."""
    s = (raw or "").strip()
    if not s or s == "0":
        return 0
    try:
        return parse_idr_input(s, "Saldo")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db),
              period: str = "month",
              user: CurrentUser = Depends(get_current_user)):
    """Consolidated dashboard page - one call into the SAME service that
    powers GET /api/v1/dashboard, so numbers never diverge between UI/API."""
    from types import SimpleNamespace as NS

    from app.services import reports as reports_service
    from app.services import savings as savings_service
    from app.services.dashboard import build_dashboard

    if not _user_has_accounts(db, user.id):
        return RedirectResponse(url="/setup", status_code=303)

    if period not in ("week", "month", "prev_month", "year"):
        period = "month"

    payload = build_dashboard(db, user_id=user.id, period=period)

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
        income=payload["income"],
        expense=payload["expense"],
        cashflow=payload["cashflow"],
        savings_rate=payload["savings_rate"],
        period=payload["period"],
        period_label=payload["period_label"],
        total_debt=payload["total_debt"],
        total_receivables=payload["total_receivables"],
        budget_summary=budgets,
        upcoming_bills=upcoming,
        recent_transactions=recent,
    )

    # Expense breakdown follows the selected period.
    breakdown = reports_service.category_breakdown(
        db, TransactionType.EXPENSE, payload["period_start"], payload["period_end"],
        user_id=user.id,
    )
    goals = [
        {"goal": g,
         "percentage": round(g.current_amount * 100 / g.target_amount, 1)
         if g.target_amount > 0 else 0}
        for g in savings_service.list_goals(db, user.id)
    ]

    return templates.TemplateResponse(request, "dashboard.html", {
        "data": data,
        "expense_breakdown": breakdown["by_category"][:5],
        "expense_total": breakdown["total"],
        "savings_goals": goals[:3],
        "period_options": [
            ("week", "7 Hari"),
            ("month", "Bulan Ini"),
            ("prev_month", "Bulan Lalu"),
            ("year", "Tahun Ini"),
        ],
        "format_rupiah": format_rupiah,
    })


@router.get("/accounts", response_class=HTMLResponse)
def list_accounts(request: Request, db: Session = Depends(get_db),
                  user: CurrentUser = Depends(get_current_user)):
    groups = accounts_service.list_accounts_grouped(db, user.id)
    total = sum(g["total"] for g in groups)
    return templates.TemplateResponse(request, "accounts/list.html", {
        "groups": groups,
        "account_types": AccountType,
        "format_rupiah": format_rupiah,
        "bank_brand": bank_brand,
        "sidebar_accounts_total": total,
    })


@router.get("/accounts/create", response_class=HTMLResponse)
def create_account_form(request: Request,
                        db: Session = Depends(get_db),
                        user: CurrentUser = Depends(get_current_user)):
    return templates.TemplateResponse(request, "accounts/create.html", {
        "account_types": AccountType,
        "icon_pools": ACCOUNT_ICON_POOLS,
        "format_rupiah": format_rupiah,
        "sidebar_accounts_total": _account_balance_total(db, user.id),
    })


@router.post("/accounts/create")
def create_account(
    name: str = Form(...),
    type: str = Form(...),
    icon: str = Form(""),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Pure add-account: balance stays 0, set later via \"Isi Saldo\"."""
    try:
        accounts_service.create_account(
            db, user_id=user.id, name=name, type_=AccountType(type),
            initial_balance=0, icon=icon or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/accounts", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/accounts/edit/{account_id}", response_class=HTMLResponse)
def edit_account_form(account_id: int, request: Request,
                      db: Session = Depends(get_db),
                      user: CurrentUser = Depends(get_current_user)):
    account = accounts_service.get_account(db, account_id, user.id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return templates.TemplateResponse(request, "accounts/edit.html", {
        "account": account, "account_types": AccountType,
        "icon_pools": ACCOUNT_ICON_POOLS,
        "format_rupiah": format_rupiah,
        "sidebar_accounts_total": _account_balance_total(db, user.id),
    })


@router.post("/accounts/edit/{account_id}")
def edit_account(account_id: int, name: str = Form(...), type: str = Form(...),
                 initial_balance: str = Form("0"), icon: str = Form(""),
                 db: Session = Depends(get_db),
                 user: CurrentUser = Depends(get_current_user)):
    # Ownership FIRST so intruders always get 404, never a balance parse error.
    if not accounts_service.get_own_account(db, account_id, user.id):
        raise HTTPException(status_code=404, detail="Account not found")
    init_bal = _parse_balance(initial_balance)
    try:
        accounts_service.update_account(
            db, account_id, user.id, name=name.strip(), type=AccountType(type),
            initial_balance=init_bal, icon=icon or None,
        )
    except accounts_service.AccountNotFound:
        raise HTTPException(status_code=404, detail="Account not found")
    return RedirectResponse(url="/accounts", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/accounts/delete/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db),
                   user: CurrentUser = Depends(get_current_user)):
    try:
        accounts_service.delete_account(db, account_id, user.id)
    except accounts_service.AccountNotFound:
        raise HTTPException(status_code=404, detail="Account not found")
    except ValueError:
        raise HTTPException(status_code=400, detail="Account masih dipakai transaksi")
    return RedirectResponse(url="/accounts", status_code=status.HTTP_303_SEE_OTHER)
