"""Tests for input validation across all layers.

Covers amount boundaries (zero/negative/rejected), required-field
enforcement, authorization checks, and CSRF protection on state-changing
form posts.
"""
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.main import app
from app.models.models import User

TODAY = "2025-01-15"


def _own_account_id(client: TestClient) -> int:
    items = client.get("/api/v1/accounts").json()["items"]
    return items[0]["id"]


class TestAmountValidation:
    """Validate amount boundaries are enforced (API layer)."""

    def test_zero_amount_rejected(self, client: TestClient):
        body = {
            "type": "EXPENSE", "amount": 0,
            "account_id": _own_account_id(client),
            "category_id": 1, "date": TODAY,
        }
        resp = client.post("/api/v1/transactions", json=body)
        assert resp.status_code in (400, 422)

    def test_negative_amount_rejected(self, client: TestClient):
        body = {
            "type": "EXPENSE", "amount": -500,
            "account_id": _own_account_id(client),
            "category_id": 1, "date": TODAY,
        }
        resp = client.post("/api/v1/transactions", json=body)
        assert resp.status_code in (400, 422)


class TestRequiredFields:
    """Validate required fields are enforced."""

    def test_missing_amount_rejected(self, client: TestClient):
        body = {
            "type": "EXPENSE",
            "account_id": _own_account_id(client),
            "category_id": 1, "date": TODAY,
        }
        resp = client.post("/api/v1/transactions", json=body)
        assert resp.status_code == 422

    def test_empty_body_rejected(self, client: TestClient):
        resp = client.post("/api/v1/transactions", json={})
        assert resp.status_code == 422


class TestAuthorization:
    """Validate authn/authz gates on protected endpoints."""

    def test_unauthenticated_api_requires_auth(self):
        saved = app.dependency_overrides.get(get_current_user)
        app.dependency_overrides.pop(get_current_user, None)
        try:
            c = TestClient(app, follow_redirects=False)
            r = c.get("/api/v1/transactions")
            assert r.status_code == 401
            assert r.json()["error"]["code"] == "UNAUTHENTICATED"
        finally:
            if saved is not None:
                app.dependency_overrides[get_current_user] = saved

    def test_non_admin_cannot_access_admin_api(self, client: TestClient):
        # The shared client runs as a non-admin default user.
        r = client.get("/api/v1/admin/stats")
        assert r.status_code == 403


class TestCsrf:
    """Validate CSRF protection on admin web POSTs."""

    def test_admin_make_admin_requires_valid_csrf(self, client: TestClient, db):
        from app.auth.security import hash_password

        admin = User(username="csrfadmin", password_hash=hash_password("p"),
                     is_active=1, is_admin=1)
        victim = User(username="csrfvictim", password_hash=hash_password("p"),
                      is_active=1)
        db.add_all([admin, victim])
        db.commit()
        db.refresh(victim)

        client.post("/login", data={"username": "csrfadmin", "password": "p"},
                    follow_redirects=False)
        resp = client.post(
            f"/admin/users/{victim.id}/make-admin",
            data={"csrf_token": "forged"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        db.refresh(victim)
        assert victim.is_admin == 0


class TestAdminModel:
    """Validate the User model carries admin/active flags."""

    def test_user_model_has_is_admin(self, db):
        u = User(username="testadmin", password_hash="x", is_active=1, is_admin=1)
        db.add(u)
        db.commit()
        db.refresh(u)
        assert u.is_admin == 1