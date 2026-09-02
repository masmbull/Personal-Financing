"""Net-worth daily snapshot job tests - idempotency, all-users, historical, tz."""
from datetime import date

from app.models.models import (
    Account, AccountType, AssetRecord, Category, Investment, NetWorthSnapshot,
    TransactionType, User,
)
from app.services.finance import create_transaction
from app.services.reports import (
    net_worth_history, record_daily_snapshot,
    run_daily_net_worth_snapshots,
)
from app.time_utils import today_in_tz, app_timezone, tz_label

from tests.conftest import client, default_user_id, get_test_db  # noqa: E402


def _cat(name):
    db = get_test_db()
    c = db.query(Category).filter(Category.name == name).first()
    db.close()
    return c.id


def _acc(name):
    db = get_test_db()
    a = db.query(Account).filter(Account.name == name).first()
    db.close()
    return a.id


def _snap_count(user_id, d):
    db = get_test_db()
    n = db.query(NetWorthSnapshot).filter(
        NetWorthSnapshot.user_id == user_id,
        NetWorthSnapshot.snapshot_date == d,
    ).count()
    db.close()
    return n


def test_normal_snapshot():
    uid = default_user_id()
    record_daily_snapshot(get_test_db(), uid)
    assert _snap_count(uid, today_in_tz()) == 1


def test_zero_liabilities_snapshot():
    uid = default_user_id()
    snap = record_daily_snapshot(get_test_db(), uid)
    assert snap.total_liabilities == 0
    assert snap.net_worth == snap.total_assets


def _add_income(amount):
    db = get_test_db()
    create_transaction(
        db, user_id=default_user_id(), type=TransactionType.INCOME,
        amount=amount, account_id=_acc("BCA"), category_id=_cat("Gaji"),
        date_val=date.today(), description="gaji")
    db.close()


def test_credit_card_liability_and_debt_and_investment_included():
    uid = default_user_id()
    db = get_test_db()
    # credit card with negative balance -> liability
    db.add(Account(user_id=uid, name="Kartu X", type=AccountType.CREDIT_CARD,
                   initial_balance=-500_000, current_balance=-500_000))
    db.add(Investment(user_id=uid, name="Reksadana", investment_type="Reksadana",
                      amount_invested=100_000, current_value=150_000))
    db.commit()
    db.close()

    snap = record_daily_snapshot(get_test_db(), uid)
    assert snap.total_liabilities >= 500_000       # credit card counted
    assert snap.total_assets >= 150_000            # investment counted


def test_physical_asset_included_in_snapshot():
    uid = default_user_id()
    db = get_test_db()
    db.add(AssetRecord(user_id=uid, name="Mobil", asset_type="Kendaraan",
                       current_value=50_000_000))
    db.commit()
    db.close()
    snap = record_daily_snapshot(get_test_db(), uid)
    assert snap.total_assets >= 50_000_000


def test_multiple_users_isolated():
    db = get_test_db()
    bob = db.query(User).filter_by(username="bob").first()
    alice = db.query(User).filter_by(username="alice").first()
    db.close()
    record_daily_snapshot(get_test_db(), bob.id)
    assert _snap_count(alice.id, today_in_tz()) == 0
    assert _snap_count(bob.id, today_in_tz()) == 1


def test_duplicate_execution_same_date_is_idempotent():
    uid = default_user_id()
    t = today_in_tz()
    run_daily_net_worth_snapshots(get_test_db(), t)
    run_daily_net_worth_snapshots(get_test_db(), t)
    assert _snap_count(uid, t) == 1


def test_run_all_users_creates_snapshot_for_each():
    db = get_test_db()
    bob = db.query(User).filter_by(username="bob").first()
    alice = db.query(User).filter_by(username="alice").first()
    db.close()
    written = run_daily_net_worth_snapshots(get_test_db(), today_in_tz())
    assert written >= 2
    assert _snap_count(bob.id, today_in_tz()) == 1
    assert _snap_count(alice.id, today_in_tz()) == 1


def test_historical_date_snapshot():
    uid = default_user_id()
    past = date(2026, 1, 15)
    record_daily_snapshot(get_test_db(), uid, past)
    assert _snap_count(uid, past) == 1
    hist = net_worth_history(get_test_db(), uid)
    assert any(p["date"] == past for p in hist)


def test_negative_net_worth():
    uid = default_user_id()
    db = get_test_db()
    db.add(Account(user_id=uid, name="Hutang", type=AccountType.LIABILITY,
                   initial_balance=-2_000_000, current_balance=-2_000_000))
    db.commit()
    db.close()
    snap = record_daily_snapshot(get_test_db(), uid)
    assert snap.total_liabilities >= 2_000_000


def test_tz_defaults_to_asia_jakarta():
    assert tz_label() == "Asia/Jakarta"
    assert str(app_timezone()) in ("Asia/Jakarta",)


def test_today_in_tz_returns_date():
    assert isinstance(today_in_tz(), date)
