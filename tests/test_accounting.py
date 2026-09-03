"""Accounting semantics invariant tests (Step 6 of the audit).

Lock in the financial invariants on the service layer (real logic, not HTML):
income/expense/transfer, credit-card liabilities, refunds, savings, debt
payments, and the credit-card-payment path (a TRANSFER to a credit-card
account - the correct way to pay down a liability without touching
income/expense).
"""
from datetime import date

from app.models.models import (
    Account, AccountType, Category, Debt, DebtType, SavingsGoal, TransactionType,
)
from app.services.finance import (
    create_transaction, expense_between, income_between,
)
from app.services import debts as debts_service, savings as savings_service

from tests.conftest import default_user_id, get_test_db  # noqa: E402


def _cat(name, tx_type):
    db = get_test_db()
    c = db.query(Category).filter(
        Category.name == name, Category.type == tx_type).first()
    db.close()
    return c.id


def _new_account(name, type_, balance=0) -> int:
    db = get_test_db()
    a = Account(user_id=default_user_id(), name=name, type=type_,
                initial_balance=balance, current_balance=balance)
    db.add(a)
    db.commit()
    db.refresh(a)
    aid = a.id
    db.close()
    return aid


def _balance(account_id):
    db = get_test_db()
    a = db.query(Account).filter(Account.id == account_id).first()
    bal = a.current_balance
    db.close()
    return bal


# ==================== INCOME / EXPENSE ====================


def test_income_increases_balance_and_income_report():
    uid = default_user_id()
    acc = _new_account("IncBank", AccountType.BANK, 0)
    cat = _cat("Gaji", TransactionType.INCOME)
    db = get_test_db()
    create_transaction(db, user_id=uid, type=TransactionType.INCOME,
                       amount=1_000_000, account_id=acc, category_id=cat,
                       date_val=date.today(), description="salary")
    db.close()
    assert _balance(acc) == 1_000_000
    assert income_between(get_test_db(), date.today(), date.today(), uid) == 1_000_000


def test_expense_decreases_balance_and_increases_expense_report():
    uid = default_user_id()
    acc = _new_account("ExpBank", AccountType.BANK, 1_000_000)
    cat = _cat("Makan & Minum", TransactionType.EXPENSE)
    db = get_test_db()
    create_transaction(db, user_id=uid, type=TransactionType.EXPENSE,
                       amount=350_000, account_id=acc, category_id=cat,
                       date_val=date.today(), description="groceries")
    db.close()
    assert _balance(acc) == 650_000
    assert expense_between(get_test_db(), date.today(), date.today(), uid) == 350_000


# ==================== TRANSFER ====================


def test_transfer_source_minus_dest_plus_income_expense_unchanged():
    uid = default_user_id()
    src = _new_account("TfSrc", AccountType.BANK, 500_000)
    dst = _new_account("TfDst", AccountType.E_WALLET, 0)
    db = get_test_db()
    create_transaction(db, user_id=uid, type=TransactionType.TRANSFER,
                       amount=200_000, account_id=src, category_id=None,
                       date_val=date.today(), description="move",
                       transfer_to_account_id=dst)
    db.close()
    assert _balance(src) == 300_000
    assert _balance(dst) == 200_000
    assert income_between(get_test_db(), date.today(), date.today(), uid) == 0
    assert expense_between(get_test_db(), date.today(), date.today(), uid) == 0

# ==================== CREDIT CARD ====================


def test_credit_card_purchase_increases_liability_not_cash():
    uid = default_user_id()
    cc = _new_account("Visa", AccountType.CREDIT_CARD, 0)
    cash = _new_account("CashX", AccountType.CASH, 1_000_000)
    cat = _cat("Belanja", TransactionType.EXPENSE)
    cash_before = _balance(cash)
    db = get_test_db()
    create_transaction(db, user_id=uid, type=TransactionType.EXPENSE,
                       amount=300_000, account_id=cc, category_id=cat,
                       date_val=date.today(), description="card purchase")
    db.close()
    assert _balance(cc) == -300_000      # liability grows
    assert _balance(cash) == cash_before  # cash untouched


def test_credit_card_payment_decreases_cash_and_liability_not_expense():
    """Paying a credit card = TRANSFER from cash to the card account."""
    uid = default_user_id()
    cc = _new_account("Visa2", AccountType.CREDIT_CARD, -300_000)
    cash = _new_account("CashY", AccountType.CASH, 1_000_000)
    db = get_test_db()
    create_transaction(db, user_id=uid, type=TransactionType.TRANSFER,
                       amount=300_000, account_id=cash, category_id=None,
                       date_val=date.today(), description="pay cc",
                       transfer_to_account_id=cc)
    db.close()
    assert _balance(cash) == 700_000     # cash decreased
    assert _balance(cc) == 0             # liability reduced to zero
    assert income_between(get_test_db(), date.today(), date.today(), uid) == 0
    assert expense_between(get_test_db(), date.today(), date.today(), uid) == 0


# ==================== REFUND ====================


