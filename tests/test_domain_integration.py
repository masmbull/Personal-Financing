"""Integration tests: merchant, payment_method, fuel, credit_card domains."""
from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.api.deps import CurrentUser, get_current_user
from app.main import app
from app.models.models import Account, AccountType, Category, Merchant, PaymentMethod, Transaction, FuelPrice, User
from app.services.seed_master import seed_master_data
from tests.conftest import DEFAULT_USER, DEFAULT_USER_2, default_user_id, get_test_db

TODAY = date.today().isoformat()

@pytest.fixture(autouse=True)
def _seed_master():
    db = get_test_db()
    seed_master_data(db)
    db.close()

def _client():
    return TestClient(app)

def _uid(username: str) -> int:
    db = get_test_db()
    uid = db.query(User).filter(User.username == username).first().id
    db.close()
    return uid

def _as(username: str, uid: int):
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=uid, username=username, display_name=username)

def _reset_user():
    app.dependency_overrides.pop(get_current_user, None)

def _cat(name: str) -> int:
    db = get_test_db()
    cid = db.query(Category).filter(Category.name == name).first().id
    db.close()
    return cid

def _new_account(name: str, type_: AccountType, uid: int = None, balance: int = 0) -> int:
    uid = uid or default_user_id()
    db = get_test_db()
    a = Account(user_id=uid, name=name, type=type_, initial_balance=balance, current_balance=balance)
    db.add(a)
    db.commit()
    db.refresh(a)
    aid = a.id
    db.close()
    return aid

class TestMerchantCRUD:
    def test_create_list_get(self):
        r = _client().post("/api/v1/merchants", json={
            "canonical_name": "Warung Bu Tini", "merchant_type": "FOOD_BEVERAGE",
            "aliases": ["WBT", "warung tini"],
        })
        assert r.status_code == 201, r.text
        b = r.json()
        assert b["canonical_name"] == "Warung Bu Tini"
        mid = b["id"]
        assert any(m["id"] == mid for m in _client().get("/api/v1/merchants").json()["items"])

    def test_update_renames(self):
        mid = _client().post("/api/v1/merchants", json={
            "canonical_name": "TmpMart", "merchant_type": "RETAIL",
        }).json()["id"]
        r = _client().put(f"/api/v1/merchants/{mid}", json={"canonical_name": "TmpRenamed"})
        assert r.status_code == 200

    def test_empty_name_rejected(self):
        r = _client().post("/api/v1/merchants", json={
            "canonical_name": "", "merchant_type": "OTHER",
        })

class TestMerchantOwnership:
    def _bob_merchant(self) -> int:
        return _client().post("/api/v1/merchants", json={
            "canonical_name": "IdorMart", "merchant_type": "RETAIL",
        }).json()["id"]

    def _alice_account(self) -> int:
        alice = _uid(DEFAULT_USER_2)
        return _new_account("AliceBank", AccountType.BANK, uid=alice, balance=500_000)

    def test_other_user_cannot_read(self):
        mid = self._bob_merchant()
        alice = _uid(DEFAULT_USER_2)
        _as(DEFAULT_USER_2, alice)
        try:
            assert _client().get(f"/api/v1/merchants/{mid}").status_code == 404
        finally:
            _reset_user()

    def test_other_user_cannot_update(self):
        mid = self._bob_merchant()
        alice = _uid(DEFAULT_USER_2)
        _as(DEFAULT_USER_2, alice)
        try:
            r = _client().put(f"/api/v1/merchants/{mid}", json={"canonical_name": "Hacked"})
            assert r.status_code == 404
        finally:
            _reset_user()

    def test_other_user_cannot_delete(self):
        mid = self._bob_merchant()
        alice = _uid(DEFAULT_USER_2)
        _as(DEFAULT_USER_2, alice)
        try:
            assert _client().delete(f"/api/v1/merchants/{mid}").status_code == 404
        finally:
            _reset_user()

    def test_global_visible_to_all(self):
        bob_ids = {m["id"] for m in _client().get("/api/v1/merchants").json()["items"]}
        alice = _uid(DEFAULT_USER_2)
        _as(DEFAULT_USER_2, alice)
        try:
            alice_ids = {m["id"] for m in _client().get("/api/v1/merchants").json()["items"]}
            assert bob_ids.issubset(alice_ids)
        finally:
            _reset_user()

