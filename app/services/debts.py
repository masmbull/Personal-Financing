"""Debt service - payable/receivable lifecycle + payments."""
from datetime import date

from sqlalchemy.orm import Session

from app.models.models import (
    Category, Debt, DebtPayment, DebtStatus, DebtType, TransactionType,
)
from app.services.finance import create_transaction


class DebtNotFound(Exception):
    pass


class PaymentError(ValueError):
    pass


def _update_debt_status(debt: Debt) -> None:
    if debt.remaining_amount <= 0:
        debt.status = DebtStatus.PAID
    elif debt.remaining_amount < debt.principal_amount:
        debt.status = DebtStatus.PARTIALLY_PAID
    elif debt.due_date and debt.due_date < date.today():
        debt.status = DebtStatus.OVERDUE
    else:
        debt.status = DebtStatus.OPEN


def get_debt(db: Session, debt_id: int) -> Debt:
    debt = db.query(Debt).filter(Debt.id == debt_id).first()
    if not debt:
        raise DebtNotFound(f"Debt {debt_id} not found")
    return debt


def list_debts(db: Session, type: DebtType | None = None):
    query = db.query(Debt).order_by(Debt.created_at.desc())
    if type:
        query = query.filter(Debt.type == type)
    debts = query.all()
    today = date.today()
    for d in debts:
        if d.status != DebtStatus.PAID and d.due_date and d.due_date < today:
            d.status = DebtStatus.OVERDUE
    return debts


def totals_for(db: Session) -> dict:
    from sqlalchemy import func
    payable = db.query(func.coalesce(func.sum(Debt.remaining_amount), 0)).filter(
        Debt.type == DebtType.PAYABLE, Debt.status != DebtStatus.PAID,
    ).scalar()
    receivable = db.query(func.coalesce(func.sum(Debt.remaining_amount), 0)).filter(
        Debt.type == DebtType.RECEIVABLE, Debt.status != DebtStatus.PAID,
    ).scalar()
    return {"total_payable": payable, "total_receivable": receivable}


def create_debt(db: Session, **fields) -> Debt:
    principal = int(fields["principal_amount"])
    if principal <= 0:
        raise ValueError("Amount must be positive")
    debt = Debt(
        type=fields["type"],
        person_name=fields["person_name"].strip(),
        description=(fields.get("description") or "").strip() or None,
        principal_amount=principal,
        remaining_amount=principal,
        start_date=date.today(),
        due_date=fields.get("due_date"),
        installment_amount=fields.get("installment_amount"),
        installment_count=fields.get("installment_count"),
        interest_rate=fields.get("interest_rate"),
        notes=(fields.get("notes") or "").strip() or None,
        person_contact=(fields.get("person_contact") or "").strip() or None,
        related_account_id=fields.get("related_account_id"),
    )
    db.add(debt)
    db.commit()
    db.refresh(debt)
    return debt


def update_debt(db: Session, debt_id: int, fields: dict) -> Debt:
    debt = get_debt(db, debt_id)
    editable = [
        "person_name", "description", "due_date", "installment_amount",
        "installment_count", "interest_rate", "person_contact",
        "related_account_id", "notes",
    ]
    for key in editable:
        value = fields.get(key)
        if value is not None:
            setattr(debt, key, value)
    _update_debt_status(debt)
    db.commit()
    db.refresh(debt)
    return debt


def pay_debt(db: Session, debt_id: int, *, amount: int,
             account_id: int | None = None, payment_date: date | None = None,
             notes: str | None = None):
    """Record a payment. When account_id is provided a real expense/income
    transaction is created so account balances stay accurate."""
    debt = get_debt(db, debt_id)
    amount = int(amount)
    if amount <= 0:
        raise PaymentError("Payment must be positive")
    if amount > debt.remaining_amount:
        raise PaymentError("Payment exceeds remaining amount")
    pay_date = payment_date or date.today()

    tx_id = None
    if account_id:
        is_payable = debt.type == DebtType.PAYABLE
        cat_name = "Bayar Hutang" if is_payable else "Terima Piutang"
        cat_type = TransactionType.EXPENSE if is_payable else TransactionType.INCOME
        cat = db.query(Category).filter(
            Category.name == cat_name, Category.type == cat_type
        ).first()
        if not cat:
            cat = Category(name=cat_name, type=cat_type,
                           icon="💸" if is_payable else "💰")
            db.add(cat)
            db.flush()
        desc = (("Bayar hutang ke %s" % debt.person_name) if is_payable
                else ("Terima piutang dari %s" % debt.person_name))
        tx = create_transaction(
            db=db, type=cat_type, amount=amount, account_id=int(account_id),
            category_id=cat.id, date_val=pay_date, description=desc,
        )
        tx_id = tx.id

    debt.remaining_amount -= amount
    _update_debt_status(debt)
    payment = DebtPayment(
        debt_id=debt.id, amount=amount, payment_date=pay_date,
        notes=(notes or "").strip() or None, transaction_id=tx_id,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return debt, payment


def delete_debt(db: Session, debt_id: int) -> None:
    debt = get_debt(db, debt_id)
    db.delete(debt)
    db.commit()
