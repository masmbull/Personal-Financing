"""Authentication + user data isolation regression tests.

Exercises the REAL auth flow (session cookie, login/logout, ownership
scoping). The shared conftest client runs as a pre-authenticated default
user for the legacy suites; here we remove that override and log in for
real, so every check goes through the actual auth machinery.
"""
import re
from datetime import date

from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.main import app
from app.models.models import Account, Budget, Transaction
from tests.conftest import (
    DEFAULT_USER, DEFAULT_USER_2, TEST_PASSWORD, TEST_PASSWORD_HASH,
    get_test_db,
)

TODAY = date.today().isoformat()


def _fresh_client() -> TestClient:
    """A client with the real get_current_user dependency (no override) and
    redirects NOT auto-followed, so we can assert on 3xx responses."""
    app.dependency_overrides.pop(get_current_user, None)
    return TestClient(app, follow_redirects=False)


def _csrf_token(client: TestClient, path: str = "/login") -> str:
    r = client.get(path)
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    assert m, "csrf_token hidden field not found"
    return m.group(1)


def _login(client: TestClient, username: str, password: str):
    token = _csrf_token(client)
    return client.post("/login", data={
        "username": username, "password": password,
        "csrf_token": token, "next": "/",
    })


def _new_user(username: str) -> int:
    db = get_test_db()
    from app.models.models import User
    u = User(username=username, password_hash=TEST_PASSWORD_HASH, is_active=1)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u.id


def _bob_id() -> int:
    db = get_test_db()
    from app.models.models import User
    uid = db.query(User).filter(User.username == DEFAULT_USER).first().id
    db.close()
    return uid


def _alice_id() -> int:
    db = get_test_db()
    from app.models.models import User
    uid = db.query(User).filter(User.username == DEFAULT_USER_2).first().id
    db.close()
    return uid


def _gen_user_client(username: str, password: str = TEST_PASSWORD) -> TestClient:
    """Create a user with own mail-slot data and log in for real."""
    _new_user(username)
    c = _fresh_client()
    _login(c, username, password)
    return c

# ==================== unauthenticated access ====================


def test_unauthenticated_page_redirects_to_login():
    c = _fresh_client()
    r = c.get("/transactions")
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")


def test_unauthenticated_api_returns_401_json():
    c = _fresh_client()
    r = c.get("/api/v1/transactions")
    assert r.status_code == 401
    body = r.json()
    assert body["error"]["code"] == "UNAUTHENTICATED"
    # no stack trace leakage
    assert "Traceback" not in r.text


# ==================== login / register ====================


def test_valid_login_success_and_session_cookie():
    c = _fresh_client()
    r = _login(c, DEFAULT_USER, TEST_PASSWORD)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    # session token stored in a cookie; protected route now reachable
    assert "pf_session" in c.cookies
    assert c.get("/api/v1/accounts").status_code == 200


def test_invalid_password_fails_generic():
    c = _fresh_client()
    r = _login(c, DEFAULT_USER, "wrong-password")
    assert r.status_code == 303
    assert "error=1" in r.headers["location"]
    assert c.get("/api/v1/transactions").status_code == 401


def test_unknown_username_fails_generic():
    c = _fresh_client()
    r = _login(c, "no-such-user", TEST_PASSWORD)
    assert r.status_code == 303
    assert "error=1" in r.headers["location"]


def test_login_requires_csrf_token():
    c = _fresh_client()
    c.get("/login")  # sets csrf cookie, but we POST without a valid token
    r = c.post("/login", data={
        "username": DEFAULT_USER, "password": TEST_PASSWORD,
        "csrf_token": "attacker-token",
    })
    assert r.status_code == 303
    assert "error=1" in r.headers["location"]
    assert c.get("/api/v1/transactions").status_code == 401


