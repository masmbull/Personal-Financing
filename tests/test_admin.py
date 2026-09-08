"""Tests for admin functionality."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.models import User
from app.auth.security import hash_password
import re


def create_user(db: Session, username: str, password: str = "password123",
                is_admin: bool = False, is_active: bool = True) -> User:
    """Helper to create a test user."""
    user = User(
        username=username,
        password_hash=hash_password(password),
        is_active=1 if is_active else 0,
        is_admin=1 if is_admin else 0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _csrf_from(client: TestClient) -> str:
    """Fetch a fresh CSRF token by priming the cookie via /login."""
    r = client.get("/login")
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    return m.group(1) if m else ""


def _login(client: TestClient, username: str, password: str = 'password123'):
    """POST /login with a valid CSRF token so the session cookie is set."""
    token = _csrf_from(client)
    return client.post("/login", data={
        "username": username, "password": password, "csrf_token": token,
    }, follow_redirects=False)


def _fresh_client() -> TestClient:
    """A client using the REAL get_current_user dependency (no override) and
    redirects NOT auto-followed, so admin API endpoints exercise actual auth.

    The shared conftest client is pre-authenticated as the default non-admin
    user via a dependency override; that override is reapplied by the autouse
    setup_db fixture at the start of every test, so popping it here only
    affects the calling test.
    """
    from app.api.deps import get_current_user
    from app.main import app
    app.dependency_overrides.pop(get_current_user, None)
    return TestClient(app, follow_redirects=False)


class TestAdminWebRoutes:
    """Tests for admin web routes (Jinja templates)."""

    def test_admin_dashboard_requires_auth(self, client: TestClient):
        """Anonymous users are redirected to login."""
        resp = client.get("/admin", follow_redirects=False)
        assert resp.status_code == 303
        assert "/login" in resp.headers["location"]

    def test_admin_dashboard_requires_admin(self, client: TestClient, db: Session):
        """Non-admin users are redirected to home."""
        user = create_user(db, "regular_user")
        _login(client, "regular_user")
        resp = client.get("/admin", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"

    def test_admin_dashboard_accessible_by_admin(self, client: TestClient, db: Session):
        """Admin users can access the dashboard."""
        admin = create_user(db, "admin_user", is_admin=True)
        _login(client, "admin_user")
        resp = client.get("/admin")
        assert resp.status_code == 200
        assert "Admin Panel" in resp.text

    def test_admin_dashboard_shows_users(self, client: TestClient, db: Session):
        """Admin dashboard shows all users."""
        admin = create_user(db, "admin_user", is_admin=True)
        user1 = create_user(db, "user_one")
        user2 = create_user(db, "user_two")
        _login(client, "admin_user")
        resp = client.get("/admin")
        assert resp.status_code == 200
        assert "user_one" in resp.text
        assert "user_two" in resp.text

    def test_admin_make_admin(self, client: TestClient, db: Session):
        """Admin can make another user admin."""
        admin = create_user(db, "admin_user", is_admin=True)
        user = create_user(db, "regular_user")
        _login(client, "admin_user")
        # Get CSRF token from cookies
        client.get("/admin")  # refresh the CSRF cookie
        csrf_token = client.cookies.get("pf_csrf", "")
        resp = client.post(f"/admin/users/{user.id}/make-admin", data={
            "csrf_token": csrf_token,
        }, follow_redirects=False)
        assert resp.status_code == 303
        db.refresh(user)
        assert user.is_admin == 1

    def test_admin_revoke_admin(self, client: TestClient, db: Session):
        """Admin can revoke admin role from another user."""
        admin = create_user(db, "admin_user", is_admin=True)
        user = create_user(db, "other_admin", is_admin=True)
        _login(client, "admin_user")
        client.get("/admin")  # refresh the CSRF cookie
        csrf_token = client.cookies.get("pf_csrf", "")
        resp = client.post(f"/admin/users/{user.id}/revoke-admin", data={
            "csrf_token": csrf_token,
        }, follow_redirects=False)
        assert resp.status_code == 303
        db.refresh(user)
        assert user.is_admin == 0

    def test_admin_cannot_modify_self(self, client: TestClient, db: Session):
        """Admin cannot modify their own status."""
        admin = create_user(db, "admin_user", is_admin=True)
        _login(client, "admin_user")
        client.get("/admin")  # refresh the CSRF cookie
        csrf_token = client.cookies.get("pf_csrf", "")
        # Try to revoke own admin
        resp = client.post(f"/admin/users/{admin.id}/revoke-admin", data={
            "csrf_token": csrf_token,
        }, follow_redirects=False)
        assert resp.status_code == 303
        db.refresh(admin)
        assert admin.is_admin == 1  # Still admin

    def test_admin_deactivate_user(self, client: TestClient, db: Session):
        """Admin can deactivate a user."""
        admin = create_user(db, "admin_user", is_admin=True)
        user = create_user(db, "regular_user")
        _login(client, "admin_user")
        client.get("/admin")  # refresh the CSRF cookie
        csrf_token = client.cookies.get("pf_csrf", "")
        resp = client.post(f"/admin/users/{user.id}/deactivate", data={
            "csrf_token": csrf_token,
        }, follow_redirects=False)
        assert resp.status_code == 303
        db.refresh(user)
        assert user.is_active == 0

    def test_admin_activate_user(self, client: TestClient, db: Session):
        """Admin can activate a deactivated user."""
        admin = create_user(db, "admin_user", is_admin=True)
        user = create_user(db, "inactive_user", is_active=False)
        _login(client, "admin_user")
        client.get("/admin")  # refresh the CSRF cookie
        csrf_token = client.cookies.get("pf_csrf", "")
        resp = client.post(f"/admin/users/{user.id}/activate", data={
            "csrf_token": csrf_token,
        }, follow_redirects=False)
        assert resp.status_code == 303
        db.refresh(user)
        assert user.is_active == 1


class TestAdminAPIRoutes:
    """Tests for admin REST API routes.

    These use a fresh client with the real get_current_user dependency (no
    conftest override) so admin gating is exercised through actual sessions.
    """

    def test_api_admin_stats_requires_auth(self):
        """Anonymous users cannot access admin API."""
        client = _fresh_client()
        resp = client.get("/api/v1/admin/stats")
        assert resp.status_code == 401

    def test_api_admin_stats_requires_admin(self, db: Session):
        """Non-admin users cannot access admin API."""
        create_user(db, "regular_user")
        client = _fresh_client()
        _login(client, "regular_user")
        resp = client.get("/api/v1/admin/stats")
        assert resp.status_code == 403

    def test_api_admin_stats(self, db: Session):
        """Admin can get system stats."""
        admin = create_user(db, "admin_user", is_admin=True)
        create_user(db, "user_one")
        create_user(db, "user_two")
        client = _fresh_client()
        _login(client, "admin_user")
        resp = client.get("/api/v1/admin/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_users"] >= 3
        assert data["admin_count"] >= 1

    def test_api_admin_list_users(self, db: Session):
        """Admin can list all users."""
        admin = create_user(db, "admin_user", is_admin=True)
        user1 = create_user(db, "user_one")
        client = _fresh_client()
        _login(client, "admin_user")
        resp = client.get("/api/v1/admin/users")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        usernames = [u["username"] for u in data["items"]]
        assert "admin_user" in usernames
        assert "user_one" in usernames

    def test_api_admin_make_admin(self, db: Session):
        """Admin can make another user admin via API."""
        admin = create_user(db, "admin_user", is_admin=True)
        user = create_user(db, "regular_user")
        client = _fresh_client()
        _login(client, "admin_user")
        resp = client.post(f"/api/v1/admin/users/{user.id}/make-admin")
        assert resp.status_code == 200
        db.refresh(user)
        assert user.is_admin == 1

    def test_api_admin_cannot_modify_self(self, db: Session):
        """Admin cannot change their own admin status via API."""
        admin = create_user(db, "admin_user", is_admin=True)
        client = _fresh_client()
        _login(client, "admin_user")
        resp = client.post(f"/api/v1/admin/users/{admin.id}/make-admin")
        assert resp.status_code == 400
        db.refresh(admin)
        assert admin.is_admin == 1


class TestHelpPage:
    """Tests for the help/knowledge base page."""

    def test_help_page_accessible(self, client: TestClient):
        """Help page is accessible without authentication."""
        resp = client.get("/help")
        assert resp.status_code == 200
        assert "Pusat Bantuan" in resp.text

    def test_help_page_has_content(self, client: TestClient):
        """Help page contains expected sections."""
        resp = client.get("/help")
        assert resp.status_code == 200
        assert "Memulai" in resp.text
        assert "Transaksi" in resp.text
        assert "Hutang" in resp.text
        assert "Laporan" in resp.text
