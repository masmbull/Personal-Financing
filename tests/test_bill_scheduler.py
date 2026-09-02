"""Bill auto-post scheduler tests - idempotency, date math, inactive, ownership."""
from datetime import date

from app.models.models import (
    Account, Bill, BillFrequency, BillOccurrence, BillOccurrenceStatus,
    Category,
)
from app.services.bills import (
    due_occurrences, generate_bill_occurrences,
    occurrence_dates, pay_bill,
)

from tests.conftest import client, default_user_id, get_test_db  # noqa: E402


def _setup_bill(**overrides) -> int:
    db = get_test_db()
    acc = db.query(Account).filter(Account.name == "BCA").first()
    cat = db.query(Category).filter(Category.name == "Makan & Minum").first()
    defaults = dict(
        user_id=default_user_id(), name="Listrik PLN", amount=500_000,
        frequency=BillFrequency.MONTHLY, due_day=10, account_id=acc.id,
        category_id=cat.id, auto_create=False, active=True,
    )
    defaults.update(overrides)
    bill = Bill(**defaults)
    db.add(bill)
    db.commit()
    db.refresh(bill)
    rid = bill.id
    db.close()
    return rid


def _bill_row(bill_id):
    db = get_test_db()
    b = db.query(Bill).filter(Bill.id == bill_id).first()
    db.close()
    return b

# ==================== occurrence_dates math ====================


def test_monthly_occurrence_after_date():
    bill = _bill_row(_setup_bill(frequency=BillFrequency.MONTHLY, due_day=15))
    dates = occurrence_dates(bill, date(2026, 8, 20))
    assert dates[:3] == [date(2026, 9, 15), date(2026, 10, 15), date(2026, 11, 15)]


def test_monthly_end_of_month_clamped():
    """due_day=31 -> Feb gets 28/29."""
    bill = _bill_row(_setup_bill(frequency=BillFrequency.MONTHLY, due_day=31))
    dates = occurrence_dates(bill, date(2026, 1, 5))
    feb_2026 = next(d for d in dates if d.month == 2 and d.year == 2026)
    assert feb_2026.day == 28  # 2026 not a leap year
    dates2 = occurrence_dates(bill, date(2027, 12, 5))
    feb_2028 = next(d for d in dates2 if d.month == 2 and d.year == 2028)
    assert feb_2028.day == 29


def test_weekly_occurrence_after_date():
    bill = _bill_row(_setup_bill(frequency=BillFrequency.WEEKLY, due_day=0))  # Monday
    dates = occurrence_dates(bill, date(2026, 9, 1))  # Tuesday
    for d in dates[:4]:
        assert d.weekday() == 0 and d > date(2026, 9, 1)
    for a, b in zip(dates[:3], dates[1:4]):
        assert (b - a).days == 7


def test_yearly_occurrence_after_date():
    bill = _bill_row(_setup_bill(frequency=BillFrequency.YEARLY, due_day=15))
    dates = occurrence_dates(bill, date(2026, 10, 1))
    assert dates[0] > date(2026, 10, 1) and dates[0].day == 15


# ==================== first occurrence / generation ====================


def test_first_occurrence_generated():
    rid = _setup_bill(frequency=BillFrequency.MONTHLY, due_day=10)
    db = get_test_db()
    created = generate_bill_occurrences(
        db, as_of=date(2026, 10, 15), user_id=default_user_id())
    db.close()
    assert created >= 1
    db = get_test_db()
    occs = db.query(BillOccurrence).filter(BillOccurrence.bill_id == rid).all()
    db.close()
    assert len(occs) >= 1 and occs[0].due_date.day == 10


def test_duplicate_scheduler_run_creates_nothing():
    rid = _setup_bill(frequency=BillFrequency.MONTHLY, due_day=10)
    db = get_test_db()
    first = generate_bill_occurrences(
        db, as_of=date(2026, 11, 15), user_id=default_user_id())
    second = generate_bill_occurrences(
        db, as_of=date(2026, 11, 15), user_id=default_user_id())
    db.close()
    assert first >= 1
    assert second == 0  # idempotent
    db = get_test_db()
    count = db.query(BillOccurrence).filter(BillOccurrence.bill_id == rid).count()
    db.close()
    assert count >= 1


# ==================== inactive / ownership / missing due_day ====================


def test_inactive_bill_no_occurrences():
    rid = _setup_bill(frequency=BillFrequency.MONTHLY, due_day=10, active=False)
    db = get_test_db()
    created = generate_bill_occurrences(
        db, as_of=date(2026, 11, 15), user_id=default_user_id())
    db.close()
    assert created == 0


def test_other_user_does_not_see_occurrences():
    _setup_bill(frequency=BillFrequency.MONTHLY, due_day=10)
    db = get_test_db()
    bob_id = default_user_id()
    generate_bill_occurrences(db, as_of=date(2026, 11, 15), user_id=bob_id)
    from app.models.models import User
    alice_id = db.query(User).filter_by(username="alice").first().id
    due = due_occurrences(db, user_id=alice_id, as_of=date(2026, 11, 15))
    db.close()
    assert len(due) == 0