def test_register_and_auto_login():
    c = _fresh_client()
    token = _csrf_token(c, path="/register")
    r = c.post("/register", data={
        "username": "newuser", "password": "supersecret1",
        "password2": "supersecret1", "csrf_token": token,
    })
    assert r.status_code == 303
    assert c.get("/api/v1/dashboard").status_code == 200

    # duplicate username rejected
    c2 = _fresh_client()
    token2 = _csrf_token(c2, path="/register")
    r = c2.post("/register", data={
        "username": "newuser", "password": "supersecret1",
        "password2": "supersecret1", "csrf_token": token2,
    })
    assert r.status_code == 303
    assert "error=1" in r.headers["location"]

def _create_own_transaction(client: TestClient, account_id: int, **over):
    payload = {
        "type": "EXPENSE", "amount": 12000, "account_id": account_id,
        "category_id": None, "date": TODAY,
    }
    payload.update(over)
    return client.post("/api/v1/transactions", json=payload).json()["id"]


def _own_account(client: TestClient, name: str = "MailSlot") -> int:
    """Create a NEW user-owned account through the real API."""
    r = client.post("/api/v1/accounts", json={
        "name": name, "type": "CASH", "initial_balance": 0,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]
# ==================== logout / session invalidation ====================


def test_logout_revokes_session():
    c = _fresh_client()
    _login(c, DEFAULT_USER, TEST_PASSWORD)
    assert c.get("/api/v1/transactions").status_code == 200
    token = c.cookies.get("pf_session")

    r = c.post("/logout", data={})  # POST-only logout
    assert r.status_code == 303
    assert r.headers["location"] == "/login"

    # server-side revocation: even the OLD cookie can no longer authenticate
    c.cookies.set("pf_session", token)
    assert c.get("/api/v1/transactions").status_code == 401
    assert c.get("/transactions").status_code == 303


# ==================== IDOR / BOLA ====================


def test_authenticated_user_can_access_own_transaction():
    c = _gen_user_client("own_tx")
    account = _own_account(c, "OwnAcc")
    cat = next(x["id"] for x in c.get("/api/v1/categories").json()["items"]
               if x["type"] == "EXPENSE")
    tid = _create_own_transaction(c, account, category_id=cat)
    assert c.get(f"/api/v1/transactions/{tid}").status_code == 200


def test_user_a_cannot_get_user_b_transaction():
    a = _gen_user_client("geta")
    account_a = _own_account(a, "AccA")
    cat = next(x["id"] for x in a.get("/api/v1/categories").json()["items"]
               if x["type"] == "EXPENSE")
    tid = _create_own_transaction(a, account_a, category_id=cat)

    b = _gen_user_client("getb")
    assert b.get(f"/api/v1/transactions/{tid}").status_code == 404


def test_user_a_cannot_edit_user_b_transaction():
    a = _gen_user_client("edita")
    account_a = _own_account(a, "AccA2")
    cat = next(x["id"] for x in a.get("/api/v1/categories").json()["items"]
               if x["type"] == "EXPENSE")
    tid = _create_own_transaction(a, account_a, category_id=cat)

    b = _gen_user_client("editb")
    assert b.put(f"/api/v1/transactions/{tid}", json={"amount": 999999}).status_code == 404


def test_user_a_cannot_delete_user_b_transaction():
    a = _gen_user_client("dela")
    account_a = _own_account(a, "AccA3")
    cat = next(x["id"] for x in a.get("/api/v1/categories").json()["items"]
               if x["type"] == "EXPENSE")
    tid = _create_own_transaction(a, account_a, category_id=cat)

    b = _gen_user_client("delb")
    assert b.delete(f"/api/v1/transactions/{tid}").status_code == 404
    # owner still has it
    assert a.get(f"/api/v1/transactions/{tid}").status_code == 200


def test_user_a_cannot_confirm_user_b_receipt():
    from tests.conftest import PNG_BYTES

    a = _gen_user_client("rcpta")
    cat = next(x["id"] for x in a.get("/api/v1/categories").json()["items"]
               if x["type"] == "EXPENSE")
    account = _own_account(a, "AccR")
    rid = a.post("/api/v1/receipts",
                 files={"file": ("r.png", PNG_BYTES, "image/png")}
                 ).json()["receipt_id"]

    b = _gen_user_client("rcptb")
    r = b.post(f"/api/v1/receipts/{rid}/confirm", json={
        "type": "EXPENSE", "amount": 1000, "account_id": account,
        "category_id": cat, "date": TODAY,
    })
    assert r.status_code == 404


def test_user_a_cannot_access_user_b_account():
    db = get_test_db()
    bob_account = db.query(Account).filter(Account.name == "BCA").first()
    db.close()
    c = _gen_user_client("accintruder")
    assert c.get(f"/api/v1/accounts/{bob_account.id}").status_code == 404


def test_user_a_cannot_access_user_b_budget():
    from app.models.models import Category, User

    db = get_test_db()
    cat = db.query(Category).filter(Category.name == "Makan & Minum").first()
    owner = User(username="budget_owner", password_hash=TEST_PASSWORD_HASH,
                 is_active=1)
    db.add(owner)
    db.commit()
    db.refresh(owner)
    budget = Budget(user_id=owner.id, category_id=cat.id, amount=100000,
                    month=date.today().month, year=date.today().year)
    db.add(budget)
    db.commit()
    db.refresh(budget)
    db.close()

    c = _gen_user_client("budget_intruder")
    assert c.get(f"/api/v1/budgets/{budget.id}").status_code == 404
    assert c.delete(f"/api/v1/budgets/{budget.id}").status_code == 404
# ==================== global master data ====================


def test_global_bank_master_accessible_to_all_authenticated_users():
    db = get_test_db()
    master = Account(name="BCA Glob", type="BANK", user_id=None,
                     initial_balance=0, current_balance=0)
    db.add(master)
    db.commit()
    db.close()

    u1 = _gen_user_client("master_u1")
    u2 = _gen_user_client("master_u2")
    names1 = [a["name"] for a in u1.get("/api/v1/accounts").json()["items"]]
    names2 = [a["name"] for a in u2.get("/api/v1/accounts").json()["items"]]
    assert "BCA Glob" in names1 and "BCA Glob" in names2


def test_global_category_master_accessible_to_all_authenticated_users():
    # conftest categories are global (no user_id) and shared
    u1 = _gen_user_client("cat_u1")
    u2 = _gen_user_client("cat_u2")
    names1 = {x["name"] for x in u1.get("/api/v1/categories").json()["items"]}
    names2 = {x["name"] for x in u2.get("/api/v1/categories").json()["items"]}
    assert "Makan & Minum" in names1 and "Makan & Minum" in names2
    assert names1 == names2  # one shared master list


# ==================== migration ====================


def test_migration_adds_user_id_preserves_data_and_is_idempotent(tmp_path):
    from sqlalchemy import create_engine, inspect, text

    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    legacy = create_engine(url, connect_args={"check_same_thread": False})
    with legacy.begin() as conn:
        conn.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE "
            "NOT NULL, password_hash TEXT NOT NULL, is_active INTEGER NOT NULL, "
            "created_at DATETIME, updated_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "type TEXT NOT NULL, institution TEXT, account_number TEXT, "
            "color TEXT, initial_balance INTEGER NOT NULL, "
            "current_balance INTEGER NOT NULL, icon TEXT, "
            "created_at DATETIME, updated_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE transactions (id INTEGER PRIMARY KEY, type TEXT NOT NULL, "
            "amount INTEGER NOT NULL, description TEXT, merchant TEXT, notes TEXT, "
            "date DATE NOT NULL, account_id INTEGER NOT NULL, category_id INTEGER, "
            "transfer_to_account_id INTEGER, created_at DATETIME, updated_at DATETIME)"
        ))
        conn.execute(text(
            "INSERT INTO accounts (name,type,initial_balance,current_balance) "
            "VALUES ('BCA','BANK',1000,1000)"
        ))
        conn.execute(text(
            "INSERT INTO transactions (type,amount,account_id,date) "
            "VALUES ('EXPENSE',500,1,'2026-01-05')"
        ))

    from app.migrations import claim_legacy_rows, run_migrations

    assert run_migrations(legacy) is True       # columns added first run
    assert run_migrations(legacy) is False      # second run is a no-op

    cols = {c["name"] for c in inspect(legacy).get_columns("transactions")}
    assert "user_id" in cols

    # data preserved (not dropped, not truncated)
    with legacy.connect() as conn:
        row = conn.execute(text(
            "SELECT current_balance, user_id FROM accounts WHERE name='BCA'"
        )).fetchone()
        assert row == (1000, None)
        tx = conn.execute(text(
            "SELECT amount, user_id FROM transactions WHERE id=1"
        )).fetchone()
        assert tx == (500, None)

    # legacy rows assigned to bootstrap owner on demand
    from sqlalchemy.orm import sessionmaker
    Sess = sessionmaker(bind=legacy)
    s = Sess()
    claim_legacy_rows(s, 42)
    s.close()
    with legacy.connect() as conn:
        assert conn.execute(text(
            "SELECT user_id FROM transactions WHERE id=1"
        )).fetchone()[0] == 42
    legacy.dispose()


