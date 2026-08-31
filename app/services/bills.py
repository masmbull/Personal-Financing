"""Bill service - recurring bills, due-date math and payment recording."""
import calendar
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.models import Bill, BillPayment, BillFrequency, TransactionType
from app.services.finance import create_transaction


class BillNotFound(Exception):
    pass


def get_bill(db: Session, bill_id: int, user_id: int) -> Bill:
    bill = db.query(Bill).filter(
        Bill.id == bill_id, Bill.user_id == user_id
    ).first()
    if not bill:
        raise BillNotFound(f"Bill {bill_id} not found")
    return bill


def list_bills(db: Session, user_id: int, active_only: bool = True):
    query = db.query(Bill).filter(Bill.user_id == user_id).order_by(Bill.name)
    if active_only:
        query = query.filter(Bill.active == True)  # noqa: E712
    return query.all()


def compute_next_due_date(bill: Bill, today: date | None = None) -> date | None:
    """Next occurrence of a recurring bill. Returns None when unknown."""
    today = today or date.today()
    if not bill.due_day:
        return None
    if bill.frequency == BillFrequency.MONTHLY:
        if today.day <= bill.due_day:
            return today.replace(day=bill.due_day)
        m, y = today.month + 1, today.year
        if m > 12:
            m, y = 1, y + 1
        return date(y, m, min(bill.due_day, calendar.monthrange(y, m)[1]))
    if bill.frequency == BillFrequency.WEEKLY:
        days_ahead = (bill.due_day - today.weekday()) % 7 or 7
        return today + timedelta(days=days_ahead)
    if bill.frequency == BillFrequency.YEARLY:
        candidate = _safe_date(today.year, today.month, bill.due_day)
        if candidate is None or candidate < today:
            candidate = _safe_date(today.year + 1, today.month, bill.due_day)
        return candidate or date(today.year + 1, 1, 1)
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    last = calendar.monthrange(year, month)[1]
    if day > last:
        return None
    return date(year, month, day)


def with_next_due(db: Session, user_id: int, today: date | None = None) -> list[dict]:
    return [
        {"bill": b, "next_due": compute_next_due_date(b, today)}
        for b in list_bills(db, user_id)
    ]


def create_bill(db: Session, *, user_id: int, **fields) -> Bill:
    amount = int(fields["amount"])
    if amount <= 0:
        raise ValueError("Amount must be positive")
    bill = Bill(
        user_id=user_id,
        name=(fields["name"] or "").strip(),
        amount=amount,
        frequency=fields.get("frequency", BillFrequency.MONTHLY),
        category_id=fields.get("category_id"),
        account_id=fields.get("account_id"),
        due_day=fields.get("due_day"),
        auto_create=bool(fields.get("auto_create", False)),
        notes=(fields.get("notes") or "").strip() or None,
    )
    db.add(bill)
    db.commit()
    db.refresh(bill)
    return bill


def update_bill(db: Session, bill_id: int, user_id: int, fields: dict) -> Bill:
    bill = get_bill(db, bill_id, user_id)
    for key in ("name", "amount", "frequency", "category_id", "account_id",
                "due_day", "active", "notes"):
        value = fields.get(key)
        if value is not None:
            setattr(bill, key, value)
    db.commit()
    db.refresh(bill)
    return bill


def pay_bill(db: Session, bill_id: int, user_id: int, *, amount: int | None = None,
             account_id: int | None = None, pay_date: date | None = None):
    """Record a payment; optionally creates a real expense transaction."""
    bill = get_bill(db, bill_id, user_id)
    pay_amount = int(amount) if amount else bill.amount
    pay_date = pay_date or date.today()
    tx_id = None
    effective_account = account_id or bill.account_id
    if effective_account:
        category_id = bill.category_id
        if not category_id:
            from app.models.models import Category
            cat = db.query(Category).filter(
                Category.name == "Tagihan",
                Category.type == TransactionType.EXPENSE,
            ).first()
            if not cat:
                cat = Category(name="Tagihan",
                               type=TransactionType.EXPENSE, icon="📄")
                db.add(cat)
                db.flush()
            category_id = cat.id
        tx = create_transaction(
            db=db, user_id=user_id, type=TransactionType.EXPENSE,
            amount=pay_amount, account_id=int(effective_account),
            category_id=category_id, date_val=pay_date,
            description="Bayar %s" % bill.name,
        )
        tx_id = tx.id
    payment = BillPayment(
        user_id=user_id, bill_id=bill.id, amount=pay_amount,
        paid_date=pay_date,
        transaction_id=tx_id,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return bill, payment


def delete_bill(db: Session, bill_id: int, user_id: int) -> None:
    bill = get_bill(db, bill_id, user_id)
    db.delete(bill)
    db.commit()
