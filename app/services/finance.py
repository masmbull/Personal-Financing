from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.models import Account, Transaction, Category, TransactionType


def recalculate_account_balance(db: Session, account_id: int, user_id: int):
    """Recompute an own account's current_balance from ITS OWN transactions.

    Global master accounts (user_id NULL) are never mutated here.
    """
    account = db.query(Account).filter(
        Account.id == account_id, Account.user_id == user_id
    ).first()
    if not account:
        return
    # Balance-affecting types. DEBT_REPAYMENT/DEBT_COLLECTION move cash like
    # expense/income (they change a real account balance) but are deliberately
    # excluded from income/expense REPORTS (see income_between/expense_between),
    # so debt principal is never double-counted as expense or income.
    income_like = (TransactionType.INCOME, TransactionType.DEBT_COLLECTION,
                   TransactionType.REFUND)
    expense_like = (TransactionType.EXPENSE, TransactionType.DEBT_REPAYMENT)
    transfer_like = (TransactionType.TRANSFER,)
    sums = {}
    for t in income_like + expense_like + transfer_like:
        sums[t] = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.account_id == account_id,
            Transaction.type == t,
            Transaction.user_id == user_id,
        ).scalar()
    transfer_in = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.transfer_to_account_id == account_id,
        Transaction.type == TransactionType.TRANSFER,
        Transaction.user_id == user_id,
    ).scalar()
    account.current_balance = (
        account.initial_balance
        + sum(sums[t] for t in income_like)
        - sum(sums[t] for t in expense_like)
        - sum(sums[t] for t in transfer_like)
        + transfer_in
    )
    db.commit()
    db.refresh(account)


def create_transaction(
    db: Session, *, user_id: int,
    type: TransactionType, amount: int, account_id: int,
    category_id: int | None, date_val: date, description: str | None,
    transfer_to_account_id: int | None = None, merchant: str | None = None,
    notes: str | None = None, merchant_id: int | None = None,
    payment_method_id: int | None = None,
    fuel_product_id: int | None = None,
    quantity_liters: float | None = None,
    price_per_liter: int | None = None,
) -> Transaction:
    """Create a transaction on an account OWNED BY ``user_id``.

    Master/global accounts (user_id NULL) cannot be used for transactions -
    this keeps balances strictly per-user.
    """
    if amount <= 0:
        raise ValueError("Amount must be positive")
    if quantity_liters is not None and quantity_liters <= 0:
        raise ValueError("Fuel quantity must be positive")
    if price_per_liter is not None and price_per_liter < 0:
        raise ValueError("Fuel price per liter cannot be negative")
    account = db.query(Account).filter(
        Account.id == account_id, Account.user_id == user_id
    ).first()
    if not account:
        raise ValueError("Account not found")
    if type == TransactionType.TRANSFER:
        if not transfer_to_account_id:
            raise ValueError("Transfer requires destination account")
        dest = db.query(Account).filter(
            Account.id == transfer_to_account_id, Account.user_id == user_id
        ).first()
        if not dest:
            raise ValueError("Destination account not found")
        if account_id == transfer_to_account_id:
            raise ValueError("Cannot transfer to same account")
    if type != TransactionType.TRANSFER and not category_id:
        # REFUND / DEBT_REPAYMENT / DEBT_COLLECTION are not true income/expense
        # and may be recorded without a category.
        if type not in (TransactionType.REFUND, TransactionType.DEBT_REPAYMENT,
                        TransactionType.DEBT_COLLECTION):
            raise ValueError("Category required for income/expense")
    if merchant_id is not None:
        from app.models.models import Merchant
        m = db.query(Merchant).filter(
            Merchant.id == merchant_id,
            (Merchant.user_id == user_id) | (Merchant.user_id.is_(None)),
        ).first()
        if not m:
            raise ValueError("Merchant not found or not owned")
    if payment_method_id is not None:
        from app.models.models import PaymentMethod
        pm = db.query(PaymentMethod).filter(
            PaymentMethod.id == payment_method_id,
            (PaymentMethod.user_id == user_id) | (PaymentMethod.user_id.is_(None)),
        ).first()
        if not pm:
            raise ValueError("Payment method not found or not owned")
    if fuel_product_id is not None:
        from app.models.models import FuelProduct
        fp = db.query(FuelProduct).filter(FuelProduct.id == fuel_product_id).first()
        if not fp:
            raise ValueError("Fuel product not found")
    transaction = Transaction(
        user_id=user_id, type=type, amount=amount, account_id=account_id,
        category_id=category_id if type != TransactionType.TRANSFER else None,
        transfer_to_account_id=transfer_to_account_id if type == TransactionType.TRANSFER else None,
        date=date_val, description=description,
        merchant=merchant.strip() if merchant else None,
        merchant_id=merchant_id, payment_method_id=payment_method_id,
        fuel_product_id=fuel_product_id,
        quantity_liters=quantity_liters, price_per_liter=price_per_liter,
        notes=notes.strip() if notes else None,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    recalculate_account_balance(db, account_id, user_id)
    if type == TransactionType.TRANSFER and transfer_to_account_id:
        recalculate_account_balance(db, transfer_to_account_id, user_id)
    return transaction


def delete_transaction(db: Session, transaction_id: int, user_id: int) -> bool:
    """Delete only when the transaction belongs to ``user_id``."""
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id, Transaction.user_id == user_id
    ).first()
    if not transaction:
        return False
    account_id = transaction.account_id
    transfer_to_id = transaction.transfer_to_account_id
    db.delete(transaction)
    db.commit()
    recalculate_account_balance(db, account_id, user_id)
    if transfer_to_id:
        recalculate_account_balance(db, transfer_to_id, user_id)
    return True