# ==================== mass assignment ====================


def test_user_id_cannot_be_mass_assigned_from_request():
    c = _gen_user_client("mass_alice")
    cats = c.get("/api/v1/categories").json()["items"]
    cat = next(x["id"] for x in cats if x["type"] == "EXPENSE")
    account = _own_account(c, "AccMass")

    # include bob's user_id in the body - must be ignored, not applied
    victim = _bob_id() or 99999
    tx = c.post("/api/v1/transactions", json={
        "type": "EXPENSE", "amount": 555, "account_id": account,
        "category_id": cat, "date": TODAY, "user_id": victim,
    })
    assert tx.status_code == 201
    tid = tx.json()["id"]

    db = get_test_db()
    row = db.query(Transaction).filter(Transaction.id == tid).first()
    owner_id = row.user_id
    db.close()
    assert owner_id != victim

    # victim cannot read it
    v = _gen_user_client("mass_victim")
    assert v.get(f"/api/v1/transactions/{tid}").status_code == 404


# ==================== open redirect protection ====================


def test_login_next_is_same_origin_only():
    c = _fresh_client()
    token = _csrf_token(c)
    r = c.post("/login", data={
        "username": DEFAULT_USER, "password": TEST_PASSWORD,
        "csrf_token": token, "next": "https://evil.example/phish",
    })
    assert r.status_code == 303
    assert r.headers["location"] == "/"  # external next blocked
