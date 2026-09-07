"""Statement / billing-cycle deep audit.

Pins the credit-card statement engine to exact calendar semantics:
- closing date = most recent statement_day <= ref (with short-month clamping)
- due date = payment_due_day of the month AFTER closing (clamped), or
  closing + 21 days when no payment_due_day is configured
- period window [prev_closing + 1, closing] INCLUSIVE on both ends
- payments counted only within [period_start, due_date]
- refunds credited within the period NET against charges
- minimum payment = integer 10% floor; statuses NOT_DUE/UNPAID/PARTIAL/PAID

Fixed reference dates (2027/2028) are used so tests never depend on today().
"""
from datetime import date

import pytest

from app.models.models import Account, AccountType, Category, TransactionType
from app.services import credit_card as cc
from app.services.credit_card import (
    calculate_statement, statement_closing_date, statement_period_for,
)
from app.services.finance import create_transaction

from tests.conftest import default_user_id, get_test_db


def _cat(name, tx_type):
    db = get_test_db()
    c = db.query(Category).filter(
        Category.name == name, Category.type == tx_type).first()
    db.close()
    return c.id


def _new_cc(name="AuditCC", statement_date=15, payment_due_day=5,
            balance=0, credit_limit=100_000_000) -> Account:
    db = get_test_db()
    a = Account(
        user_id=default_user_id(), name=name, type=AccountType.CREDIT_CARD,
        initial_balance=balance, current_balance=balance,
        statement_date=statement_date, payment_due_day=payment_due_day,
        credit_limit=credit_limit,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    db.close()
    return a


def _charge(cc_id, amount, d, desc="charge"):
    db = get_test_db()
    tx = create_transaction(
        db, user_id=default_user_id(), type=TransactionType.EXPENSE,
        amount=amount, account_id=cc_id,
        category_id=_cat("Belanja", TransactionType.EXPENSE),
        date_val=d, description=desc)
    db.close()
    return tx


def _pay(src_id, dest_id, amount, d, desc="payment"):
    """TRANSFER from ``src_id`` INTO ``dest_id``."""
    db = get_test_db()
    tx = create_transaction(
        db, user_id=default_user_id(), type=TransactionType.TRANSFER,
        amount=amount, account_id=src_id, category_id=None,
        transfer_to_account_id=dest_id, date_val=d, description=desc)
    db.close()
    return tx


def _stmt(account, ref):
    db = get_test_db()
    p = calculate_statement(db, account, ref, default_user_id())
    db.close()
    return p


# ==================== closing-date math ====================

def test_A_closing_is_most_recent_statement_day_le_ref():
    assert statement_closing_date(15, date(2027, 3, 20)) == date(2027, 3, 15)
    assert statement_closing_date(15, date(2027, 3, 15)) == date(2027, 3, 15)
    # before this month's closing -> previous month
    assert statement_closing_date(15, date(2027, 3, 10)) == date(2027, 2, 15)
    assert statement_closing_date(1, date(2027, 3, 1)) == date(2027, 3, 1)


def test_B_closing_clamps_to_short_months():
    # statement_day 31 in a 28-day February (2027 is not a leap year)
    assert statement_closing_date(31, date(2027, 2, 28)) == date(2027, 2, 28)
    # leap year February 2028 has 29 days
    assert statement_closing_date(31, date(2028, 2, 29)) == date(2028, 2, 29)
    # 30-day month
    assert statement_closing_date(31, date(2027, 4, 30)) == date(2027, 4, 30)
    # day 31 requested in Feb (ref mid-month) -> clamped to Feb 28
    assert statement_closing_date(31, date(2027, 2, 10)) == date(2027, 1, 31)


# ==================== due-date math ====================

def test_C_due_is_payment_due_day_of_month_after_closing():
    account = _new_cc("DueCC", statement_date=15, payment_due_day=5)
    p = statement_period_for(account, date(2027, 3, 20))
    assert p.closing_date == date(2027, 3, 15)
    assert p.due_date == date(2027, 4, 5)


def test_D_due_clamped_in_short_months():
    # closing 2027-03-31, due day 31 -> April has 30 days -> 2027-04-30
    account = _new_cc("DueCC2", statement_date=31, payment_due_day=31)
    p = statement_period_for(account, date(2027, 3, 31))
    assert p.closing_date == date(2027, 3, 31)
    assert p.due_date == date(2027, 4, 30)


def test_E_due_defaults_to_closing_plus_21_days():
    account = _new_cc("DueCC3", statement_date=15, payment_due_day=None)
    p = statement_period_for(account, date(2027, 1, 20))
    assert p.closing_date == date(2027, 1, 15)
    assert p.due_date == date(2027, 2, 5)  # 15 + 21 days


def test_F_period_window_is_prev_closing_plus_one_to_closing():
    account = _new_cc("WinCC", statement_date=15, payment_due_day=5)
    p = statement_period_for(account, date(2027, 3, 20))
    assert p.period_start == date(2027, 2, 16)  # day after prev closing
    assert p.period_end == date(2027, 3, 15)    # == closing


# ==================== charge window boundaries ====================

def test_G_charges_on_period_boundaries_are_inclusive():
    account = _new_cc("BoundCC", statement_date=15, payment_due_day=5)
    cc_id = account.id
    _charge(cc_id, 100_000, date(2027, 2, 15))  # day BEFORE period_start
    _charge(cc_id, 200_000, date(2027, 2, 16))  # period_start itself
    _charge(cc_id, 300_000, date(2027, 3, 15))  # period_end / closing itself
    _charge(cc_id, 400_000, date(2027, 3, 16))  # next cycle

    p = _stmt(account, date(2027, 3, 20))
    assert p.statement_balance == 500_000       # 200k + 300k only
    assert p.minimum_payment == 50_000
    assert p.payment_status == "UNPAID"


def test_H_charges_after_closing_belong_to_next_cycle():
    account = _new_cc("NextCC", statement_date=15, payment_due_day=5)
    cc_id = account.id
    _charge(cc_id, 50_000, date(2027, 3, 16))   # after closing

    this_cycle = _stmt(account, date(2027, 3, 20))
    assert this_cycle.statement_balance == 0
    assert this_cycle.payment_status == "NOT_DUE"

    next_cycle = _stmt(account, date(2027, 4, 20))
    assert next_cycle.statement_balance == 50_000


def test_I_transfers_out_of_card_are_not_charges():
    """Cash advance (TRANSFER out of the card) moves liability but is NOT a
    statement charge (only EXPENSE is)."""
    account = _new_cc("AdvCC", statement_date=15, payment_due_day=5,
                      balance=-1_000_000)
    cash_id = _bank("AdvCash", balance=0)

    _pay(account.id, cash_id, 200_000, date(2027, 3, 10), "cash advance out")

    p = _stmt(account, date(2027, 3, 20))
    assert p.statement_balance == 0
    assert p.payment_status == "NOT_DUE"


# ==================== payment window ====================

def test_J_payments_counted_only_up_to_due_date():
    from app.models.models import Account as Acc
    account = _new_cc("PayCC", statement_date=15, payment_due_day=5)
    cc_id = account.id
    db = get_test_db()
    bank = Acc(user_id=default_user_id(), name="PayBank",
               type=AccountType.BANK, initial_balance=50_000_000,
               current_balance=50_000_000)
    db.add(bank)
    db.commit()
    db.refresh(bank)
    bank_id = bank.id
    db.close()

    _charge(cc_id, 1_000_000, date(2027, 3, 1))
    _pay(bank_id, cc_id, 400_000, date(2027, 4, 5))    # ON due date: counted
    _pay(bank_id, cc_id, 100_000, date(2027, 4, 6))    # AFTER due: NOT counted

    p = _stmt(account, date(2027, 3, 20))
    assert p.due_date == date(2027, 4, 5)
    assert p.statement_balance == 1_000_000
    assert p.payment_status == "PARTIAL"  # 400k of 1M (late 100k not credited)


def test_K_payments_before_period_start_not_counted():
    from app.models.models import Account as Acc
    account = _new_cc("PayCC2", statement_date=15, payment_due_day=5)
    cc_id = account.id
    db = get_test_db()
    bank = Acc(user_id=default_user_id(), name="PayBank2",
               type=AccountType.BANK, initial_balance=50_000_000,
               current_balance=50_000_000)
    db.add(bank)
    db.commit()
    db.refresh(bank)
    bank_id = bank.id
    db.close()

    _charge(cc_id, 800_000, date(2027, 2, 20))
    _pay(bank_id, cc_id, 800_000, date(2027, 2, 10))  # BEFORE period_start

    p = _stmt(account, date(2027, 3, 20))
    # The payment belongs to the PREVIOUS cycle's window; this cycle sees an
    # unpaid charge (paid=0) even though the card balance is now zero.
    assert p.statement_balance == 800_000
    assert p.payment_status == "UNPAID"


# ==================== statuses ====================

def test_L_status_not_due_when_no_charges():
    account = _new_cc("StCC1", statement_date=15, payment_due_day=5)
    p = _stmt(account, date(2027, 3, 20))
    assert p.statement_balance == 0
    assert p.minimum_payment == 0
    assert p.payment_status == "NOT_DUE"


def _bank(name, balance=50_000_000) -> int:
    db = get_test_db()
    bank = Account(user_id=default_user_id(), name=name,
                   type=AccountType.BANK, initial_balance=balance,
                   current_balance=balance)
    db.add(bank)
    db.commit()
    db.refresh(bank)
    bid = bank.id
    db.close()
    return bid


def test_M_status_unpaid_partial_paid():
    account = _new_cc("StCC2", statement_date=15, payment_due_day=5)
    cc_id = account.id
    bank_id = _bank("StBank")

    _charge(cc_id, 1_000_000, date(2027, 3, 1))

    unpaid = _stmt(account, date(2027, 3, 20))
    assert unpaid.payment_status == "UNPAID"

    _pay(bank_id, cc_id, 400_000, date(2027, 3, 25))
    partial = _stmt(account, date(2027, 3, 26))
    assert partial.payment_status == "PARTIAL"
    assert partial.minimum_payment == 100_000  # 10% integer floor

    _pay(bank_id, cc_id, 600_000, date(2027, 3, 27))
    paid = _stmt(account, date(2027, 3, 28))
    assert paid.payment_status == "PAID"


# ==================== refund netting ====================

def test_N_refund_within_period_reduces_statement_balance():
    """A refund reverses a charge on the SAME statement: 1M charged - 300k
    refunded = 700k balance, 70k minimum."""
    account = _new_cc("RefNetCC", statement_date=15, payment_due_day=5)
    cc_id = account.id
    _charge(cc_id, 1_000_000, date(2027, 3, 1))

    db = get_test_db()
    cc.credit_card_refund(db, user_id=default_user_id(), account_id=cc_id,
                          amount=300_000, date_val=date(2027, 3, 5),
                          description="item returned")
    db.close()

    p = _stmt(account, date(2027, 3, 20))
    assert p.statement_balance == 700_000
    assert p.minimum_payment == 70_000
    assert p.payment_status == "UNPAID"


def test_O_refund_can_flip_status_to_paid_or_not_due():
    account = _new_cc("RefFlipCC", statement_date=15, payment_due_day=5)
    cc_id = account.id
    bank_id = _bank("RefFlipBank")

    # charge 1M, refund 300k -> net 700k; pay 700k -> PAID on NET balance
    _charge(cc_id, 1_000_000, date(2027, 3, 1))
    db = get_test_db()
    cc.credit_card_refund(db, user_id=default_user_id(), account_id=cc_id,
                          amount=300_000, date_val=date(2027, 3, 2))
    db.close()
    _pay(bank_id, cc_id, 700_000, date(2027, 3, 25))
    p = _stmt(account, date(2027, 3, 26))
    assert p.statement_balance == 700_000
    assert p.payment_status == "PAID"  # paid covers the NET, not gross charges

    # Refund exceeding this period's charges clamps at 0 -> NOT_DUE.
    # Set current_balance negative so the over-refund guard allows a large refund.
    db = get_test_db()
    acc_row = db.query(Account).filter(Account.id == cc_id).first()
    acc_row.initial_balance = -5_000_000   # earlier-cycle liability backing
    acc_row.current_balance = -5_000_000
    db.commit()
    db.close()
    # Refund date must be inside the period [2027-2-16, 2027-3-15] to affect it.
    db = get_test_db()
    cc.credit_card_refund(db, user_id=default_user_id(), account_id=cc_id,
                          amount=2_000_000, date_val=date(2027, 3, 15),
                          description="refund of last month's charge")
    db.close()
    p2 = _stmt(account, date(2027, 3, 28))
    # Refund exceeds charges -> net_charges clamps at 0 -> NOT_DUE
    assert p2.statement_balance == 0
    assert p2.payment_status == "NOT_DUE"


# ==================== guards & scoping ====================

def test_P_not_a_credit_card_raises():
    db = get_test_db()
    bank = Account(user_id=default_user_id(), name="NotCC",
                   type=AccountType.BANK, initial_balance=0,
                   current_balance=0, statement_date=15)
    db.add(bank)
    db.commit()
    db.refresh(bank)
    db.close()
    with pytest.raises(ValueError, match="Not a credit card"):
        _stmt(bank, date(2027, 3, 20))


def test_Q_cc_without_statement_date_raises():
    db = get_test_db()
    cc_no_stmt = Account(user_id=default_user_id(), name="NoStmtCC",
                         type=AccountType.CREDIT_CARD, initial_balance=0,
                         current_balance=0)
    db.add(cc_no_stmt)
    db.commit()
    db.refresh(cc_no_stmt)
    db.close()
    with pytest.raises(ValueError, match="Not a credit card"):
        _stmt(cc_no_stmt, date(2027, 3, 20))


def test_R_statement_scopes_transactions_by_user():
    """The user_id filter excludes rows belonging to other users even if such
    rows were written directly against the card."""
    from app.models.models import Transaction as Tx, User
    account = _new_cc("ScopeCC", statement_date=15, payment_due_day=5)
    cc_id = account.id
    _charge(cc_id, 100_000, date(2027, 3, 2))  # bob's own

    db = get_test_db()
    alice = db.query(User).filter(User.username == "alice").first()
    db.add(Tx(user_id=alice.id, type=TransactionType.EXPENSE, amount=999_000,
              account_id=cc_id, date=date(2027, 3, 3), description="alien"))
    db.commit()
    db.close()

    p = _stmt(account, date(2027, 3, 20))
    assert p.statement_balance == 100_000      # only bob's charge


def test_S_full_cycle_end_to_end_reconciles_with_liability():
    """Statement math reconciles with the ledger: charges - refunds - payments
    inside the window equal the outstanding movement of the cycle."""
    account = _new_cc("E2ECC", statement_date=15, payment_due_day=5)
    cc_id = account.id
    bank_id = _bank("E2EBank")

    _charge(cc_id, 2_000_000, date(2027, 2, 20))            # in period
    _charge(cc_id, 1_000_000, date(2027, 3, 10))            # in period
    db = get_test_db()
    cc.credit_card_refund(db, user_id=default_user_id(), account_id=cc_id,
                          amount=500_000, date_val=date(2027, 3, 11))
    db.close()
    _pay(bank_id, cc_id, 1_500_000, date(2027, 3, 12))      # in window

    p = _stmt(account, date(2027, 3, 20))
    # net charges = 3M - 500k refund = 2.5M; paid 1.5M -> PARTIAL
    assert p.statement_balance == 2_500_000
    assert p.minimum_payment == 250_000
    assert p.payment_status == "PARTIAL"

    # ledger cross-check: outstanding liability = 3M charged - 500k refund
    # - 1.5M paid = 1M
    db = get_test_db()
    acc_row = db.query(Account).filter(Account.id == cc_id).first()
    outstanding = -acc_row.current_balance
    db.close()
    assert outstanding == 1_000_000
    assert outstanding == p.statement_balance - 1_500_000




