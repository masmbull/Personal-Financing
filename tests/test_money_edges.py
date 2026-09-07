"""Money edge cases - decimal / integer boundary hardening.

Project invariant: all money is an INTEGER in Rupiah; floats never touch
money math. These tests pin the boundaries:
- smallest positive amount (Rp 1)
- the MAX_TX_AMOUNT cap (deterministic ValueError instead of a raw
  OverflowError escaping from the SQLite DBAPI at flush time)
- fuel quantity as a (float) quantity vs price as (integer) money
- minimum-payment floor computed with pure integer arithmetic
"""
from datetime import date

import pytest

from app.models.models import Account, AccountType, Category, TransactionType
from app.services.credit_card import minimum_payment_from
from app.services.finance import MAX_TX_AMOUNT, create_transaction

from tests.conftest import default_user_id, get_test_db

TODAY = date.today()


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


def test_A_smallest_positive_amount_is_exact():
    """Rp 1 is the smallest meaningful unit - balances must stay exact."""
    uid = default_user_id()
    bank = _new_account("EdgeBank", AccountType.BANK, balance=0)
    exp = _cat("Makan & Minum", TransactionType.EXPENSE)
    inc = _cat("Gaji", TransactionType.INCOME)

    db = get_test_db()
    create_transaction(db, user_id=uid, type=TransactionType.EXPENSE,
                       amount=1, account_id=bank, category_id=exp,
                       date_val=TODAY, description="one rupiah out")
    db.close()
    assert _balance(bank) == -1

    db = get_test_db()
    create_transaction(db, user_id=uid, type=TransactionType.INCOME,
                       amount=1, account_id=bank, category_id=inc,
                       date_val=TODAY, description="one rupiah in")
    db.close()
    assert _balance(bank) == 0


def test_B_amount_just_under_cap_is_accepted():
    """MAX_TX_AMOUNT - 1 flows through with exact integer math."""
    uid = default_user_id()
    bank = _new_account("CapBank", AccountType.BANK, balance=0)
    inc = _cat("Gaji", TransactionType.INCOME)
    big = MAX_TX_AMOUNT - 1

    db = get_test_db()
    create_transaction(db, user_id=uid, type=TransactionType.INCOME,
                       amount=big, account_id=bank, category_id=inc,
                       date_val=TODAY, description="huge but legal")
    db.close()
    assert _balance(bank) == big


def test_C_amount_at_cap_is_accepted_boundary():
    """Boundary: amount == MAX_TX_AMOUNT is allowed (> cap is rejected)."""
    uid = default_user_id()
    bank = _new_account("CapBank2", AccountType.BANK, balance=0)
    inc = _cat("Gaji", TransactionType.INCOME)

    db = get_test_db()
    create_transaction(db, user_id=uid, type=TransactionType.INCOME,
                       amount=MAX_TX_AMOUNT, account_id=bank,
                       category_id=inc, date_val=TODAY, description="cap")
    db.close()
    assert _balance(bank) == MAX_TX_AMOUNT


def test_D_amount_over_cap_rejected_cleanly_no_mutation():
    """Beyond the cap: deterministic ValueError, zero mutation, usable session.

    Without the cap this would surface as a raw OverflowError from
    sqlite3 at flush time ("Python int too large to convert to SQLite
    INTEGER"), leaving the session mid-transaction.
    """
    uid = default_user_id()
    bank = _new_account("CapBank3", AccountType.BANK, balance=500_000)
    inc = _cat("Gaji", TransactionType.INCOME)

    with pytest.raises(ValueError, match="maximum supported"):
        db = get_test_db()
        try:
            create_transaction(db, user_id=uid, type=TransactionType.INCOME,
                               amount=MAX_TX_AMOUNT + 1, account_id=bank,
                               category_id=inc, date_val=TODAY,
                               description="over cap")
        finally:
            db.rollback()
            db.close()

    assert _balance(bank) == 500_000

    # session still usable right after
    db = get_test_db()
    create_transaction(db, user_id=uid, type=TransactionType.INCOME,
                       amount=1_000, account_id=bank, category_id=inc,
                       date_val=TODAY, description="after cap error")
    db.close()
    assert _balance(bank) == 501_000


