"""Credit card hardening tests — Commit B Phase 3 (overpayment) + Phase 4 (over-limit).

Phase 3: TRANSFER payment to a CC account with amount > outstanding liability
         must be rejected with deterministic ValueError.
Phase 4: EXPENSE on a CC account with credit_limit set and amount > available
         credit must be rejected with deterministic ValueError.
         Available credit = credit_limit - outstanding.
"""
from datetime import date

from app.models.models import (
    Account, AccountType, Category, TransactionType,
)
from app.services.finance import create_transaction
from app.services import accounts as accounts_service

from tests.conftest import default_user_id, get_test_db


def _cat(name, tx_type):
    """Get a category by name and type."""
    db = get_test_db()
    c = db.query(Category).filter(
        Category.name == name, Category.type == tx_type).first()
    db.close()
    return c.id


def _new_account(name, type_, balance=0, **cc_fields) -> int:
    """Create a test account."""
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


def _get_balance(account_id) -> int:
    """Get current balance of an account."""
    db = get_test_db()
    a = db.query(Account).filter(Account.id == account_id).first()
    db.close()
    return a.current_balance if a else None


def test_A_cc_charge_reduces_balance_by_increasing_liability():
    """EXPENSE on CREDIT_CARD increases liability (negative balance)."""
    db = get_test_db()
    uid = default_user_id()
    
    cc_id = _new_account("TestCC", AccountType.CREDIT_CARD, balance=0)
    exp_cat_id = _cat("Makan & Minum", TransactionType.EXPENSE)
    
    # Charge 100k
    tx = create_transaction(
        db=db, user_id=uid, type=TransactionType.EXPENSE, amount=100_000,
        account_id=cc_id, category_id=exp_cat_id, date_val=date.today(),
        description="Test charge"
    )
    tx_amount = tx.amount
    db.close()
    
    # Balance should be -100k (liability)
    assert _get_balance(cc_id) == -100_000
    assert tx_amount == 100_000


def test_B_cc_payment_reduces_liability():
    """TRANSFER to CREDIT_CARD decreases liability (balance moves toward zero)."""
    db = get_test_db()
    uid = default_user_id()
    
    bank_id = _new_account("TestBank", AccountType.BANK, balance=500_000)
    cc_id = _new_account("TestCC", AccountType.CREDIT_CARD, balance=-100_000)
    
    # Pay 50k from bank to CC
    tx = create_transaction(
        db=db, user_id=uid, type=TransactionType.TRANSFER, amount=50_000,
        account_id=bank_id, category_id=None, date_val=date.today(),
        transfer_to_account_id=cc_id, description="CC payment"
    )
    db.close()
    
    # CC balance should be -50k (paid down from -100k)
    assert _get_balance(cc_id) == -50_000
    # Bank balance should be 450k
    assert _get_balance(bank_id) == 450_000


def test_C_cc_payment_equal_to_outstanding_clears_balance():
    """TRANSFER to CREDIT_CARD with amount == outstanding => balance = 0."""
    db = get_test_db()
    uid = default_user_id()
    
    bank_id = _new_account("TestBank", AccountType.BANK, balance=300_000)
    cc_id = _new_account("TestCC", AccountType.CREDIT_CARD, balance=-300_000)
    
    # Pay exactly outstanding amount (300k)
    tx = create_transaction(
        db=db, user_id=uid, type=TransactionType.TRANSFER, amount=300_000,
        account_id=bank_id, category_id=None, date_val=date.today(),
        transfer_to_account_id=cc_id, description="Full payment"
    )
    db.close()
    
    # CC balance should be 0
    assert _get_balance(cc_id) == 0


