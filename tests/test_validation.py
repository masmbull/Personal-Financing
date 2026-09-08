"""Tests for input validation across all layers.

Covers amount boundaries (zero/negative/rejected), required-field
enforcement, authorization checks, and CSRF protection on state-changing
form posts.
"""
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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

    def test_admin_make_admin_requires_valid_csrf(self, db: Session):
        """A forged CSRF token must block the action even for an authenticated admin.

        The previous version raw-POSTed /login with no CSRF token, so the login
        never set a session and the admin POST was rejected by the AUTH gate (not
        the CSRF check) - the 303 assertion passed for the wrong reason. Here we
        log in for real (which itself requires a valid CSRF token), then POST the
        admin action with a forged token, so only the CSRF check can reject it.
        """
        import re

        from app.api.deps import get_current_user
        from app.auth.security import hash_password

        admin = User(username="csrfadmin", password_hash=hash_password("p"),
                     is_active=1, is_admin=1)
        victim = User(username="csrfvictim", password_hash=hash_password("p"),
                      is_active=1)
        db.add_all([admin, victim])
        db.commit()
        db.refresh(victim)

        # Use REAL auth (drop the conftest get_current_user override) so the
        # session cookie - not the test override - decides the request identity.
        app.dependency_overrides.pop(get_current_user, None)
        real_client = TestClient(app, follow_redirects=False)

        # Establish an authenticated admin session via the real login flow,
        # which requires a valid CSRF token of its own.
        m = re.search(r'name="csrf_token" value="([^"]+)"',
                      real_client.get("/login").text)
        login_token = m.group(1) if m else ""
        login_resp = real_client.post(
            "/login",
            data={"username": "csrfadmin", "password": "p",
                  "csrf_token": login_token},
            follow_redirects=False,
        )
        assert login_resp.status_code == 303, \
            f"login should succeed with valid CSRF; got {login_resp.status_code}"

        # Now POST the admin action with a FORGED CSRF token. Auth is valid, so
        # the only gate that can reject it is the CSRF check.
        resp = real_client.post(
            f"/admin/users/{victim.id}/make-admin",
            data={"csrf_token": "forged"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        db.refresh(victim)
        assert victim.is_admin == 0, \
            "victim must NOT be promoted when the CSRF token is forged"


class TestAdminModel:
    """Validate the User model carries admin/active flags."""

    def test_user_model_has_is_admin(self, db):
        u = User(username="testadmin", password_hash="x", is_active=1, is_admin=1)
        db.add(u)
        db.commit()
        db.refresh(u)
        assert u.is_admin == 1