"""Bill service - recurring bills, due-date math and payment recording."""
import calendar
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.models import (
    Account, Bill, BillPayment, BillFrequency, BillOccurrence, BillOccurrenceStatus,
    Category,
    TransactionType,
)
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


def _validate_bill_fields(db: Session, *, user_id: int, amount, frequency,
                          due_day, account_id, category_id, name) -> tuple:
    """Validate references and schedule semantics before a bill is persisted."""
    from app.services.finance import validate_amount

    normalized_amount = validate_amount(amount, "Amount")
    normalized_frequency = (
        frequency if isinstance(frequency, BillFrequency)
        else BillFrequency(str(frequency).upper())
    )
    normalized_name = (name or "").strip()
    if not normalized_name:
        raise ValueError("Bill name is required")
    if due_day is not None:
        due_day = int(due_day)
        maximum = 6 if normalized_frequency == BillFrequency.WEEKLY else 31
        minimum = 0 if normalized_frequency == BillFrequency.WEEKLY else 1
        if not minimum <= due_day <= maximum:
            label = "0-6 for weekly bills" if normalized_frequency == BillFrequency.WEEKLY else "1-31"
            raise ValueError(f"due_day must be {label}")
    if account_id is not None:
        account = db.query(Account).filter(
            Account.id == int(account_id), Account.user_id == user_id
        ).first()
        if account is None:
            raise ValueError("Account not found or not owned by user")
        account_id = account.id
    if category_id is not None:
        category = db.query(Category).filter(Category.id == int(category_id)).first()
        if category is None:
            raise ValueError("Category not found")
        if category.type != TransactionType.EXPENSE:
            raise ValueError("Bill category must be an expense category")
        category_id = category.id
    return normalized_amount, normalized_frequency, due_day, account_id, category_id, normalized_name


def create_bill(db: Session, *, user_id: int, **fields) -> Bill:
    amount, frequency, due_day, account_id, category_id, name = _validate_bill_fields(
        db, user_id=user_id, amount=fields["amount"],
        frequency=fields.get("frequency", BillFrequency.MONTHLY),
        due_day=fields.get("due_day"), account_id=fields.get("account_id"),
        category_id=fields.get("category_id"), name=fields.get("name"),
    )
    bill = Bill(
        user_id=user_id,
        name=name,
        amount=amount,
        frequency=frequency, category_id=category_id, account_id=account_id,
        due_day=due_day,
        auto_create=bool(fields.get("auto_create", False)),
        notes=(fields.get("notes") or "").strip() or None,
    )
    db.add(bill)
    db.commit()
    db.refresh(bill)
    return bill


def update_bill(db: Session, bill_id: int, user_id: int, fields: dict) -> Bill:
    bill = get_bill(db, bill_id, user_id)
    candidate = {
        "name": fields.get("name", bill.name),
        "amount": fields.get("amount", bill.amount),
        "frequency": fields.get("frequency", bill.frequency),
        "category_id": fields.get("category_id", bill.category_id),
        "account_id": fields.get("account_id", bill.account_id),
        "due_day": fields.get("due_day", bill.due_day),
    }
    amount, frequency, due_day, account_id, category_id, name = _validate_bill_fields(
        db, user_id=user_id, **candidate
    )
    bill.name = name
    bill.amount = amount
    bill.frequency = frequency
    bill.category_id = category_id
    bill.account_id = account_id
    bill.due_day = due_day
    for key in ("active", "notes"):
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


def pay_occurrence(db: Session, occurrence_id: int, user_id: int, *,
                   amount: int | None = None, account_id: int | None = None,
                   pay_date: date | None = None):
    """Pay a specific generated occurrence. Reuses ``pay_bill`` for the
    financial movement, then marks the occurrence PAID and links the
    resulting payment - so settling an occurrence is never double-counted
    (idempotency by (bill, due_date)). Raises BillNotFound if the occurrence
    is not owned or not DUE."""
    occurrence = db.query(BillOccurrence).filter(
        BillOccurrence.id == occurrence_id,
        BillOccurrence.user_id == user_id,
    ).first()
    if not occurrence:
        raise BillNotFound(f"Occurrence {occurrence_id} not found")
    if occurrence.status != BillOccurrenceStatus.DUE:
        raise ValueError("Occurrence is not DUE")
    bill, payment = pay_bill(
        db, occurrence.bill_id, user_id,
        amount=amount, account_id=account_id, pay_date=pay_date,
    )
    occurrence.status = BillOccurrenceStatus.PAID
    occurrence.bill_payment_id = payment.id
    db.commit()
    db.refresh(occurrence)
    return bill, payment, occurrence


def delete_bill(db: Session, bill_id: int, user_id: int) -> None:
    bill = get_bill(db, bill_id, user_id)
    db.delete(bill)
    db.commit()


# ==================== Bill auto-post scheduler ====================
#
# A bill occurrence is ONE scheduled due date of a recurring bill. The
# scheduler ONLY materialises unpaid "DUE" occurrences - it NEVER silently
# moves money. A real expense transaction is created only when the user pays
# the occurrence through the normal payment flow.
#
# Idempotency: (bill_id, due_date) is unique (schema-level UNIQUE index), so
# re-running the scheduler for an already-covered date inserts nothing.