# ==================== account edit HTML route IDOR regression ====================
# The earlier /accounts/edit/2 {"detail":"Account not found"} finding was a
# stale id after user-scoping. Ownership must stay strict on the HTML edit
# routes too - an intruder editing someone else's account gets 404, and
# cannot mutate master/global accounts.


def test_user_a_cannot_edit_user_b_account_via_html_route():
    db = get_test_db()
    bob_account = db.query(Account).filter(Account.name == "BCA").first()
    bid = bob_account.id
    db.close()
    c = _gen_user_client("editintruder")
    # GET edit form -> 404 (ownership enforced)
    assert c.get(f"/accounts/edit/{bid}").status_code == 404
    # POST edit -> 404
    r = c.post(f"/accounts/edit/{bid}", data={
        "name": "Hacked", "type": "BANK", "initial_balance": "0", "icon": "",
    })
    assert r.status_code == 404
    db = get_test_db()
    acct = db.query(Account).filter(Account.id == bid).first()
    db.close()
    assert acct is not None and acct.name == "BCA"  # unchanged


def test_global_master_account_cannot_be_edited():
    # master accounts (user_id NULL) are immutable for HTML edits
    from app.models.models import Account as A, AccountType
    db = get_test_db()
    master = A(name="BCA Master", type=AccountType.BANK, user_id=None)
    db.add(master)
    db.commit()
    db.refresh(master)
    mid = master.id
    db.close()
    c = _gen_user_client("masterintruder")
    r = c.post(f"/accounts/edit/{mid}", data={
        "name": "Hacked", "type": "BANK", "initial_balance": "0", "icon": "",
    })
    # POST edit uses strictly-own lookup -> must NOT succeed
    assert r.status_code == 404
    db = get_test_db()
    acct = db.query(A).filter(A.id == mid).first()
    db.close()
    assert acct is not None and acct.name == "BCA Master"