def has_transactions_for_category(db: Session, category_id: int) -> bool:
    count = db.query(func.count(Transaction.id)).filter(
        Transaction.category_id == category_id
    ).scalar()
    return count > 0


def get_dashboard_data(db: Session) -> dict:
    today = date.today()
    first_day_of_month = today.replace(day=1)
    total_balance = db.query(func.coalesce(func.sum(Account.current_balance), 0)).scalar()
    total_income = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.type == TransactionType.INCOME,
        Transaction.date >= first_day_of_month, Transaction.date <= today,
    ).scalar()
    total_expense = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.type == TransactionType.EXPENSE,
        Transaction.date >= first_day_of_month, Transaction.date <= today,
    ).scalar()
    recent_transactions = db.query(Transaction).order_by(
        Transaction.date.desc(), Transaction.id.desc()
    ).limit(10).all()
    expense_by_category = db.query(
        Category.name, Category.icon,
        func.sum(Transaction.amount).label("total")
    ).join(Category, Transaction.category_id == Category.id).filter(
        Transaction.type == TransactionType.EXPENSE,
        Transaction.date >= first_day_of_month, Transaction.date <= today,
    ).group_by(Category.id).order_by(func.sum(Transaction.amount).desc()).all()
    accounts = db.query(Account).order_by(Account.name).all()
    return {
        "total_balance": total_balance, "total_income": total_income,
        "total_expense": total_expense, "cashflow": total_income - total_expense,
        "recent_transactions": recent_transactions,
        "expense_by_category": expense_by_category, "accounts": accounts,
        }


def income_between(db: Session, start: date, end: date, user_id: int) -> int:
    """Total income in [start, end] (inclusive) for one user."""
    return db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.type == TransactionType.INCOME,
        Transaction.date >= start, Transaction.date <= end,
        Transaction.user_id == user_id,
    ).scalar()


def expense_between(db: Session, start: date, end: date, user_id: int) -> int:
    """Total expense in [start, end] (inclusive) for one user."""
    return db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.type == TransactionType.EXPENSE,
        Transaction.date >= start, Transaction.date <= end,
        Transaction.user_id == user_id,
    ).scalar()


def get_report_data(db: Session, user_id: int) -> dict:
    from datetime import timedelta
    today = date.today()
    first_day_of_month = today.replace(day=1)
    first_day_of_week = today - timedelta(days=today.weekday())
    today_expense = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.type == TransactionType.EXPENSE, Transaction.date == today,
        Transaction.user_id == user_id,
    ).scalar()
    week_expense = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.type == TransactionType.EXPENSE,
        Transaction.date >= first_day_of_week, Transaction.date <= today,
        Transaction.user_id == user_id,
    ).scalar()
    month_expense = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.type == TransactionType.EXPENSE,
        Transaction.date >= first_day_of_month, Transaction.date <= today,
        Transaction.user_id == user_id,
    ).scalar()
    month_income = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.type == TransactionType.INCOME,
        Transaction.date >= first_day_of_month, Transaction.date <= today,
        Transaction.user_id == user_id,
    ).scalar()
    expense_by_category = db.query(
        Category.name, Category.icon,
        func.sum(Transaction.amount).label("total")
    ).join(Category, Transaction.category_id == Category.id).filter(
        Transaction.type == TransactionType.EXPENSE,
        Transaction.date >= first_day_of_month, Transaction.date <= today,
        Transaction.user_id == user_id,
    ).group_by(Category.id).order_by(func.sum(Transaction.amount).desc()).all()
    monthly_data = []
    for i in range(5, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        m_first = date(y, m, 1)
        if m == 12:
            m_last = date(y + 1, 1, 1) - timedelta(days=1)
        else:
            m_last = date(y, m + 1, 1) - timedelta(days=1)
        inc = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.type == TransactionType.INCOME,
            Transaction.date >= m_first, Transaction.date <= m_last,
            Transaction.user_id == user_id,
        ).scalar()
        exp = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.type == TransactionType.EXPENSE,
            Transaction.date >= m_first, Transaction.date <= m_last,
            Transaction.user_id == user_id,
        ).scalar()
        monthly_data.append({"month": m_first.strftime("%b %Y"), "income": inc, "expense": exp})
    return {
        "today_expense": today_expense, "week_expense": week_expense,
        "month_expense": month_expense, "month_income": month_income,
        "expense_by_category": expense_by_category, "monthly_data": monthly_data,
    }