def test_bill_without_due_day_skipped():
    rid = _setup_bill(frequency=BillFrequency.MONTHLY, due_day=None)
    db = get_test_db()
    created = generate_bill_occurrences(
        db, as_of=date(2026, 11, 15), user_id=default_user_id())
    db.close()
    assert created == 0
    db = get_test_db()
    count = db.query(BillOccurrence).filter(BillOccurrence.bill_id == rid).count()
    db.close()
    assert count == 0


def test_monthly_rollover_multiple_months():
    rid = _setup_bill(frequency=BillFrequency.MONTHLY, due_day=10)
    db = get_test_db()
    created = generate_bill_occurrences(
        db, as_of=date(2026, 12, 20), user_id=default_user_id())
    db.close()
    assert created >= 3
    db = get_test_db()
    occs = db.query(BillOccurrence).filter(BillOccurrence.bill_id == rid).all()
    db.close()
    months = {(o.due_date.year, o.due_date.month) for o in occs}
    assert len(months) >= 3


def test_overdue_bill_backfills():
    rid = _setup_bill(frequency=BillFrequency.MONTHLY, due_day=10)
    db = get_test_db()
    created = generate_bill_occurrences(
        db, as_of=date(2026, 12, 10), user_id=default_user_id())
    db.close()
    assert created >= 3
    db = get_test_db()
    occs = db.query(BillOccurrence).filter(
        BillOccurrence.bill_id == rid).order_by(BillOccurrence.due_date).all()
    db.close()
    assert occs[0].status == BillOccurrenceStatus.DUE


def test_due_occurrences_filters_by_as_of():
    db = get_test_db()
    bob_id = default_user_id()
    due = due_occurrences(db, user_id=bob_id, as_of=date(2026, 11, 15))
    db.close()
    assert isinstance(due, list)


def test_pay_bill_still_works_after_scheduler():
    rid = _setup_bill(frequency=BillFrequency.MONTHLY, due_day=10)
    db = get_test_db()
    bob_id = default_user_id()
    generate_bill_occurrences(db, as_of=date(2026, 11, 15), user_id=bob_id)
    bill, payment = pay_bill(db, rid, bob_id, pay_date=date(2026, 10, 10))
    assert payment.id is not None
    db.close()

# ==================== API endpoints ====================


def _acc_id(name):
    db = get_test_db()
    a = db.query(Account).filter(Account.name == name).first()
    aid = a.id if a else None
    db.close()
    return aid


def test_api_generate_and_list_occurrences():
    rid = _setup_bill(frequency=BillFrequency.MONTHLY, due_day=10,
                      account_id=_acc_id("BCA"))
    r = client.post("/api/v1/bills/occurrences/run?as_of=2026-12-15")
    assert r.status_code == 201
    body = r.json()
    assert body["created"] >= 1
    # idempotent at the API level too
    r2 = client.post("/api/v1/bills/occurrences/run?as_of=2026-12-15")
    assert r2.status_code == 201
    assert r2.json()["created"] == 0

    r3 = client.get("/api/v1/bills/occurrences/due?as_of=2026-12-15")
    assert r3.status_code == 200
    assert any(i["bill_id"] == rid for i in r3.json()["items"])


def test_api_pay_occurrence_marks_paid():
    rid = _setup_bill(frequency=BillFrequency.MONTHLY, due_day=10,
                      account_id=_acc_id("BCA"))
    client.post("/api/v1/bills/occurrences/run?as_of=2026-12-15")
    items = client.get(
        "/api/v1/bills/occurrences/due?as_of=2026-12-15").json()["items"]
    occ = next(i for i in items if i["bill_id"] == rid)

    acc = _acc_id("BCA")
    r = client.post(f"/api/v1/bills/occurrences/{occ['id']}/pay", json={
        "account_id": acc, "date": "2026-12-10", "amount": 5000})
    assert r.status_code == 201, r.text
    assert r.json()["transaction_id"] is not None

    # paying again -> 400 (already PAID, not DUE)
    r2 = client.post(f"/api/v1/bills/occurrences/{occ['id']}/pay", json={
        "account_id": acc, "date": "2026-12-10", "amount": 5000})
    assert r2.status_code == 400


def test_same_month_due_after_creation_is_generated():
    """Bill created on the 1st with due_day=10 -> the 10th of the SAME month
    must be generated when the scheduler runs after it (regression for a
    base-date off-by-one that used to skip it)."""
    db = get_test_db()
    acc = db.query(Account).filter(Account.name == "BCA").first()
    cat = db.query(Category).filter(Category.name == "Makan & Minum").first()
    from datetime import datetime
    bill = Bill(user_id=default_user_id(), name="RegListrik", amount=200_000,
                frequency=BillFrequency.MONTHLY, due_day=10, account_id=acc.id,
                category_id=cat.id, active=True,
                created_at=datetime(2026, 9, 1, 8, 0, 0))
    db.add(bill)
    db.commit()
    db.refresh(bill)
    rid = bill.id
    db.close()

    db = get_test_db()
    # scheduler runs on Sep 15 -> Sep 10 occurrence must exist
    created = generate_bill_occurrences(
        db, as_of=date(2026, 9, 15), user_id=default_user_id())
    db.close()
    assert created >= 1
    db = get_test_db()
    occ = db.query(BillOccurrence).filter(
        BillOccurrence.bill_id == rid,
        BillOccurrence.due_date == date(2026, 9, 10)).first()
    db.close()
    assert occ is not None
