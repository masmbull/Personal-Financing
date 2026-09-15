"""Recurring transaction service — CRUD + scheduler."""
import calendar
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.models import (
    Account, RecurringFrequency, RecurringTransaction,
    Transaction, TransactionType,
)


class RecurringNotFound(Exception):
    pass


def _assert_account_owned(db: Session, account_id: int, user_id: int) -> None:
    acc = db.query(Account).filter(
        Account.id == account_id, Account.user_id == user_id
    ).first()
    if not acc:
        raise ValueError("Account not found or not owned by user")


def create_recurring(
    db: Session, *, user_id: int, account_id: int, category_id,
    tx_type: str, amount: int, description, frequency: str,
    start_date: date, notes=None,
) -> RecurringTransaction:
    amount = int(amount)
    if amount <= 0:
        raise ValueError("Amount must be positive")
    _assert_account_owned(db, account_id, user_id)
    rec = RecurringTransaction(
        user_id=user_id, account_id=account_id,
        category_id=int(category_id) if category_id else None,
        type=TransactionType(tx_type), amount=amount,
        description=description,
        frequency=RecurringFrequency(frequency),
        next_due_date=start_date, notes=notes,
    )
    db.add(rec); db.commit(); db.refresh(rec)
    return rec


def list_recurring(db: Session, user_id: int) -> list:
    return (
        db.query(RecurringTransaction)
        .filter(RecurringTransaction.user_id == user_id)
        .order_by(RecurringTransaction.next_due_date)
        .all()
    )


def get_recurring(db: Session, rec_id: int, user_id: int) -> RecurringTransaction:
    r = db.query(RecurringTransaction).filter(
        RecurringTransaction.id == rec_id,
        RecurringTransaction.user_id == user_id,
    ).first()
    if not r:
        raise RecurringNotFound(f"RecurringTransaction {rec_id} not found")
    return r


def update_recurring(db: Session, rec_id: int, user_id: int, **fields) -> RecurringTransaction:
    r = get_recurring(db, rec_id, user_id)
    allowed = {"amount", "description", "frequency", "next_due_date",
               "active", "notes", "category_id", "account_id"}
    for k, v in fields.items():
        if k in allowed and v is not None:
            setattr(r, k, v)
    db.commit(); db.refresh(r)
    return r


def delete_recurring(db: Session, rec_id: int, user_id: int) -> None:
    r = get_recurring(db, rec_id, user_id)
    db.delete(r); db.commit()


def _advance(d: date, freq: RecurringFrequency) -> date:
    if freq == RecurringFrequency.DAILY:
        return d + timedelta(days=1)
    if freq == RecurringFrequency.WEEKLY:
        return d + timedelta(weeks=1)
    if freq == RecurringFrequency.MONTHLY:
        month = d.month + 1 if d.month < 12 else 1
        year  = d.year if d.month < 12 else d.year + 1
        day   = min(d.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    # YEARLY
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=28)


def generate_recurring_transactions(
    db: Session, as_of: date | None = None, user_id: int | None = None
) -> int:
    """Post all due recurring transactions up to as_of (default: today).

    Idempotent — checks for existing Transaction with marker in notes
    before inserting. Returns count of new Transaction rows created.
    """
    today = as_of or date.today()
    q = db.query(RecurringTransaction).filter(
        RecurringTransaction.active == True,  # noqa: E712
        RecurringTransaction.next_due_date <= today,
    )
    if user_id:
        q = q.filter(RecurringTransaction.user_id == user_id)

    created = 0
    for rec in q.all():
        while rec.next_due_date <= today:
            due = rec.next_due_date
            marker = f"[rec:{rec.id}:{due.isoformat()}]"
            exists = db.query(Transaction.id).filter(
                Transaction.user_id == rec.user_id,
                Transaction.date == due,
                Transaction.notes.contains(marker),
            ).first()
            if not exists:
                acc = db.query(Account).filter(Account.id == rec.account_id).first()
                if acc:
                    tx = Transaction(
                        user_id=rec.user_id, account_id=rec.account_id,
                        category_id=rec.category_id, type=rec.type,
                        amount=rec.amount, date=due,
                        description=rec.description or "",
                        notes=marker,
                    )
                    db.add(tx)
                    if rec.type == TransactionType.EXPENSE:
                        acc.current_balance -= rec.amount
                    elif rec.type == TransactionType.INCOME:
                        acc.current_balance += rec.amount
                    created += 1
            rec.next_due_date = _advance(rec.next_due_date, rec.frequency)
        db.commit()
    return created


def row_payload(r: RecurringTransaction) -> dict:
    return {
        "id": r.id,
        "type": r.type.value,
        "amount": r.amount,
        "description": r.description,
        "frequency": r.frequency.value,
        "next_due_date": r.next_due_date.isoformat(),
        "active": r.active,
        "notes": r.notes,
        "account": {"id": r.account.id, "name": r.account.name} if r.account else None,
        "category": {
            "id": r.category.id, "name": r.category.name, "icon": r.category.icon,
        } if r.category else None,
    }