def test_E_ridiculously_large_amount_rejected_before_any_io():
    """Values beyond the 64-bit boundary can never reach the DBAPI."""
    uid = default_user_id()
    bank = _new_account("OvfBank", AccountType.BANK, balance=0)
    inc = _cat("Gaji", TransactionType.INCOME)

    with pytest.raises(ValueError, match="maximum supported"):
        db = get_test_db()
        try:
            create_transaction(db, user_id=uid, type=TransactionType.INCOME,
                               amount=2 ** 63, account_id=bank,
                               category_id=inc, date_val=TODAY,
                               description="int64 overflow attempt")
        finally:
            db.rollback()
            db.close()
    assert _balance(bank) == 0


def test_F_fuel_quantity_float_vs_price_integer():
    """quantity_liters is a float QUANTITY (never money); price_per_liter is
    integer money and 0 is allowed (promo / redeem)."""
    uid = default_user_id()
    bank = _new_account("FuelEdgeBank", AccountType.BANK, balance=1_000_000)
    cat = _cat("BBM", TransactionType.EXPENSE)

    # tiny quantity + zero price per liter (free fuel promo) is valid
    db = get_test_db()
    tx = create_transaction(
        db, user_id=uid, type=TransactionType.EXPENSE, amount=1,
        account_id=bank, category_id=cat, date_val=TODAY,
        description="promo fuel",
        quantity_liters=0.01, price_per_liter=0)
    qty1 = tx.quantity_liters  # capture before session close (detached instance)
    ppl1 = tx.price_per_liter
    db.close()
    assert qty1 == 0.01
    assert ppl1 == 0
    assert _balance(bank) == 999_999

    # large realistic fill-up
    db = get_test_db()
    tx2 = create_transaction(
        db, user_id=uid, type=TransactionType.EXPENSE, amount=765_000,
        account_id=bank, category_id=cat, date_val=TODAY,
        description="pertamax full tank",
        quantity_liters=250.0, price_per_liter=3_060)
    qty2 = tx2.quantity_liters  # capture before session close (detached instance)
    ppl2 = tx2.price_per_liter
    db.close()
    assert qty2 == 250.0
    assert ppl2 == 3_060
    assert _balance(bank) == 234_999


# ==================== minimum payment: pure integer math ====================

def test_G_minimum_payment_floor_semantics():
    """10% floor with integer division - matches int(x*0.10) for small values."""
    assert minimum_payment_from(0) == 0
    assert minimum_payment_from(-5) == 0          # defensive: never negative
    assert minimum_payment_from(1) == 0           # floor of 0.1
    assert minimum_payment_from(25) == 2          # floor of 2.5
    assert minimum_payment_from(99) == 9
    assert minimum_payment_from(100) == 10
    assert minimum_payment_from(1_000_003) == 100_000  # floor, not round


def test_H_minimum_payment_huge_balance_integer_exact():
    """int(charges * 0.10) via float would LOSE precision beyond 2**53
    (float64 mantissa): for charges = 999_999_999_999_999_999 the float path
    yields 100_000_000_000_000_000, the correct integer floor is
    99_999_999_999_999_999. Integer math is exact at any magnitude.
    """
    huge = 999_999_999_999_999_999
    assert minimum_payment_from(huge) == huge // 10
    assert minimum_payment_from(huge) != int(huge * 0.10)  # float path is WRONG
    assert minimum_payment_from(huge) == 99_999_999_999_999_999


def test_I_minimum_payment_consistent_with_percentage_constant():
    from app.services.credit_card import MIN_PAYMENT_PERCENT
    for charges in (0, 7, 70, 777, 123_456_789):
        assert minimum_payment_from(
            charges) == charges * MIN_PAYMENT_PERCENT // 100

