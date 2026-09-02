"""Bill service - recurring bills, due-date math and payment recording."""
import calendar
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.models import (
    Bill, BillPayment, BillFrequency, BillOccurrence, BillOccurrenceStatus,
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

