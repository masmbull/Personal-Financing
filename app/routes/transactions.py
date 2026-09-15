from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, func
from app.database.db import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.models import Transaction, Account, Category, TransactionType, TransactionTag, Tag
from app.services.finance import create_transaction, delete_transaction
from app.api.audit_decorator import audit_action
from app.utils import format_rupiah, today_str
from app.validation import parse_idr_input
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
    """Strictly own accounts. Legacy NULL rows hidden."""
    return db.query(Account).filter(
        Account.user_id == user_id
    ).order_by(Account.name).all()


@router.get("/transactions", response_class=HTMLResponse)
def list_transactions(
    request: Request,
    filter_date_from: str = "",
    filter_date_to: str = "",
    filter_account: str = "",
    filter_category: str = "",
    filter_tag: str = "",
    search: str = "",
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    query = db.query(Transaction).options(
        joinedload(Transaction.account),
        joinedload(Transaction.category),
        joinedload(Transaction.transfer_to_account),
        joinedload(Transaction.tags),
    ).filter(Transaction.user_id == user.id)
    if filter_date_from:
        query = query.filter(Transaction.date >= date.fromisoformat(filter_date_from))
    if filter_date_to:
        query = query.filter(Transaction.date <= date.fromisoformat(filter_date_to))
    if filter_account:
        query = query.filter(Transaction.account_id == int(filter_account))
    if filter_category:
        query = query.filter(Transaction.category_id == int(filter_category))
    if filter_tag:
        tag_ids = db.query(TransactionTag.transaction_id).filter(
            TransactionTag.tag_id == int(filter_tag)
        ).subquery()
        query = query.filter(Transaction.id.in_(tag_ids))
    if search:
        query = query.filter(
            Transaction.description.ilike(f"%{search}%") |
            Transaction.merchant.ilike(f"%{search}%")
        )

    transactions = query.order_by(desc(Transaction.date), desc(Transaction.id)).limit(200).all()
    accounts = _visible_accounts(db, user.id)
    categories = db.query(Category).order_by(Category.name).all()
    tags = db.query(Tag).filter(Tag.user_id == user.id).order_by(Tag.name).all()
    for tx in transactions:
        _set_tx_display(tx)

    # Summary totals for filtered result
    total_income = sum(tx.amount for tx in transactions if tx.type == TransactionType.INCOME)
    total_expense = sum(tx.amount for tx in transactions if tx.type == TransactionType.EXPENSE)

    return templates.TemplateResponse(request, "transactions/list.html", {
        "transactions": transactions,
        "accounts": accounts, "categories": categories, "tags": tags,
        "format_rupiah": format_rupiah, "today": today_str(),
        "total_income": total_income, "total_expense": total_expense,
        "filters": {
            "date_from": filter_date_from, "date_to": filter_date_to,
            "account": filter_account, "category": filter_category,
            "tag": filter_tag, "search": search,
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
@audit_action(action="transaction_create", entity="transaction")
def add_transaction(
    request: Request,
    type: str = Form(...), amount: str = Form(...), account_id: str = Form(...),
    category_id: str = Form(""), transfer_to_account_id: str = Form(""),
    date_val: str = Form(...), description: str = Form(""),
    merchant: str = Form(""),
    tag_ids: str = Form(""),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    try:
        amount_int = parse_idr_input(amount, "Nominal")
        tx_date = date.fromisoformat(date_val)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        tx = create_transaction(
            db=db, user_id=user.id, type=TransactionType(type), amount=amount_int,
            account_id=int(account_id),
            category_id=int(category_id) if category_id else None,
            date_val=tx_date, description=description.strip() if description else None,
            transfer_to_account_id=int(transfer_to_account_id) if transfer_to_account_id else None,
            merchant=merchant.strip() if merchant else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if tag_ids and tx:
        from app.services.tags import attach_tags
        ids = [int(x) for x in tag_ids.split(",") if x.strip().isdigit()]
        if ids:
            attach_tags(db, tx.id, ids, user.id)
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
@audit_action(action="transaction_update", entity="transaction")
def edit_transaction(
    request: Request,
    tx_id: int, type: str = Form(...), amount: str = Form(...),
    account_id: str = Form(...), category_id: str = Form(""),
    transfer_to_account_id: str = Form(""), date_val: str = Form(...),
    description: str = Form(""), merchant: str = Form(""),
    tag_ids: str = Form(""),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    tx = db.query(Transaction).filter(
        Transaction.id == tx_id, Transaction.user_id == user.id
    ).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    try:
        amount_int = parse_idr_input(amount, "Nominal")
        tx_date = date.fromisoformat(date_val)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    delete_transaction(db, tx_id, user.id)
    new_tx = create_transaction(
        db=db, user_id=user.id, type=TransactionType(type), amount=amount_int,
        account_id=int(account_id),
        category_id=int(category_id) if category_id else None,
        date_val=tx_date, description=description.strip() if description else None,
        transfer_to_account_id=int(transfer_to_account_id) if transfer_to_account_id else None,
        merchant=merchant.strip() if merchant else None,
    )
    if tag_ids and new_tx:
        from app.services.tags import attach_tags
        ids = [int(x) for x in tag_ids.split(",") if x.strip().isdigit()]
        if ids:
            attach_tags(db, new_tx.id, ids, user.id)
    return RedirectResponse(url="/transactions", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/transactions/delete/{tx_id}")
@audit_action(action="transaction_delete", entity="transaction")
def delete_tx(tx_id: int, request: Request, db: Session = Depends(get_db),
              user: CurrentUser = Depends(get_current_user)):
    if not delete_transaction(db, tx_id, user.id):
        raise HTTPException(status_code=404, detail="Transaction not found")
    return RedirectResponse(url="/transactions", status_code=status.HTTP_303_SEE_OTHER)