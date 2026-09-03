"""Credit card statement engine — domain calculations.

Given a credit card account's statement_date and payment_due_day (day of month,
1-28 so every month has that day), computes the current/previous statement
period and payment status. This is the domain foundation; it does NOT build a
full bank-statement reconciliation system.
"""
import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.models import Account, AccountType, Transaction, TransactionType
from app.services.finance import create_transaction


@dataclass
class StatementPeriod:
    closing_date: date
    due_date: date
    period_start: date
    period_end: date
    statement_balance: int
    minimum_payment: int
    payment_status: str  # "PAID" | "PARTIAL" | "UNPAID" | "NOT_DUE"


def _shift_month(y: int, m: int, delta: int) -> tuple[int, int]:
    total = y * 12 + (m - 1) + delta
    return total // 12, total % 12 + 1


def statement_closing_date(statement_day: int, ref: date) -> date:
    """The most recent closing date <= ref for the given statement day."""
    # Candidate: this month's closing on `statement_day`
    # If it's after ref, use previous month's closing.
    y, m = ref.year, ref.month
    last_day = calendar.monthrange(y, m)[1]
    day = min(statement_day, last_day)
    cand = date(y, m, day)
    if cand <= ref:
        return cand
    py, pm = _shift_month(y, m, -1)
    last_day = calendar.monthrange(py, pm)[1]
    return date(py, pm, min(statement_day, last_day))


def statement_period_for(account: Account, ref: date | None = None) -> StatementPeriod:
    """Compute the current statement period for a credit card.

    Period closes on statement_date; payment is due payment_due_day days after
    closing. relieved of the previous statement's charges.
    """
    if account.type != AccountType.CREDIT_CARD or not account.statement_date:
        raise ValueError("Not a credit card with a statement_date")
    ref = ref or date.today()
    closing = statement_closing_date(account.statement_date, ref)

    # Determine due date: use the billing-cycle convention where due date is
    # the payment_due_day of the month AFTER closing (typical ~15-25 days later).
    # If no payment_due_day set, default to 21 days after closing.
    if account.payment_due_day:
        cy, cm = closing.year, closing.month
        due_y, due_m = _shift_month(cy, cm, 1)
        last_day = calendar.monthrange(due_y, due_m)[1]
        due = date(due_y, due_m, min(account.payment_due_day, last_day))
    else:
        due = closing + timedelta(days=21)

    # Period start = day after the PREVIOUS closing.
    prev_y, prev_m = _shift_month(closing.year, closing.month, -1)
    prev_last = calendar.monthrange(prev_y, prev_m)[1]
    prev_closing = date(prev_y, prev_m, min(account.statement_date, prev_last))
    period_start = prev_closing + timedelta(days=1)
    period_end = closing

    return StatementPeriod(
        closing_date=closing, due_date=due,
        period_start=period_start, period_end=period_end,
        statement_balance=0, minimum_payment=0, payment_status="NOT_DUE",
    )


def calculate_statement(db: Session, account: Account, ref: date | None = None,
                        user_id: int | None = None) -> StatementPeriod:
    """Compute a credit card's current statement with balance + payment status.

    statement_balance = net expense in the period on the card (sum of EXPENSE
    amounts), since a credit-card expense increases liability.
    minimum_payment = 10% of statement_balance (standard Indonesian CC floor,
    common minimum 3-10%; we use 10% as a documented default).
    payment_status derives from transactions that are credit-card TRANSFER
    payments credited within [period_start, due_date].
    """
    if account.type != AccountType.CREDIT_CARD or not account.statement_date:
        raise ValueError("Not a credit card with a statement_date")
    period = statement_period_for(account, ref)

    q = db.query(Transaction).filter(
        Transaction.account_id == account.id,
        Transaction.type == TransactionType.EXPENSE,
        Transaction.date >= period.period_start,
        Transaction.date <= period.period_end,
    )
    if user_id is not None:
        q = q.filter(Transaction.user_id == user_id)
    charges = sum(t.amount for t in q.all())

    # Payments: TRANSFER into this card within the period
    pay_q = db.query(Transaction).filter(
        Transaction.transfer_to_account_id == account.id,
        Transaction.type == TransactionType.TRANSFER,
        Transaction.date >= period.period_start,
        Transaction.date <= period.due_date,
    )
    if user_id is not None:
        pay_q = pay_q.filter(Transaction.user_id == user_id)
    paid = sum(t.amount for t in pay_q.all())

    minimum = int(charges * 0.10)
    if charges == 0:
        status = "NOT_DUE"
    elif paid >= charges:
        status = "PAID"
    elif paid > 0:
        status = "PARTIAL"
    else:
        status = "UNPAID"

    period.statement_balance = charges
    period.minimum_payment = minimum
    period.payment_status = status
    return period


def _to_dict(p: StatementPeriod) -> dict:
    return {
        "period_start": p.period_start,
        "closing_date": p.closing_date,
        "due_date": p.due_date,
        "period_end": p.period_end,
        "statement_balance": p.statement_balance,
        "minimum_payment": p.minimum_payment,
        "payment_status": p.payment_status,
    }


def credit_card_refund(db: Session, *, user_id: int, account_id: int,
                       amount: int, date_val, description: str | None = None,
                       category_id: int | None = None) -> "Transaction":
    """Reverse a credit-card charge: the issuer credits the card back.

    Accounting: the card's outstanding liability DECREASES, so the balance moves
    toward zero. We model this as a REFUND transaction on the card account — it
    is balance-positive (liability down) but is NOT counted as income. No cash
    account is touched (the money never left the card).
    """
    if amount <= 0:
        raise ValueError("Refund amount must be positive")
    account = db.query(Account).filter(
        Account.id == account_id, Account.user_id == user_id
    ).first()
    if not account or account.type != AccountType.CREDIT_CARD:
        raise ValueError("Refund target must be an owned credit-card account")
    tx = create_transaction(
        db=db, user_id=user_id, type=TransactionType.REFUND, amount=amount,
        account_id=account_id, category_id=category_id,
        date_val=date_val, description=description,
    )
    return tx