def occurrence_dates(bill: Bill, after: date) -> list[date]:
    """Deterministic upcoming occurrence dates for a bill, strictly after
    ``after`` (exclusive). Handles monthly rollover, month-end clamping
    (31 -> Apr 30) and leap years (Feb 29).

    WEEKLY uses ``due_day`` as a weekday 0-6 (matching compute_next_due_date).
    Returns dates up to and including the coverage horizon (after + 2 years)
    for MONTHLY/YEARLY so overdue bills backfill completely.
    """
    from datetime import timedelta
    dates: list[date] = []
    freq = bill.frequency
    dd = bill.due_day

    if freq == BillFrequency.WEEKLY:
        if dd is None:
            return []
        # next strictly-after instance of weekday ``dd``, then each +7 days.
        cursor = after + timedelta(days=1)
        days_ahead = (dd - cursor.weekday()) % 7 or 7
        first = cursor + timedelta(days=days_ahead)
        dates.append(first)
        while len(dates) < 52:  # a year of weekly occurrences is plenty
            nxt = dates[-1] + timedelta(days=7)
            dates.append(nxt)
        return dates

    if freq == BillFrequency.MONTHLY:
        if dd is None:
            return []
        y, m = after.year, after.month
        # Same-month candidate when the due day has not passed yet.
        if after.day < dd:
            last = calendar.monthrange(y, m)[1]
            d = date(y, m, min(dd, last))
            if d > after:
                dates.append(d)
        # move to the month AFTER ``after``
        m += 1
        if m > 12:
            m, y = 1, y + 1
        for _ in range(24):
            last = calendar.monthrange(y, m)[1]
            day = min(dd, last)
            d = date(y, m, day)
            if d > after:
                dates.append(d)
            m += 1
            if m > 12:
                m, y = 1, y + 1
        return dates

    if freq == BillFrequency.YEARLY:
        if dd is None:
            return []
        # yearly, same month as ``after`` (matching compute_next_due_date),
        # clamped to valid day, strictly after ``after``.
        for offset in (0, 1, 2):
            yy = after.year + offset
            last = calendar.monthrange(yy, after.month)[1]
            day = min(dd, last)
            d = date(yy, after.month, day)
            if d > after:
                dates.append(d)
        return dates

    return []  # CUSTOM has no deterministic expansion


def generate_bill_occurrences(db: Session, *, as_of: date | None = None,
                              user_id: int | None = None) -> int:
    """Materialise DUE occurrences for every due date <= ``as_of`` that does
    not yet have an occurrence row. Idempotent - running again yields 0 new.

    Only ACTIVE bills owned by ``user_id`` (or all active bills when
    ``user_id`` is None) with a ``due_day`` and a payable account are
    considered. Returns the number of occurrences created.
    """
    from app.models.models import BillOccurrence
    as_of = as_of or date.today()
    query = db.query(Bill).filter(Bill.active == True)  # noqa: E712
    if user_id is not None:
        query = query.filter(Bill.user_id == user_id)
    created = 0
    for bill in query.all():
        # Skip bills with no due_day; skip when no account is configured so
        # the occurrence genuinely represents payable work for this user.
        if not bill.due_day or not bill.account_id:
            continue
        # Legacy ownerless bills (user_id NULL from old seeds) can't have
        # occurrences - the column is NOT NULL and nobody would see them.
        if bill.user_id is None:
            continue
        # Expand from a base date far enough back to catch overdue bills.
        # Use the earliest of (as_of - 2 years) or the bill's creation.
        # Minus 1 day so a due date in the SAME month as creation, after the
        # creation day, is included (created 1st, due 10th -> 10th counts).
        base = bill.created_at.date() - timedelta(days=1) if bill.created_at else as_of
        base = min(base, as_of)
        horizon = as_of - timedelta(days=365 * 2)
        base = min(base, horizon)
        for due in occurrence_dates(bill, base):
            if due > as_of:
                break
            # Idempotent skip: the UNIQUE(bill_id, due_date) constraint is the
            # backstop; the query below avoids the exception in the common case.
            existing = db.query(BillOccurrence.id).filter(
                BillOccurrence.bill_id == bill.id,
                BillOccurrence.due_date == due,
            ).first()
            if existing:
                continue
            db.add(BillOccurrence(
                user_id=bill.user_id, bill_id=bill.id,
                due_date=due, amount=bill.amount,
                status=BillOccurrenceStatus.DUE,
            ))
            created += 1
    db.commit()
    return created


def due_occurrences(db: Session, *, user_id: int,
                    as_of: date | None = None) -> list:
    """Unpaid (DUE) occurrences for one user, oldest due first."""
    from app.models.models import BillOccurrence, BillOccurrenceStatus
    as_of = as_of or date.today()
    return (
        db.query(BillOccurrence)
        .filter(BillOccurrence.user_id == user_id,
                BillOccurrence.status == BillOccurrenceStatus.DUE,
                BillOccurrence.due_date <= as_of)
        .order_by(BillOccurrence.due_date, BillOccurrence.id)
        .all()
    )

