"""Tests for financial institutions and e-wallet providers."""
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.models import Account, AccountType, FinancialInstitution, EWalletProvider
from tests.conftest import default_user_id, get_test_db

client = TestClient(app)


# ==================== INSTITUTION CRUD ====================


def test_list_institutions():
    """List all financial institutions (global, user_id=NULL)."""
    db = get_test_db()
    resp = client.get("/api/v1/institutions")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] > 0
    # Should have canonical banks
    banks = [i["code"] for i in data["items"]]
    assert "BCA" in banks
    db.close()


def test_create_institution_own():
    """Authenticated user can create own (user-owned) institution."""
    db = get_test_db()
    resp = client.post("/api/v1/institutions", json={
        "code": "OWN_BANK",
        "legal_name": "My Own Bank",
        "short_name": "OwnBank",
        "institution_type": "OTHER_LICENSED",  # Use valid default
    })
    assert resp.status_code == 201, f"Got {resp.status_code}: {resp.json()}"
    data = resp.json()
    assert data["code"] == "OWN_BANK"
    db.close()


def test_get_institution():
    """Fetch a single institution by id."""
    db = get_test_db()
    inst = db.query(FinancialInstitution).first()
    if not inst:
        db.close()
        return  # No institutions in test DB
    resp = client.get(f"/api/v1/institutions/{inst.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == inst.code
    assert data["legal_name"] == inst.legal_name
    db.close()


def test_account_institution_fk_validation():
    """Account.institution_id must reference a valid institution."""
    uid = default_user_id()
    db = get_test_db()
    inst = db.query(FinancialInstitution).first()
    if not inst:
        db.close()
        return
    # Valid: create account with valid institution_id
    acc = Account(
        name="Test Bank Account",
        user_id=uid,
        type=AccountType.BANK,
        initial_balance=100_000,
        current_balance=100_000,
        institution_id=inst.id,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    assert acc.institution_id == inst.id
    # Clean up
    db.delete(acc)
    db.commit()
    db.close()


# ==================== E-WALLET PROVIDER CRUD ====================


def test_list_ewallet_providers():
    """List all e-wallet providers (global)."""
    db = get_test_db()
    resp = client.get("/api/v1/ewallet-providers")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] > 0
    # Should have canonical providers
    codes = [p["code"] for p in data["items"]]
    assert "GOPAY" in codes or "OVO" in codes or "DANA" in codes
    db.close()


def test_create_ewallet_provider_own():
    """Authenticated user can create own e-wallet provider."""
    db = get_test_db()
    resp = client.post("/api/v1/ewallet-providers", json={
        "code": "OWN_WALLET",
        "legal_name": "My Own Wallet",
        "short_name": "OwnWallet",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["code"] == "OWN_WALLET"
    db.close()


def test_get_ewallet_provider():
    """Fetch a single e-wallet provider by id."""
    db = get_test_db()
    provider = db.query(EWalletProvider).first()
    if not provider:
        db.close()
        return
    resp = client.get(f"/api/v1/ewallet-providers/{provider.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == provider.code
    assert data["legal_name"] == provider.legal_name
    db.close()