def test_D_cc_payment_overpay_rejected_with_valueerror():
    """TRANSFER to CREDIT_CARD with amount > outstanding raises ValueError (Phase 3)."""
    db = get_test_db()
    uid = default_user_id()
    
    bank_id = _new_account("TestBank", AccountType.BANK, balance=500_000)
    cc_id = _new_account("TestCC", AccountType.CREDIT_CARD, balance=-200_000)
    
    # Try to pay 250k when only 200k outstanding
    try:
        tx = create_transaction(
            db=db, user_id=uid, type=TransactionType.TRANSFER, amount=250_000,
            account_id=bank_id, category_id=None, date_val=date.today(),
            transfer_to_account_id=cc_id, description="Overpay attempt"
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "exceeds outstanding" in str(e)
        assert "200" in str(e) or "200000" in str(e)
    finally:
        db.close()


def test_E_cc_charge_without_credit_limit_allowed():
    """EXPENSE on CREDIT_CARD without credit_limit set is always allowed."""
    db = get_test_db()
    uid = default_user_id()
    
    # CC with NO credit_limit
    cc_id = _new_account("TestCC", AccountType.CREDIT_CARD, balance=0,
                         credit_limit=None)
    exp_cat_id = _cat("Makan & Minum", TransactionType.EXPENSE)
    
    # Charge 1M without limit
    tx = create_transaction(
        db=db, user_id=uid, type=TransactionType.EXPENSE, amount=1_000_000,
        account_id=cc_id, category_id=exp_cat_id, date_val=date.today(),
        description="Large charge, no limit"
    )
    db.close()
    
    # Should succeed, balance is -1M
    assert _get_balance(cc_id) == -1_000_000


def test_F_cc_charge_within_available_credit_allowed():
    """EXPENSE on CREDIT_CARD with amount <= available_credit succeeds (Phase 4)."""
    db = get_test_db()
    uid = default_user_id()
    
    # CC with 1M limit, no outstanding
    cc_id = _new_account("TestCC", AccountType.CREDIT_CARD, balance=0,
                         credit_limit=1_000_000)
    exp_cat_id = _cat("Makan & Minum", TransactionType.EXPENSE)
    
    # Charge 500k (< available 1M)
    tx = create_transaction(
        db=db, user_id=uid, type=TransactionType.EXPENSE, amount=500_000,
        account_id=cc_id, category_id=exp_cat_id, date_val=date.today(),
        description="Within limit"
    )
    db.close()
    
    # Should succeed, balance is -500k
    assert _get_balance(cc_id) == -500_000


def test_G_cc_charge_equal_to_available_credit_allowed():
    """EXPENSE on CREDIT_CARD with amount == available_credit succeeds."""
    db = get_test_db()
    uid = default_user_id()
    
    # CC with 1M limit, no outstanding
    cc_id = _new_account("TestCC", AccountType.CREDIT_CARD, balance=0,
                         credit_limit=1_000_000)
    exp_cat_id = _cat("Makan & Minum", TransactionType.EXPENSE)
    
    # Charge exactly 1M (= available)
    tx = create_transaction(
        db=db, user_id=uid, type=TransactionType.EXPENSE, amount=1_000_000,
        account_id=cc_id, category_id=exp_cat_id, date_val=date.today(),
        description="Max charge"
    )
    db.close()
    
    # Should succeed, balance is -1M
    assert _get_balance(cc_id) == -1_000_000


def test_H_cc_charge_exceeds_available_credit_rejected():
    """EXPENSE on CREDIT_CARD with amount > available_credit raises ValueError (Phase 4)."""
    db = get_test_db()
    uid = default_user_id()
    
    # CC with 1M limit, no outstanding
    cc_id = _new_account("TestCC", AccountType.CREDIT_CARD, balance=0,
                         credit_limit=1_000_000)
    exp_cat_id = _cat("Makan & Minum", TransactionType.EXPENSE)
    
    # Try to charge 1.1M (> available 1M)
    try:
        tx = create_transaction(
            db=db, user_id=uid, type=TransactionType.EXPENSE, amount=1_100_000,
            account_id=cc_id, category_id=exp_cat_id, date_val=date.today(),
            description="Over limit"
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "exceeds available credit" in str(e)
        assert "1000000" in str(e) or "1M" in str(e)
    finally:
        db.close()


def test_I_cc_charge_exceeds_remaining_credit_after_partial_outstanding():
    """EXPENSE on CREDIT_CARD: available = limit - outstanding, reduce by existing debt."""
    db = get_test_db()
    uid = default_user_id()
    
    # CC with 1M limit, already owe 300k
    cc_id = _new_account("TestCC", AccountType.CREDIT_CARD, balance=-300_000,
                         credit_limit=1_000_000)
    exp_cat_id = _cat("Makan & Minum", TransactionType.EXPENSE)
    
    # Available = 1M - 300k = 700k
    # Try to charge 750k (> 700k available)
    try:
        tx = create_transaction(
            db=db, user_id=uid, type=TransactionType.EXPENSE, amount=750_000,
            account_id=cc_id, category_id=exp_cat_id, date_val=date.today(),
            description="Partial debt + new"
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "exceeds available credit" in str(e)
        assert "700" in str(e) or "700000" in str(e)
    finally:
        db.close()


def test_J_cc_charge_within_remaining_credit_after_partial_outstanding():
    """EXPENSE allowed when amount <= (limit - outstanding)."""
    db = get_test_db()
    uid = default_user_id()
    
    # CC with 1M limit, already owe 300k
    cc_id = _new_account("TestCC", AccountType.CREDIT_CARD, balance=-300_000,
                         credit_limit=1_000_000)
    exp_cat_id = _cat("Makan & Minum", TransactionType.EXPENSE)
    
    # Available = 1M - 300k = 700k
    # Charge 600k (< 700k available)
    tx = create_transaction(
        db=db, user_id=uid, type=TransactionType.EXPENSE, amount=600_000,
        account_id=cc_id, category_id=exp_cat_id, date_val=date.today(),
        description="Partial debt + new"
    )
    db.close()
    
    # Should succeed, balance is -(300k + 600k) = -900k
    assert _get_balance(cc_id) == -900_000


def test_K_get_available_credit_for_non_cc_returns_none():
    """get_available_credit returns None for non-CREDIT_CARD accounts."""
    bank_id = _new_account("TestBank", AccountType.BANK, balance=500_000)
    
    db = get_test_db()
    acc = db.query(Account).filter(Account.id == bank_id).first()
    db.close()
    
    avail = accounts_service.get_available_credit(acc)
    assert avail is None


def test_L_get_available_credit_for_cc_without_limit_returns_none():
    """get_available_credit returns None for CREDIT_CARD without credit_limit."""
    cc_id = _new_account("TestCC", AccountType.CREDIT_CARD, balance=0,
                         credit_limit=None)
    
    db = get_test_db()
    acc = db.query(Account).filter(Account.id == cc_id).first()
    db.close()
    
    avail = accounts_service.get_available_credit(acc)
    assert avail is None


def test_M_get_available_credit_calculates_correctly():
    """get_available_credit returns limit - outstanding (canonical calc)."""
    # CC: 1M limit, owe 300k => available = 700k
    cc_id = _new_account("TestCC", AccountType.CREDIT_CARD, balance=-300_000,
                         credit_limit=1_000_000)
    
    db = get_test_db()
    acc = db.query(Account).filter(Account.id == cc_id).first()
    db.close()
    
    avail = accounts_service.get_available_credit(acc)
    assert avail == 700_000


# ==================== REFUND MATRIX (Commit C / Phase 5) ====================
from app.services import credit_card as cc_service


def test_N_refund_partial_reduces_liability():
    """Partial refund reduces outstanding liability; available credit reflects it."""
    uid = default_user_id()
    cc_id = _new_account("RefundCC", AccountType.CREDIT_CARD, balance=0)
    db = get_test_db()
    create_transaction(
        db, user_id=uid, type=TransactionType.EXPENSE, amount=1_000_000,
        account_id=cc_id, category_id=_cat("Belanja", TransactionType.EXPENSE),
        date_val=date.today(), description="purchase",
    )
    db.close()
    assert _get_balance(cc_id) == -1_000_000

    db = get_test_db()
    db.query(Account).filter(Account.id == cc_id).update(
        {"credit_limit": 10_000_000})
    db.commit()
    db.close()

    cc_service.credit_card_refund(
        get_test_db(), user_id=uid, account_id=cc_id, amount=250_000,
        date_val=date.today(), description="partial refund")

    assert _get_balance(cc_id) == -750_000

    db = get_test_db()
    acc = db.query(Account).filter(Account.id == cc_id).first()
    avail = accounts_service.get_available_credit(acc)
    db.close()
    assert avail == 9_250_000  # 10M limit - 750k outstanding


def test_O_refund_full_zeroes_outstanding():
    """Full refund brings outstanding to 0 (no positive credit balance)."""
    uid = default_user_id()
    cc_id = _new_account("RefundCC", AccountType.CREDIT_CARD, balance=0)
    db = get_test_db()
    create_transaction(
        db, user_id=uid, type=TransactionType.EXPENSE, amount=500_000,
        account_id=cc_id, category_id=_cat("Belanja", TransactionType.EXPENSE),
        date_val=date.today(), description="purchase",
    )
    db.close()
    assert _get_balance(cc_id) == -500_000

    cc_service.credit_card_refund(
        get_test_db(), user_id=uid, account_id=cc_id, amount=500_000,
        date_val=date.today(), description="full refund")

    assert _get_balance(cc_id) == 0


def test_P_refund_exceeds_outstanding_rejected():
    """Refund > outstanding liability rejected; no positive credit balance."""
    uid = default_user_id()
    cc_id = _new_account("RefundCC", AccountType.CREDIT_CARD, balance=-300_000)
    try:
        cc_service.credit_card_refund(
            get_test_db(), user_id=uid, account_id=cc_id, amount=500_000,
            date_val=date.today(), description="over refund")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "exceeds outstanding liability" in str(e)
    finally:
        assert _get_balance(cc_id) == -300_000  # unchanged


def test_Q_refund_not_counted_as_income():
    """REFUND reduces liability; must NOT appear in income reports."""
    uid = default_user_id()
    cc_id = _new_account("RefundCC", AccountType.CREDIT_CARD, balance=-200_000)
    cc_service.credit_card_refund(
        get_test_db(), user_id=uid, account_id=cc_id, amount=200_000,
        date_val=date.today(), description="refund")

    from app.services.finance import income_between
    assert income_between(get_test_db(), date.today(), date.today(), uid) == 0
    assert _get_balance(cc_id) == 0


def test_R_refund_wrong_user_rejected():
    """User B cannot refund User A's credit card."""
    from app.models.models import User
    uid = default_user_id()
    cc_id = _new_account("RefundCC", AccountType.CREDIT_CARD, balance=-200_000)

    db = get_test_db()
    other = db.query(User).filter(User.username == "alice").first().id
    db.close()

    try:
        cc_service.credit_card_refund(
            get_test_db(), user_id=other, account_id=cc_id, amount=100_000,
            date_val=date.today(), description="IDOR refund")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    finally:
        assert _get_balance(cc_id) == -200_000  # unchanged


# ==================== END-TO-END SCENARIO (Commit C / Phase 13) ====================
def test_S_purchase_payment_refund_reporting_invariants():
    """Full CC lifecycle: charge -> partial pay -> refund, reconciles everything.

    Verifies the accounting invariant end-to-end (Phase 13): available credit,
    balance, and expense/income reports all agree with the outstanding
    liability across a purchase, a payment (TRANSFER), and a refund.
    """
    from app.services.finance import expense_between, income_between

    uid = default_user_id()
    cc_id = _new_account("ScenarioCC", AccountType.CREDIT_CARD, balance=0,
                         credit_limit=10_000_000)
    bank_id = _new_account("ScenarioBank", AccountType.BANK, balance=5_000_000)
    exp_cat = _cat("Belanja", TransactionType.EXPENSE)

    # 1. Charge Rp 1,000,000
    db = get_test_db()
    create_transaction(
        db, user_id=uid, type=TransactionType.EXPENSE, amount=1_000_000,
        account_id=cc_id, category_id=exp_cat, date_val=date.today(),
        description="laptop")
    db.close()
    assert _get_balance(cc_id) == -1_000_000
    assert _get_balance(bank_id) == 5_000_000  # cash untouched by CC charge

    # 2. Pay Rp 400,000 from bank to CC (TRANSFER)
    db = get_test_db()
    create_transaction(
        db, user_id=uid, type=TransactionType.TRANSFER, amount=400_000,
        account_id=bank_id, category_id=None, date_val=date.today(),
        transfer_to_account_id=cc_id, description="cc payment")
    db.close()
    assert _get_balance(cc_id) == -600_000   # 1M liability - 400k paid
    assert _get_balance(bank_id) == 4_600_000

    # 3. Refund Rp 300,000 on the card
    cc_service.credit_card_refund(
        get_test_db(), user_id=uid, account_id=cc_id, amount=300_000,
        date_val=date.today(), description="item refund")
    assert _get_balance(cc_id) == -300_000  # remaining outstanding

    # Available credit = 10M limit - 300k outstanding
    db = get_test_db()
    acc = db.query(Account).filter(Account.id == cc_id).first()
    avail = accounts_service.get_available_credit(acc)
    db.close()
    assert avail == 9_700_000

    # Reporting invariants: the charge (1M) is expense; payment & refund are
    # NOT income. Expense report = 1M, income report = 0.
    assert expense_between(get_test_db(), date.today(), date.today(), uid) == 1_000_000
    assert income_between(get_test_db(), date.today(), date.today(), uid) == 0


def test_T_mid_cycle_charge_respects_reduced_available_credit():
    """After purchase+refund, a new charge is bounded by remaining available credit."""
    uid = default_user_id()
    cc_id = _new_account("CycleCC", AccountType.CREDIT_CARD, balance=-1_000_000,
                         credit_limit=5_000_000)
    exp_cat = _cat("Makan & Minum", TransactionType.EXPENSE)

    # Available before refund = 5M - 1M = 4M. Charge 2M OK.
    db = get_test_db()
    create_transaction(
        db, user_id=uid, type=TransactionType.EXPENSE, amount=2_000_000,
        account_id=cc_id, category_id=exp_cat, date_val=date.today(),
        description="charge")
    db.close()
    assert _get_balance(cc_id) == -3_000_000

    # Refund 2M -> outstanding 1M -> available 4M
    cc_service.credit_card_refund(
        get_test_db(), user_id=uid, account_id=cc_id, amount=2_000_000,
        date_val=date.today(), description="refund")
    assert _get_balance(cc_id) == -1_000_000

    db = get_test_db()
    acc = db.query(Account).filter(Account.id == cc_id).first()
    avail = accounts_service.get_available_credit(acc)
    db.close()
    assert avail == 4_000_000

    # Charge exceeding available (5M) must be rejected.
    try:
        db = get_test_db()
        create_transaction(
            db, user_id=uid, type=TransactionType.EXPENSE, amount=5_000_000,
            account_id=cc_id, category_id=exp_cat, date_val=date.today(),
            description="over limit")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "exceeds available credit" in str(e)
    finally:
        assert _get_balance(cc_id) == -1_000_000



