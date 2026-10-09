"""Tests for new features: recurring transactions, budget alerts, health history, tag filter."""
import pytest
from datetime import date, timedelta


# Use the shared client fixture from conftest (already authenticated as bob)
# and the shared setup_db fixture (autouse=True, already active).

def _api(c, method, path, **kw):
    r = getattr(c, method)(path, **kw)
    assert r.status_code < 300, f"{method.upper()} {path} → {r.status_code}: {r.text[:300]}"
    return r.json()


def _setup(client):
    """Return (acc_id, cat_id) from the seeded test DB."""
    accs = _api(client, "get", "/api/v1/accounts")
    # accounts API returns {"items": [...], "total": N}
    items = accs.get("items", accs) if isinstance(accs, dict) else accs
    acc_id = items[0]["id"]
    cats = _api(client, "get", "/api/v1/categories")
    cat_items = cats.get("items", cats) if isinstance(cats, dict) else cats
    exp_cats = [c for c in cat_items if c.get("type") == "EXPENSE"]
    cat_id = exp_cats[0]["id"] if exp_cats else None
    return acc_id, cat_id


# ── Recurring transactions ────────────────────────────────────────────

def test_recurring_create_list_delete(client):
    acc_id, cat_id = _setup(client)
    today = date.today().isoformat()

    r = _api(client, "post", "/api/v1/recurring", json={
        "account_id": acc_id, "category_id": cat_id,
        "type": "EXPENSE", "amount": 150000,
        "description": "Spotify", "frequency": "MONTHLY",
        "start_date": today,
    })
    rec_id = r["id"]
    assert r["amount"] == 150000
    assert r["frequency"] == "MONTHLY"

    lst = _api(client, "get", "/api/v1/recurring")
    assert any(x["id"] == rec_id for x in lst)

    detail = _api(client, "get", f"/api/v1/recurring/{rec_id}")
    assert detail["description"] == "Spotify"

    upd = _api(client, "put", f"/api/v1/recurring/{rec_id}",
               json={"amount": 200000})
    assert upd["amount"] == 200000

    resp = client.delete(f"/api/v1/recurring/{rec_id}")
    assert resp.status_code == 204

    lst2 = _api(client, "get", "/api/v1/recurring")
    assert not any(x["id"] == rec_id for x in lst2)


def test_recurring_run_generates_transaction(client):
    acc_id, cat_id = _setup(client)
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    _api(client, "post", "/api/v1/recurring", json={
        "account_id": acc_id, "category_id": cat_id,
        "type": "EXPENSE", "amount": 50000,
        "description": "Test Recurring Run", "frequency": "MONTHLY",
        "start_date": yesterday,
    })
    r = _api(client, "post", "/api/v1/recurring/run")
    assert r["created"] >= 1


def test_recurring_idempotent(client):
    """Running twice must not double-post."""
    acc_id, _ = _setup(client)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _api(client, "post", "/api/v1/recurring", json={
        "account_id": acc_id, "type": "INCOME", "amount": 5000000,
        "description": "Gaji Idempotent", "frequency": "MONTHLY",
        "start_date": yesterday,
    })
    _api(client, "post", "/api/v1/recurring/run")
    r2 = _api(client, "post", "/api/v1/recurring/run")
    assert r2["created"] == 0