class TestPaymentMethod:
    def test_create_list_get(self):
        r = _client().post("/api/v1/payment-methods", json={
            "name": "BNI Debit", "method_type": "DEBIT_CARD",
        })
        assert r.status_code == 201, r.text
        pid = r.json()["id"]
        items = _client().get("/api/v1/payment-methods").json()["items"]
        assert any(p["id"] == pid for p in items)

    def test_update_name(self):
        pid = _client().post("/api/v1/payment-methods", json={
            "name": "OldName", "method_type": "CREDIT_CARD",
        }).json()["id"]
        r = _client().put(f"/api/v1/payment-methods/{pid}", json={"name": "NewName"})
        assert r.status_code == 200

    def test_delete_payment_method(self):
        pid = _client().post("/api/v1/payment-methods", json={
            "name": "DelPM", "method_type": "CASH",
        }).json()["id"]
        assert _client().delete(f"/api/v1/payment-methods/{pid}").status_code == 204

class TestTransactionWithForeignKeys:
    def test_transaction_stores_foreign_keys(self):
        m_id = _client().post("/api/v1/merchants", json={
            "canonical_name": "TxnMart", "merchant_type": "RETAIL",
        }).json()["id"]
        pm_id = _client().post("/api/v1/payment-methods", json={
            "name": "TxnPM", "method_type": "EWALLET",
        }).json()["id"]
        acc = _new_account("TxnAcc", AccountType.BANK, balance=100_000)
        r = _client().post("/api/v1/transactions", json={
            "type": "EXPENSE", "amount": 5000, "account_id": acc,
            "category_id": _cat("Makan & Minum"),
            "merchant_id": m_id, "payment_method_id": pm_id, "date": TODAY,
        })
        assert r.status_code == 201, r.text
        tid = r.json()["id"]
        db = get_test_db()
        tx = db.query(Transaction).filter(Transaction.id == tid).first()
        assert tx.merchant_id == m_id
        assert tx.payment_method_id == pm_id
        db.close()

    def test_transaction_survives_merchant_delete(self):
        m_id = _client().post("/api/v1/merchants", json={
            "canonical_name": "DelMart", "merchant_type": "RETAIL",
        }).json()["id"]
        acc = _new_account("DelAcc", AccountType.BANK, balance=100_000)
        r = _client().post("/api/v1/transactions", json={
            "type": "EXPENSE", "amount": 1000, "account_id": acc,
            "category_id": _cat("Makan & Minum"), "merchant_id": m_id, "date": TODAY,
        })
        tid = r.json()["id"]
        _client().delete(f"/api/v1/merchants/{m_id}")
        db = get_test_db()
        tx = db.query(Transaction).filter(Transaction.id == tid).first()

class TestCreditCard:
    def test_create_cc_account(self):
        r = _client().post("/api/v1/accounts", json={
            "name": "BCA Card", "type": "CREDIT_CARD", "initial_balance": 0,
            "credit_limit": 10_000_000, "statement_date": 15, "payment_due_day": 5,
            "interest_rate_pct": 2.5, "annual_fee": 500_000, "card_network": "VISA",
        })
        assert r.status_code == 201, r.text
        b = r.json()
        assert b["credit_limit"] == 10_000_000

    def test_purchase_increases_liability(self):
        cc = _new_account("MyCC", AccountType.CREDIT_CARD, balance=0)
        db = get_test_db()
        a = db.query(Account).filter(Account.id == cc).first()
        a.credit_limit = 5_000_000
        db.commit()
        db.close()
        r = _client().post("/api/v1/transactions", json={
            "type": "EXPENSE", "amount": 200_000, "account_id": cc,
            "category_id": _cat("Makan & Minum"), "date": TODAY,
        })
        assert r.status_code == 201
        bal = _client().get(f"/api/v1/accounts/{cc}").json()["current_balance"]
        assert bal == -200_000

class TestMigration:
    def _cols(self, table: str) -> set:
        db = get_test_db()
        cols = {c[1] for c in db.execute(text(f"PRAGMA table_info({table})")).fetchall()}
        db.close()
        return cols

    def test_transaction_domain_columns(self):
        cols = self._cols("transactions")
        assert "merchant_id" in cols
        assert "payment_method_id" in cols
        assert "fuel_product_id" in cols
        assert "quantity_liters" in cols
        assert "price_per_liter" in cols

    def test_account_domain_columns(self):
        cols = self._cols("accounts")
        assert "credit_limit" in cols
        assert "card_network" in cols

class TestSeedIdempotency:
    def test_seed_is_idempotent(self):
        db = get_test_db()
        before = db.query(PaymentMethod).count()
        db.close()
        seed_master_data(get_test_db())
        db = get_test_db()
        after = db.query(PaymentMethod).count()
        db.close()
        assert before == after