def test_refund_reverses_expense_via_income_category():
    uid = default_user_id()
    acc = _new_account("RefundAcct", AccountType.BANK, 100_000)
    cat = _cat("Freelance", TransactionType.INCOME)
    db = get_test_db()
    create_transaction(db, user_id=uid, type=TransactionType.INCOME,
                       amount=25_000, account_id=acc, category_id=cat,
                       date_val=date.today(), description="refund")
    db.close()
    assert _balance(acc) == 125_000


# ==================== DEBT PAYMENT ====================


def test_debt_payment_reduces_balance_not_counted_as_expense():
    """Principal repayment of a payable reduces cash but is NOT an expense."""
    uid = default_user_id()
    cash = _new_account("DebtCash2", AccountType.CASH, 1_000_000)
    db = get_test_db()
    debt = Debt(user_id=uid, type=DebtType.PAYABLE, person_name="Budi",
                principal_amount=500_000, remaining_amount=500_000,
                start_date=date.today())
    db.add(debt)
    db.commit()
    db.refresh(debt)
    debt_id = debt.id
    db.close()
    debts_service.pay_debt(
        get_test_db(), debt_id, uid, amount=200_000, account_id=cash,
        payment_date=date.today())
    assert _balance(cash) == 800_000
    # Principal repayment must NOT inflate expense totals.
    assert expense_between(get_test_db(), date.today(), date.today(), uid) == 0
    # ...nor should the matched collection-type logic treat it as income.
    assert income_between(get_test_db(), date.today(), date.today(), uid) == 0


def test_debt_collection_increases_balance_not_counted_as_income():
    """Collecting a receivable increases cash but is NOT income."""
    uid = default_user_id()
    cash = _new_account("RecvCash", AccountType.CASH, 0)
    db = get_test_db()
    debt = Debt(user_id=uid, type=DebtType.RECEIVABLE, person_name="Citra",
                principal_amount=300_000, remaining_amount=300_000,
                start_date=date.today())
    db.add(debt)
    db.commit()
    db.refresh(debt)
    debt_id = debt.id
    db.close()
    debts_service.pay_debt(
        get_test_db(), debt_id, uid, amount=300_000, account_id=cash,
        payment_date=date.today())
    assert _balance(cash) == 300_000
    assert income_between(get_test_db(), date.today(), date.today(), uid) == 0
    assert expense_between(get_test_db(), date.today(), date.today(), uid) == 0


# ==================== CREDIT CARD REFUND ====================


def test_credit_card_refund_reduces_liability_not_income():
    """Refunding a card charge reduces the card liability; not counted as income."""
    uid = default_user_id()
    cc = _new_account("RefundCC", AccountType.CREDIT_CARD, 0)
    cat = _cat("Belanja", TransactionType.EXPENSE)
    db = get_test_db()
    create_transaction(db, user_id=uid, type=TransactionType.EXPENSE,
                      amount=300_000, account_id=cc, category_id=cat,
                      date_val=date.today(), description="purchase")
    db.close()
    assert _balance(cc) == -300_000
    from app.services import credit_card as cc_service
    cc_service.credit_card_refund(
        get_test_db(), user_id=uid, account_id=cc, amount=300_000,
        date_val=date.today(), description="refund")
    assert _balance(cc) == 0
    # Refund must not be counted as income.
    assert income_between(get_test_db(), date.today(), date.today(), uid) == 0


# ==================== FUEL VALIDATION ====================


def test_fuel_quantity_and_price_validation():
    uid = default_user_id()
    acc = _new_account("FuelAcc", AccountType.BANK, 1_000_000)
    cat = _cat("BBM", TransactionType.EXPENSE)
    db = get_test_db()
    # Invalid: quantity <= 0
    try:
        create_transaction(db, user_id=uid, type=TransactionType.EXPENSE,
                          amount=100_000, account_id=acc, category_id=cat,
                          date_val=date.today(), description="bad fuel",
                          quantity_liters=0.0, price_per_liter=10000)
        assert False, "expected ValueError for non-positive quantity"
    except ValueError:
        pass
    # Invalid: negative price
    try:
        create_transaction(db, user_id=uid, type=TransactionType.EXPENSE,
                          amount=100_000, account_id=acc, category_id=cat,
                          date_val=date.today(), description="bad fuel",
                          quantity_liters=5.0, price_per_liter=-1)
        assert False, "expected ValueError for negative price"
    except ValueError:
        pass
    # Valid: positive quantity + non-negative price
    create_transaction(db, user_id=uid, type=TransactionType.EXPENSE,
                      amount=100_000, account_id=acc, category_id=cat,
                      date_val=date.today(), description="ok fuel",
                      quantity_liters=5.0, price_per_liter=10000)
    db.commit()
    db.close()


# ==================== SAVINGS CONTRIBUTION ====================


def test_savings_deposit_not_expense():
    uid = default_user_id()
    db = get_test_db()
    goal = SavingsGoal(user_id=uid, name="Mobil", target_amount=30_000_000,
                       current_amount=0)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    gid = goal.id
    db.close()
    savings_service.deposit(get_test_db(), gid, user_id=uid, amount=5_000_000)
    db_ = get_test_db()
    goal = db_.query(SavingsGoal).filter(SavingsGoal.id == gid).first()
    bal = goal.current_amount
    db_.close()
    assert bal == 5_000_000
    assert expense_between(get_test_db(), date.today(), date.today(), uid) == 0