def test_recurring_update_rejects_another_users_account(client):
    """A recurring schedule cannot be redirected to another user's account."""
    acc_id, cat_id = _setup(client)
    today = date.today().isoformat()
    created = _api(client, "post", "/api/v1/recurring", json={
        "account_id": acc_id, "category_id": cat_id,
        "type": "EXPENSE", "amount": 150000,
        "description": "Private schedule", "frequency": "MONTHLY",
        "start_date": today,
    })

    from app.models.models import Account, AccountType, User
    from tests.conftest import DEFAULT_USER_2, TestingSessionLocal
    db = TestingSessionLocal()
    try:
        alice = db.query(User).filter(User.username == DEFAULT_USER_2).one()
        foreign_account = Account(
            name="Alice private account", user_id=alice.id,
            type=AccountType.BANK, initial_balance=0, current_balance=0,
        )
        db.add(foreign_account)
        db.commit()
        foreign_account_id = foreign_account.id
    finally:
        db.close()

    response = client.put(
        f"/api/v1/recurring/{created['id']}",
        json={"account_id": foreign_account_id},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert _api(client, "get", f"/api/v1/recurring/{created['id']}")["account"]["id"] == acc_id


def test_bill_rejects_another_users_default_account(client):
    """Bills may only retain a default account owned by the current user."""
    from app.models.models import Account, AccountType, User
    from tests.conftest import DEFAULT_USER_2, TestingSessionLocal
    db = TestingSessionLocal()
    try:
        alice = db.query(User).filter(User.username == DEFAULT_USER_2).one()
        account = Account(name="Alice bill account", user_id=alice.id,
                          type=AccountType.BANK, initial_balance=0, current_balance=0)
        db.add(account)
        db.commit()
        foreign_account_id = account.id
    finally:
        db.close()

    response = client.post("/api/v1/bills", json={
        "name": "Should fail", "amount": 50_000, "frequency": "MONTHLY",
        "account_id": foreign_account_id, "due_day": 1,
    })
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_weekly_bill_accepts_sunday_as_due_day(client):
    """Weekly schedules use Python weekdays, where Sunday is 6."""
    response = client.post("/api/v1/bills", json={
        "name": "Sunday schedule", "amount": 50_000,
        "frequency": "WEEKLY", "due_day": 6,
    })
    assert response.status_code == 201
    assert response.json()["due_day"] == 6


# ── Budget alerts ─────────────────────────────────────────────────────

def test_budget_alerts_empty(client):
    today = date.today()
    r = _api(client, "get",
             f"/api/v1/budgets/alerts?year={today.year}&month={today.month}")
    assert "alerts" in r
    assert r["count"] == len(r["alerts"])


def test_budget_alerts_exceeded(client):
    acc_id, cat_id = _setup(client)
    if not cat_id:
        pytest.skip("no expense category")
    today = date.today()

    # Tiny budget so any expense exceeds it
    _api(client, "post", "/api/v1/budgets", json={
        "category_id": cat_id, "amount": 1,
        "month": today.month, "year": today.year,
    })
    _api(client, "post", "/api/v1/transactions", json={
        "account_id": acc_id, "category_id": cat_id,
        "type": "EXPENSE", "amount": 100000,
        "date": today.isoformat(), "description": "Over budget test",
    })
    r = _api(client, "get",
             f"/api/v1/budgets/alerts?year={today.year}&month={today.month}")
    assert r["count"] >= 1
    assert any(a["status"] == "EXCEEDED" for a in r["alerts"])


def test_budget_alert_banner_dashboard_and_budgets(client):
    """Exceeded budget surfaces as an alert banner on / and /budgets."""
    acc_id, cat_id = _setup(client)
    if not cat_id:
        pytest.skip("no expense category")
    today = date.today()
    _api(client, "post", "/api/v1/budgets", json={
        "category_id": cat_id, "amount": 1,
        "month": today.month, "year": today.year,
    })
    _api(client, "post", "/api/v1/transactions", json={
        "account_id": acc_id, "category_id": cat_id,
        "type": "EXPENSE", "amount": 100000,
        "date": today.isoformat(), "description": "Banner test",
    })

    r = client.get("/")
    assert r.status_code == 200
    assert "budget-alert-banner" in r.text
    assert "hampir/lewat batas" in r.text

    r2 = client.get("/budgets")
    assert r2.status_code == 200
    assert "budget-alert-banner" in r2.text


# ── Health score history ──────────────────────────────────────────────

def test_health_score_history_empty(client):
    r = _api(client, "get", "/api/v1/health-score/history?days=30")
    assert isinstance(r, list)


def test_health_score_snapshot_and_history(client):
    snap = _api(client, "post", "/api/v1/health-score/snapshot")
    assert "score" in snap
    assert "snapshot_date" in snap

    history = _api(client, "get", "/api/v1/health-score/history?days=7")
    assert any(h["date"] == snap["snapshot_date"] for h in history)


# ── Transaction list tag filter + summary ────────────────────────────

def test_transaction_list_tag_filter_accepted(client):
    r = client.get("/transactions?filter_tag=999")
    assert r.status_code == 200


def test_transaction_list_with_transactions_shows_summary(client):
    """Add a transaction then check summary cards appear."""
    acc_id, cat_id = _setup(client)
    today = date.today().isoformat()
    _api(client, "post", "/api/v1/transactions", json={
        "account_id": acc_id, "category_id": cat_id,
        "type": "EXPENSE", "amount": 50000,
        "date": today, "description": "Test summary",
    })
    r = client.get("/transactions")
    assert r.status_code == 200
    assert b"Pemasukan" in r.content
    assert b"Pengeluaran" in r.content


# ── Recurring UI pages ────────────────────────────────────────────────

def test_recurring_ui_list(client):
    r = client.get("/recurring")
    assert r.status_code == 200
    assert b"Transaksi Berulang" in r.content


def test_recurring_ui_add_form(client):
    r = client.get("/recurring/add")
    assert r.status_code == 200
    assert b"Transaksi Berulang" in r.content

