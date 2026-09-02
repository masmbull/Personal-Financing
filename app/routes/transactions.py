from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, or_
from app.database.db import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.models import Transaction, Account, Category, TransactionType
from app.services.finance import create_transaction, delete_transaction
from app.utils import format_rupiah, today_str
from datetime import date
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


def _set_tx_display(tx):
    if tx.category:
        tx.category_display = tx.category.name
        tx.category_icon = tx.category.icon or ""
    elif tx.type == TransactionType.TRANSFER and tx.transfer_to_account:
        tx.category_display = "Transfer ke " + tx.transfer_to_account.name
        tx.category_icon = "\u2194"
    else:
        tx.category_display = tx.type.value
        tx.category_icon = ""


def _visible_accounts(db: Session, user_id: int):
    """Own accounts + global master accounts (user_id NULL)."""
    return db.query(Account).filter(
        or_(Account.user_id == user_id, Account.user_id.is_(None))
    ).order_by(Account.name).all()


@router.get("/transactions", response_class=HTMLResponse)
def list_transactions(
    request: Request,
    filter_date_from: str = "",
    filter_date_to: str = "",
    filter_account: str = "",
    filter_category: str = "",
    search: str = "",
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    query = db.query(Transaction).options(
        joinedload(Transaction.account),
        joinedload(Transaction.category),
        joinedload(Transaction.transfer_to_account),
    ).filter(Transaction.user_id == user.id)
    if filter_date_from:
        query = query.filter(Transaction.date >= date.fromisoformat(filter_date_from))
    if filter_date_to:
        query = query.filter(Transaction.date <= date.fromisoformat(filter_date_to))
    if filter_account:
        query = query.filter(Transaction.account_id == int(filter_account))
    if filter_category:
        query = query.filter(Transaction.category_id == int(filter_category))
    if search:
        query = query.filter(
            Transaction.description.ilike(f"%{search}%") |
            Transaction.merchant.ilike(f"%{search}%")
        )

    transactions = query.order_by(desc(Transaction.date), desc(Transaction.id)).limit(200).all()
    accounts = _visible_accounts(db, user.id)
    categories = db.query(Category).order_by(Category.name).all()
    for tx in transactions:
        _set_tx_display(tx)
    return templates.TemplateResponse(request, "transactions/list.html", { "transactions": transactions,
        "accounts": accounts, "categories": categories,
        "format_rupiah": format_rupiah, "today": today_str(),
        "filters": {
            "date_from": filter_date_from, "date_to": filter_date_to,
            "account": filter_account, "category": filter_category,
            "search": search,
        },
    })


@router.get("/transactions/add", response_class=HTMLResponse)
def add_transaction_form(request: Request, tx_type: str = "EXPENSE",
                         db: Session = Depends(get_db),
                         user: CurrentUser = Depends(get_current_user)):
    # Master accounts (NULL user_id) are read-only templates; only OWN accounts
    # can hold balances. Filter to own only so the dropdown never shows
    # something the service will reject with "Account not found".
    own_accounts = db.query(Account).filter(
        Account.user_id == user.id
    ).order_by(Account.name).all()
    categories = db.query(Category).filter(Category.type == TransactionType(tx_type)).order_by(Category.name).all()
    return templates.TemplateResponse(request, "transactions/add.html", {
        "accounts": own_accounts, "categories": categories,
        "tx_type": tx_type, "today": today_str(), "TransactionType": TransactionType,
        "has_accounts": len(own_accounts) > 0,
    })


@router.post("/transactions/add")
def add_transaction(
    type: str = Form(...), amount: str = Form(...), account_id: str = Form(...),
    category_id: str = Form(""), transfer_to_account_id: str = Form(""),
    date_val: str = Form(...), description: str = Form(""),
    merchant: str = Form(""),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    try:
        amount_int = int(amount)
        tx_date = date.fromisoformat(date_val)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid input")
    if amount_int <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    try:
        create_transaction(
            db=db, user_id=user.id, type=TransactionType(type), amount=amount_int,
            account_id=int(account_id),
            category_id=int(category_id) if category_id else None,
            date_val=tx_date, description=description.strip() if description else None,
            transfer_to_account_id=int(transfer_to_account_id) if transfer_to_account_id else None,
            merchant=merchant.strip() if merchant else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/transactions/edit/{tx_id}", response_class=HTMLResponse)
def edit_transaction_form(tx_id: int, request: Request,
                          db: Session = Depends(get_db),
                          user: CurrentUser = Depends(get_current_user)):
    tx = db.query(Transaction).filter(
        Transaction.id == tx_id, Transaction.user_id == user.id
    ).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    accounts = _visible_accounts(db, user.id)
    categories = db.query(Category).order_by(Category.name).all()
    return templates.TemplateResponse(request, "transactions/edit.html", { "tx": tx, "accounts": accounts,
        "categories": categories, "TransactionType": TransactionType,
    })


@router.post("/transactions/edit/{tx_id}")
def edit_transaction(
    tx_id: int, type: str = Form(...), amount: str = Form(...),
    account_id: str = Form(...), category_id: str = Form(""),
    transfer_to_account_id: str = Form(""), date_val: str = Form(...),
    description: str = Form(""), merchant: str = Form(""),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    tx = db.query(Transaction).filter(
        Transaction.id == tx_id, Transaction.user_id == user.id
    ).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    try:
        amount_int = int(amount)
        tx_date = date.fromisoformat(date_val)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid input")
    delete_transaction(db, tx_id, user.id)
    create_transaction(
        db=db, user_id=user.id, type=TransactionType(type), amount=amount_int,
        account_id=int(account_id),
        category_id=int(category_id) if category_id else None,
        date_val=tx_date, description=description.strip() if description else None,
        transfer_to_account_id=int(transfer_to_account_id) if transfer_to_account_id else None,
        merchant=merchant.strip() if merchant else None,
    )
    return RedirectResponse(url="/transactions", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/transactions/delete/{tx_id}")
def delete_tx(tx_id: int, db: Session = Depends(get_db),
              user: CurrentUser = Depends(get_current_user)):
    if not delete_transaction(db, tx_id, user.id):
        raise HTTPException(status_code=404, detail="Transaction not found")
    return RedirectResponse(url="/transactions", status_code=status.HTTP_303_SEE_OTHER)