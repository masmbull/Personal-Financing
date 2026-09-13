"""Audit decorator integration: mutating endpoints append an audit row."""
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, CurrentUser
from app.main import app
from app.models.audit import AuditLog
from app.models.models import User
from tests.conftest import DEFAULT_USER, TestingSessionLocal


@pytest.fixture
def client():
    db = TestingSessionLocal()
    bob = db.query(User).filter_by(username=DEFAULT_USER).first()
    db.close()

    def _user():
        return CurrentUser(id=bob.id, username=DEFAULT_USER, display_name="Bob")

    app.dependency_overrides[get_current_user] = _user
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


def _row_count(action):
    db = TestingSessionLocal()
    try:
        return db.query(AuditLog).filter(AuditLog.action == action).count()
    finally:
        db.close()


def test_transaction_create_records_audit(client):
    before = _row_count("transaction_create")
    r = client.post(
        "/api/v1/transactions",
        json={"type": "EXPENSE", "amount": "50000", "account_id": 1, "category_id": 1,
              "description": "audit test"},
    )
    assert r.status_code == 201, r.text
    assert _row_count("transaction_create") == before + 1


def test_account_create_and_delete_records_audit(client):
    r = client.post(
        "/api/v1/accounts",
        json={"name": "Audit Acc", "type": "CASH", "initial_balance": "0"},
    )
    assert r.status_code == 201, r.text
    acc_id = r.json()["id"]
    assert _row_count("account_create") >= 1

    r = client.delete(f"/api/v1/accounts/{acc_id}")
    assert r.status_code == 204
    assert _row_count("account_delete") >= 1


def test_budget_and_savings_endpoints_audit(client):
    r = client.post(
        "/api/v1/budgets",
        json={"category_id": 1, "amount": "100000", "month": 1, "year": 2030},
    )
    assert r.status_code == 201, r.text
    assert _row_count("budget_create") >= 1

    r = client.post(
        "/api/v1/savings",
        json={"name": "Tabungan", "target_amount": "1000000"},
    )
    assert r.status_code == 201, r.text
    assert _row_count("savings_goal_create") >= 1


def test_list_endpoint_does_not_audit(client):
    before = _row_count("account_list")
    client.get("/api/v1/accounts")
    assert _row_count("account_list") == before


def test_audit_row_captures_actor_and_entity(client):
    r = client.post(
        "/api/v1/categories",
        json={"name": "Audit Cat", "type": "EXPENSE", "icon": "X"},
    )
    assert r.status_code == 201, r.text
    cat_id = r.json()["id"]
    db = TestingSessionLocal()
    try:
        row = db.query(AuditLog).filter(
            AuditLog.action == "category_create",
            AuditLog.entity_id == cat_id,
        ).first()
        assert row is not None
        assert row.actor_user_id is not None
        assert row.entity_type == "category"
    finally:
        db.close()
