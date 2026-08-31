"""Transaction service - listing/filtering/pagination + partial updates.

Core create/delete/balance logic stays in app.services.finance; this module
adds API-oriented operations shared by the REST layer.
"""
from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.models import Transaction, TransactionType
from app.services.finance import create_transaction, delete_transaction


class TransactionNotFound(Exception):
    pass


def _to_response(tx: Transaction) -> dict:
    """Explicit response payload - SQLAlchemy objects are never returned raw."""
    return {
        "id": tx.id,
        "type": tx.type.value,
        "amount": tx.amount,
        "account_id": tx.account_id,
        "account_name": tx.account.name if tx.account else None,
        "category_id": tx.category_id,
        "category_name": tx.category.name if tx.category else None,
        "transfer_to_account_id": tx.transfer_to_account_id,
        "merchant": tx.merchant,
        "description": tx.description,
        "notes": tx.notes,
        "date": tx.date,
        "created_at": tx.created_at,
    }


def list_transactions(
    db: Session, *, user_id: int,
    type: Optional[str] = None,
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    transfer_to_account_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    merchant: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    query = db.query(Transaction).options(
        joinedload(Transaction.account),
        joinedload(Transaction.category),
        joinedload(Transaction.transfer_to_account),
    ).filter(Transaction.user_id == user_id)
    if type:
        query = query.filter(Transaction.type == TransactionType(type.upper()))
    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    if category_id:
        query = query.filter(Transaction.category_id == category_id)
    if transfer_to_account_id:
        query = query.filter(Transaction.transfer_to_account_id == transfer_to_account_id)
    if date_from:
        query = query.filter(Transaction.date >= date_from)
    if date_to:
        query = query.filter(Transaction.date <= date_to)
    if merchant:
        query = query.filter(Transaction.merchant.ilike(f"%{merchant}%"))
    if search:
        query = query.filter(
            Transaction.description.ilike(f"%{search}%") |
            Transaction.merchant.ilike(f"%{search}%") |
            Transaction.notes.ilike(f"%{search}%")
        )

    total = query.with_entities(func.count(Transaction.id)).scalar()
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    items = (
        query.order_by(Transaction.date.desc(), Transaction.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [_to_response(t) for t in items], total, page, page_size


def get_transaction(db: Session, tx_id: int, user_id: int) -> dict:
    """Ownership-checked lookup: id AND owner in one query."""
    tx = (
        db.query(Transaction)
        .options(joinedload(Transaction.account), joinedload(Transaction.category))
        .filter(Transaction.id == tx_id, Transaction.user_id == user_id)
        .first()
    )
    if not tx:
        raise TransactionNotFound(f"Transaction {tx_id} not found")
    return _to_response(tx)


def update_transaction(db: Session, tx_id: int, fields: dict, user_id: int) -> dict:
    """Partial update. Reuses delete+create semantics from the HTML edit flow so
    balance recalculation and validation stay in one code path."""
    tx = db.query(Transaction).filter(
        Transaction.id == tx_id, Transaction.user_id == user_id
    ).first()
    if not tx:
        raise TransactionNotFound(f"Transaction {tx_id} not found")

    merged = {
        "type": (fields.get("type") or tx.type),
        "amount": fields.get("amount", tx.amount),
        "account_id": fields.get("account_id", tx.account_id),
        "category_id": fields.get("category_id", tx.category_id),
        "date_val": fields.get("date", tx.date),
        "description": fields.get("description", tx.description),
        "merchant": fields.get("merchant", tx.merchant),
        "notes": fields.get("notes", tx.notes),
        "transfer_to_account_id": fields.get(
            "transfer_to_account_id", tx.transfer_to_account_id
        ),
    }
    delete_transaction(db, tx_id, user_id)
    try:
        new_tx = create_transaction(
            db=db, user_id=user_id,
            type=merged["type"] if isinstance(merged["type"], TransactionType)
            else TransactionType(str(merged["type"]).upper()),
            amount=int(merged["amount"]),
            account_id=int(merged["account_id"]),
            category_id=int(merged["category_id"]) if merged["category_id"] else None,
            date_val=merged["date_val"],
            description=merged["description"],
            transfer_to_account_id=(
                int(merged["transfer_to_account_id"])
                if merged["transfer_to_account_id"] else None
            ),
            merchant=merged["merchant"],
            notes=merged["notes"],
        )
    except ValueError as e:
        db.rollback()
        raise ValueError(str(e)) from e
    return get_transaction(db, new_tx.id, user_id)
