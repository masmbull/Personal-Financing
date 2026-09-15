"""Recurring transactions web UI routes."""
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.database.db import get_db
from app.models.models import Account, Category, TransactionType
from app.services.recurring import (
    RecurringNotFound, create_recurring, delete_recurring,
    get_recurring, list_recurring, update_recurring,
)
from app.utils import format_rupiah, today_str
from app.validation import parse_idr_input

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()


def _own_accounts(db, user_id):
    return db.query(Account).filter(Account.user_id == user_id).order_by(Account.name).all()


def _all_categories(db):
    return db.query(Category).order_by(Category.name).all()


@router.get("/recurring", response_class=HTMLResponse)
def recurring_list(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    recurrings = list_recurring(db, user.id)
    return templates.TemplateResponse(request, "recurring/index.html", {
        "recurrings": recurrings, "format_rupiah": format_rupiah,
    })


@router.get("/recurring/add", response_class=HTMLResponse)
def recurring_add_form(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(request, "recurring/form.html", {
        "rec": None, "accounts": _own_accounts(db, user.id),
        "categories": _all_categories(db), "today": today_str(), "error": None,
    })


@router.post("/recurring/add")
def recurring_add(
    request: Request,
    tx_type: str = Form("EXPENSE"),
    amount: str = Form(...),
    description: str = Form(""),
    account_id: int = Form(...),
    category_id: str = Form(""),
    frequency: str = Form("MONTHLY"),
    start_date: str = Form(...),
    notes: str = Form(""),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        amt = parse_idr_input(amount)
        create_recurring(
            db, user_id=user.id, account_id=account_id,
            category_id=int(category_id) if category_id else None,
            tx_type=tx_type, amount=amt,
            description=description or None,
            frequency=frequency,
            start_date=date.fromisoformat(start_date),
            notes=notes or None,
        )
        return RedirectResponse("/recurring", status_code=303)
    except Exception as e:
        return templates.TemplateResponse(request, "recurring/form.html", {
            "rec": None, "accounts": _own_accounts(db, user.id),
            "categories": _all_categories(db), "today": today_str(),
            "error": str(e),
        }, status_code=400)


@router.get("/recurring/edit/{rec_id}", response_class=HTMLResponse)
def recurring_edit_form(
    rec_id: int, request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        rec = get_recurring(db, rec_id, user.id)
    except RecurringNotFound:
        return RedirectResponse("/recurring", status_code=303)
    return templates.TemplateResponse(request, "recurring/form.html", {
        "rec": rec, "accounts": _own_accounts(db, user.id),
        "categories": _all_categories(db), "today": today_str(), "error": None,
    })


@router.post("/recurring/edit/{rec_id}")
def recurring_edit(
    rec_id: int, request: Request,
    tx_type: str = Form("EXPENSE"),
    amount: str = Form(...),
    description: str = Form(""),
    account_id: int = Form(...),
    category_id: str = Form(""),
    frequency: str = Form("MONTHLY"),
    start_date: str = Form(...),
    active: str = Form(""),
    notes: str = Form(""),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        amt = parse_idr_input(amount)
        update_recurring(
            db, rec_id, user.id,
            amount=amt,
            description=description or None,
            account_id=account_id,
            category_id=int(category_id) if category_id else None,
            frequency=frequency,
            next_due_date=date.fromisoformat(start_date),
            active=bool(active),
            notes=notes or None,
        )
        return RedirectResponse("/recurring", status_code=303)
    except Exception as e:
        try:
            rec = get_recurring(db, rec_id, user.id)
        except RecurringNotFound:
            return RedirectResponse("/recurring", status_code=303)
        return templates.TemplateResponse(request, "recurring/form.html", {
            "rec": rec, "accounts": _own_accounts(db, user.id),
            "categories": _all_categories(db), "today": today_str(),
            "error": str(e),
        }, status_code=400)


@router.post("/recurring/delete/{rec_id}")
def recurring_delete(
    rec_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        delete_recurring(db, rec_id, user.id)
    except RecurringNotFound:
        pass
    return RedirectResponse("/recurring", status_code=303)
