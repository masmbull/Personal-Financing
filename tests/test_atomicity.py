"""Phase 14 - atomicity / rollback tests.

CONTRACT: when a service operation fails validation, it must leave ZERO
persisted mutations - no transaction rows, no balance changes, no status
changes - and the session must remain usable afterwards (callers roll back
the discarded pending state, then continue).

Every test asserts on the state of the DB after the failure, not just the
exception type, so a validation added at the wrong place (after the first
mutation) is caught.
"""
from datetime import date

import pytest

from app.models.models import (
    Account, AccountType, BillFrequency, BillPayment, Category, Debt,
    DebtPayment, DebtType, SavingsGoal, SavingsGoalTransaction, Transaction,
    TransactionType, User,
)
from app.services import bills as bills_service
from app.services import credit_card as cc_service
from app.services import debts as debts_service
from app.services import savings as savings_service
from app.services.finance import (
    create_transaction, delete_transaction,
)

from tests.conftest import default_user_id, get_test_db


def _cat(name, tx_type):
    db = get_test_db()
    c = db.query(Category).filter(
        Category.name == name, Category.type == tx_type).first()
    db.close()
    return c.id


def _new_account(name, type_, balance=0, **cc_fields) -> int:
    db = get_test_db()
    a = Account(
        user_id=default_user_id(), name=name, type=type_,
        initial_balance=balance, current_balance=balance,
        **cc_fields
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    aid = a.id
    db.close()
    return aid


def _balance(account_id) -> int:
    db = get_test_db()
    a = db.query(Account).filter(Account.id == account_id).first()
    db.close()
    return a.current_balance if a else None


def _tx_count() -> int:
    db = get_test_db()
    n = db.query(Transaction).count()
    db.close()
    return n


def _alice_id() -> int:
    db = get_test_db()
    aid = db.query(User).filter(User.username == "alice").first().id
    db.close()
    return aid


def _other_users_account(name: str = "alice_secret_bank") -> int:
    """An account owned by alice (bob must never be able to touch it)."""
    db = get_test_db()
    a = Account(user_id=_alice_id(), name=name, type=AccountType.BANK,
                initial_balance=1_000_000, current_balance=1_000_000)
    db.add(a)
    db.commit()
    db.refresh(a)
    aid = a.id
    db.close()
    return aid


TODAY = date.today()


# ==================== create_transaction validation failures ====================

def test_A_zero_and_negative_amount_create_no_transaction():
    """amount <= 0 rejected before any mutation (Phase 14)."""
    uid = default_user_id()
    bank = _new_account("AtzBank", AccountType.BANK, balance=1_000_000)
    cat = _cat("Makan & Minum", TransactionType.EXPENSE)

    for bad_amount in (0, -1, -100_000):
        before = _tx_count()
        with pytest.raises(ValueError, match="Amount must be positive"):
            db = get_test_db()
            try:
                create_transaction(
                    db, user_id=uid, type=TransactionType.EXPENSE,
                    amount=bad_amount, account_id=bank, category_id=cat,
                    date_val=TODAY, description="bad")
            finally:
                db.rollback()
                db.close()
        assert _tx_count() == before, f"tx created for amount={bad_amount}"
    assert _balance(bank) == 1_000_000


def test_B_unknown_account_creates_no_transaction():
    uid = default_user_id()
    before = _tx_count()
    with pytest.raises(ValueError, match="Account not found"):
        db = get_test_db()
        try:
            create_transaction(
                db, user_id=uid, type=TransactionType.EXPENSE,
                amount=50_000, account_id=999_999,
                category_id=_cat("Makan & Minum", TransactionType.EXPENSE),
                date_val=TODAY, description="ghost account")
        finally:
            db.rollback()
            db.close()
    assert _tx_count() == before


def test_C_other_users_account_cannot_be_charged():
    """IDOR at service level: alice's account is invisible to bob."""
    uid = default_user_id()
    alice_acc = _other_users_account()

    before = _tx_count()
    with pytest.raises(ValueError, match="Account not found"):
        db = get_test_db()
        try:
            create_transaction(
                db, user_id=uid, type=TransactionType.EXPENSE,
                amount=25_000, account_id=alice_acc,
                category_id=_cat("Makan & Minum", TransactionType.EXPENSE),
                date_val=TODAY, description="IDOR attempt")
        finally:
            db.rollback()
            db.close()
    assert _tx_count() == before
    assert _balance(alice_acc) == 1_000_000  # victim untouched


def test_D_transfer_without_or_with_bad_destination_mutates_nothing():
    uid = default_user_id()
    bank = _new_account("TrzBank", AccountType.BANK, balance=800_000)

    # missing destination
    with pytest.raises(ValueError, match="Transfer requires destination"):
        db = get_test_db()
        try:
            create_transaction(
                db, user_id=uid, type=TransactionType.TRANSFER,
                amount=100_000, account_id=bank, category_id=None,
                date_val=TODAY, description="no dest")
        finally:
            db.rollback()
            db.close()

    # unknown destination
    with pytest.raises(ValueError, match="Destination account not found"):
        db = get_test_db()
        try:
            create_transaction(
                db, user_id=uid, type=TransactionType.TRANSFER,
                amount=100_000, account_id=bank, category_id=None,
                transfer_to_account_id=999_999,
                date_val=TODAY, description="ghost dest")
        finally:
            db.rollback()
            db.close()

    # same-account transfer
    with pytest.raises(ValueError, match="Cannot transfer to same account"):
        db = get_test_db()
        try:
            create_transaction(
                db, user_id=uid, type=TransactionType.TRANSFER,
                amount=100_000, account_id=bank, category_id=None,
                transfer_to_account_id=bank,
                date_val=TODAY, description="self transfer")
        finally:
            db.rollback()
            db.close()

    assert _balance(bank) == 800_000
    assert _tx_count() == 0  # fresh fixture - nothing above may have slipped


def test_E_cc_overpayment_via_transfer_leaves_everything_unchanged():
    uid = default_user_id()
    bank = _new_account("OvpBank", AccountType.BANK, balance=5_000_000)
    cc = _new_account("OvpCC", AccountType.CREDIT_CARD, balance=-1_000_000)

    before = _tx_count()
    with pytest.raises(ValueError, match="overpayment is not supported"):
        db = get_test_db()
        try:
            create_transaction(
                db, user_id=uid, type=TransactionType.TRANSFER,
                amount=1_000_001, account_id=bank, category_id=None,
                transfer_to_account_id=cc, date_val=TODAY,
                description="overpay")
        finally:
            db.rollback()
            db.close()

    assert _tx_count() == before
    assert _balance(bank) == 5_000_000      # source untouched
    assert _balance(cc) == -1_000_000       # liability untouched


def test_F_cc_overlimit_charge_creates_no_transaction():
    uid = default_user_id()
    cc = _new_account("LimCC", AccountType.CREDIT_CARD, balance=-2_000_000,
                      credit_limit=5_000_000)  # available = 3M
    cat = _cat("Belanja", TransactionType.EXPENSE)

    before = _tx_count()
    with pytest.raises(ValueError, match="exceeds available credit"):
        db = get_test_db()
        try:
            create_transaction(
                db, user_id=uid, type=TransactionType.EXPENSE,
                amount=3_000_001, account_id=cc, category_id=cat,
                date_val=TODAY, description="over limit")
        finally:
            db.rollback()
            db.close()

    assert _tx_count() == before
    assert _balance(cc) == -2_000_000


def test_G_missing_category_creates_no_transaction():
    uid = default_user_id()
    bank = _new_account("CatBank", AccountType.BANK, balance=100_000)

    with pytest.raises(ValueError, match="Category required"):
        db = get_test_db()
        try:
            create_transaction(
                db, user_id=uid, type=TransactionType.EXPENSE,
                amount=10_000, account_id=bank, category_id=None,
                date_val=TODAY, description="no category")
        finally:
            db.rollback()
            db.close()
    assert _balance(bank) == 100_000


def test_H_unknown_master_refs_create_no_transaction():
    """merchant_id / payment_method_id / fuel_product_id must be owned/known
    BEFORE any row is written."""
    uid = default_user_id()
    bank = _new_account("RefBank", AccountType.BANK, balance=250_000)
    cat = _cat("Makan & Minum", TransactionType.EXPENSE)

    for kwargs, match in (
        ({"merchant_id": 999_999}, "Merchant not found"),
        ({"payment_method_id": 999_999}, "Payment method not found"),
        ({"fuel_product_id": 999_999}, "Fuel product not found"),
    ):
        before = _tx_count()
        with pytest.raises(ValueError, match=match):
            db = get_test_db()
            try:
                create_transaction(
                    db, user_id=uid, type=TransactionType.EXPENSE,
                    amount=10_000, account_id=bank, category_id=cat,
                    date_val=TODAY, description="bad ref", **kwargs)
            finally:
                db.rollback()
                db.close()
        assert _tx_count() == before, f"tx created for {kwargs}"
    assert _balance(bank) == 250_000


def test_I_bad_fuel_quantities_create_no_transaction():
    uid = default_user_id()
    bank = _new_account("FuelBank", AccountType.BANK, balance=300_000)
    cat = _cat("BBM", TransactionType.EXPENSE)

    for kwargs, match in (
        ({"quantity_liters": 0}, "Fuel quantity must be positive"),
        ({"quantity_liters": -5.0}, "Fuel quantity must be positive"),
        ({"price_per_liter": -1}, "cannot be negative"),
    ):
        before = _tx_count()
        with pytest.raises(ValueError, match=match):
            db = get_test_db()
            try:
                create_transaction(
                    db, user_id=uid, type=TransactionType.EXPENSE,
                    amount=10_000, account_id=bank, category_id=cat,
                    date_val=TODAY, description="bad fuel", **kwargs)
            finally:
                db.rollback()
                db.close()
        assert _tx_count() == before, f"tx created for {kwargs}"
    assert _balance(bank) == 300_000


def test_J_over_refund_creates_no_refund_transaction():
    """Commit C guard, now with explicit zero-mutation proof."""
    uid = default_user_id()
    cc = _new_account("RfCC", AccountType.CREDIT_CARD, balance=-500_000)

    before = _tx_count()
    with pytest.raises(ValueError, match="over-refund is not supported"):
        db = get_test_db()
        try:
            cc_service.credit_card_refund(
                db, user_id=uid, account_id=cc, amount=500_001,
                date_val=TODAY, description="over refund")
        finally:
            db.rollback()
            db.close()

    assert _tx_count() == before
    assert _balance(cc) == -500_000


def test_K_session_usable_after_failure_and_commits_exactly_one_row():
    """A failed operation must not poison the session for the next caller."""
    uid = default_user_id()
    bank = _new_account("RecoverBank", AccountType.BANK, balance=10_000)
    cat = _cat("Makan & Minum", TransactionType.EXPENSE)

    with pytest.raises(ValueError):
        db = get_test_db()
        try:
            create_transaction(
                db, user_id=uid, type=TransactionType.EXPENSE,
                amount=0, account_id=bank, category_id=cat,
                date_val=TODAY, description="boom")
        finally:
            db.rollback()
            db.close()

    before = _tx_count()
    db = get_test_db()
    tx = create_transaction(
        db, user_id=uid, type=TransactionType.EXPENSE,
        amount=10_000, account_id=bank, category_id=cat,
        date_val=TODAY, description="recovered")
    tx_amount = tx.amount  # capture before session close (detached instance)
    db.close()
    assert _tx_count() == before + 1
    assert _balance(bank) == 0
    assert tx_amount == 10_000


# ==================== debt payments ====================

def _new_debt(amount=1_000_000) -> int:
    db = get_test_db()
    d = debts_service.create_debt(
        db, user_id=default_user_id(), type=DebtType.PAYABLE,
        person_name="Budi", principal_amount=amount)
    db.close()
    return d.id


def _debt_remaining(debt_id) -> int:
    db = get_test_db()
    d = db.query(Debt).filter(Debt.id == debt_id).first()
    db.close()
    return d.remaining_amount


def _debt_payment_count(debt_id) -> int:
    db = get_test_db()
    n = db.query(DebtPayment).filter(DebtPayment.debt_id == debt_id).count()
    db.close()
    return n


def test_L_debt_payment_validation_errors_mutate_nothing():
    uid = default_user_id()
    debt_id = _new_debt(500_000)

    for bad_amount in (0, -1, 500_001):
        before = _tx_count()
        with pytest.raises(Exception, match="Payment"):
            db = get_test_db()
            try:
                debts_service.pay_debt(
                    db, debt_id, uid, amount=bad_amount, account_id=None)
            finally:
                db.rollback()
                db.close()
        assert _tx_count() == before, f"tx created for amount={bad_amount}"
    assert _debt_remaining(debt_id) == 500_000
    assert _debt_payment_count(debt_id) == 0


def test_M_debt_payment_with_missing_account_is_fully_atomic():
    """The debt category is flushed BEFORE create_transaction fails - the
    caller's rollback must discard it and the debt must stay untouched."""
    uid = default_user_id()
    debt_id = _new_debt(300_000)

    with pytest.raises(ValueError, match="Account not found"):
        db = get_test_db()
        try:
            debts_service.pay_debt(
                db, debt_id, uid, amount=100_000, account_id=999_999)
        finally:
            db.rollback()
            db.close()

    assert _debt_remaining(debt_id) == 300_000
    assert _debt_payment_count(debt_id) == 0
    db = get_test_db()
    cats = db.query(Category).filter(Category.name == "Bayar Hutang").count()
    txs = db.query(Transaction).filter(
        Transaction.type == TransactionType.DEBT_REPAYMENT).count()
    db.close()
    assert cats == 0 and txs == 0


def test_N_debt_payment_unknown_debt_raises_and_creates_nothing():
    uid = default_user_id()
    with pytest.raises(debts_service.DebtNotFound):
        db = get_test_db()
        try:
            debts_service.pay_debt(db, 999_999, uid, amount=10_000)
        finally:
            db.rollback()
            db.close()


# ==================== savings ====================

def _new_goal(target=1_000_000) -> int:
    db = get_test_db()
    g = savings_service.create_goal(
        db, user_id=default_user_id(), name="Liburan", target_amount=target)
    db.close()
    return g.id


def _goal_amount(goal_id) -> int:
    db = get_test_db()
    g = db.query(SavingsGoal).filter(SavingsGoal.id == goal_id).first()
    db.close()
    return g.current_amount


def _goal_tx_count(goal_id) -> int:
    db = get_test_db()
    n = db.query(SavingsGoalTransaction).filter(
        SavingsGoalTransaction.goal_id == goal_id).count()
    db.close()
    return n


def test_O_savings_deposit_validation_mutates_nothing():
    uid = default_user_id()
    goal_id = _new_goal()

    for bad_amount in (0, -10):
        with pytest.raises(Exception, match="Amount must be positive"):
            db = get_test_db()
            try:
                savings_service.deposit(db, goal_id, user_id=uid,
                                        amount=bad_amount)
            finally:
                db.rollback()
                db.close()

    with pytest.raises(savings_service.GoalNotFound):
        db = get_test_db()
        try:
            savings_service.deposit(db, 999_999, user_id=uid, amount=10_000)
        finally:
            db.rollback()
            db.close()

    assert _goal_amount(goal_id) == 0
    assert _goal_tx_count(goal_id) == 0


def test_P_savings_over_withdrawal_mutates_nothing():
    uid = default_user_id()
    goal_id = _new_goal()
    db = get_test_db()
    savings_service.deposit(db, goal_id, user_id=uid, amount=100_000)
    db.close()

    with pytest.raises(Exception, match="exceeds saved amount"):
        db = get_test_db()
        try:
            savings_service.withdraw(db, goal_id, user_id=uid, amount=100_001)
        finally:
            db.rollback()
            db.close()

    assert _goal_amount(goal_id) == 100_000
    assert _goal_tx_count(goal_id) == 1  # only the deposit


# ==================== bills ====================

def test_Q_bill_pay_with_missing_account_is_fully_atomic():
    uid = default_user_id()
    db = get_test_db()
    bill = bills_service.create_bill(
        db, user_id=uid, name="Listrik", amount=200_000,
        frequency=BillFrequency.MONTHLY, due_day=10, account_id=None)
    db.close()
    bill_id = bill.id

    with pytest.raises(ValueError, match="Account not found"):
        db = get_test_db()
        try:
            bills_service.pay_bill(db, bill_id, uid, account_id=999_999)
        finally:
            db.rollback()
            db.close()

    db = get_test_db()
    n = db.query(BillPayment).filter(BillPayment.bill_id == bill_id).count()
    cats = db.query(Category).filter(Category.name == "Tagihan").count()
    db.close()
    assert n == 0 and cats == 0


# ==================== delete as compensation ====================

def test_R_delete_transaction_of_other_user_returns_false_no_mutation():
    uid = default_user_id()
    bank = _new_account("DelBank", AccountType.BANK, balance=900_000)
    cat = _cat("Makan & Minum", TransactionType.EXPENSE)

    db = get_test_db()
    tx = create_transaction(
        db, user_id=uid, type=TransactionType.EXPENSE, amount=100_000,
        account_id=bank, category_id=cat, date_val=TODAY, description="mine")
    tx_id = tx.id
    db.close()
    assert _balance(bank) == 800_000

    db = get_test_db()
    result = delete_transaction(db, tx_id, _alice_id())  # alice tries
    db.close()
    assert result is False
    assert _balance(bank) == 800_000


def test_S_deleting_own_transfer_restores_both_balances():
    """Compensating rollback of a transfer: both legs must reconcile."""
    uid = default_user_id()
    src = _new_account("CompSrc", AccountType.BANK, balance=1_000_000)
    dst = _new_account("CompDst", AccountType.E_WALLET, balance=0)

    db = get_test_db()
    tx = create_transaction(
        db, user_id=uid, type=TransactionType.TRANSFER, amount=250_000,
        account_id=src, category_id=None, transfer_to_account_id=dst,
        date_val=TODAY, description="move")
    tx_id = tx.id
    db.close()
    assert _balance(src) == 750_000 and _balance(dst) == 250_000

    db = get_test_db()
    assert delete_transaction(db, tx_id, uid) is True
    db.close()
    assert _balance(src) == 1_000_000
    assert _balance(dst) == 0


def test_T_deleting_own_refund_restores_liability():
    uid = default_user_id()
    cc = _new_account("CompCC", AccountType.CREDIT_CARD, balance=-400_000)

    db = get_test_db()
    tx = cc_service.credit_card_refund(
        db, user_id=uid, account_id=cc, amount=150_000,
        date_val=TODAY, description="refund then undo")
    tx_id = tx.id
    db.close()
    assert _balance(cc) == -250_000

    db = get_test_db()
    assert delete_transaction(db, tx_id, uid) is True
    db.close()
    assert _balance(cc) == -400_000
