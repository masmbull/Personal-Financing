"""Tests for the admin login-as-user (impersonation) support feature."""
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.test_admin import create_user, _login, _fresh_client
from app.models.models import User


class TestAdminImpersonation:
    def _client_as_admin(self, db: Session, username: str = "boss") -> TestClient:
        client = _fresh_client()
        create_user(db, username, is_admin=True)
        _login(client, username)
        return client

    def _admin_csrf(self, client: TestClient) -> str:
        client.get("/admin/users")  # primes pf_csrf cookie + token
        return client.cookies.get("pf_csrf", "")

    def test_users_page_requires_auth(self):
        client = _fresh_client()
        r = client.get("/admin/users", follow_redirects=False)
        assert r.status_code == 303
        assert "/login" in r.headers["location"]

    def test_users_page_requires_admin(self, db: Session):
        create_user(db, "regular")
        client = _fresh_client()
        _login(client, "regular")
        r = client.get("/admin/users", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/"

    def test_users_page_lists_users(self, db: Session):
        client = self._client_as_admin(db)
        create_user(db, "victim_one")
        create_user(db, "victim_two")
        r = client.get("/admin/users")
        assert r.status_code == 200
        assert "victim_one" in r.text
        assert "victim_two" in r.text
        # Per-user support entry point is rendered for non-admin active users.
        assert "/impersonate" in r.text

    def test_admin_can_impersonate_user(self, db: Session):
        client = self._client_as_admin(db)
        target = create_user(db, "victim")
        self._admin_csrf(client)
        # Confirmation page renders.
        r = client.get(f"/admin/users/{target.id}/impersonate")
        assert r.status_code == 200
        m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
        assert m
        confirm_csrf = m.group(1)
        # Switch session to the victim.
        r = client.post(f"/admin/users/{target.id}/impersonate",
                        data={"csrf_token": confirm_csrf},
                        follow_redirects=False)
        assert r.status_code == 303
        # Now browsing as the victim. The victim has no accounts, so GET /
        # redirects to /setup; the followed page (which uses base.html) shows
        # the username in the auth-bar and the support banner.
        r = client.get("/", follow_redirects=True)
        assert r.status_code == 200
        assert "victim" in r.text
        assert "Mode dukungan" in r.text
        # Return to admin.
        csrf2 = client.cookies.get("pf_csrf", "")
        r = client.post("/admin/stop-impersonating",
                        data={"csrf_token": csrf2}, follow_redirects=False)
        assert r.status_code == 303
        r = client.get("/", follow_redirects=True)
        assert "Mode dukungan" not in r.text

    def test_impersonate_requires_csrf(self, db: Session):
        client = self._client_as_admin(db)
        target = create_user(db, "victim")
        r = client.post(f"/admin/users/{target.id}/impersonate",
                        data={"csrf_token": ""})
        assert r.status_code == 303
        assert "error=1" in r.headers["location"]
        # Still the admin, not impersonating.
        r = client.get("/")
        assert "Mode dukungan" not in r.text

    def test_cannot_impersonate_self(self, db: Session):
        client = self._client_as_admin(db, "boss")
        boss = db.query(User).filter(User.username == "boss").first()
        csrf = self._admin_csrf(client)
        r = client.post(f"/admin/users/{boss.id}/impersonate",
                        data={"csrf_token": csrf})
        assert r.status_code == 303
        assert "error=6" in r.headers["location"]

    def test_cannot_impersonate_other_admin(self, db: Session):
        client = self._client_as_admin(db)
        other = create_user(db, "other_admin", is_admin=True)
        csrf = self._admin_csrf(client)
        r = client.post(f"/admin/users/{other.id}/impersonate",
                        data={"csrf_token": csrf})
        assert r.status_code == 303
        assert "error=4" in r.headers["location"]

    def test_cannot_impersonate_inactive_user(self, db: Session):
        client = self._client_as_admin(db)
        inactive = create_user(db, "ghost", is_active=False)
        csrf = self._admin_csrf(client)
        r = client.post(f"/admin/users/{inactive.id}/impersonate",
                        data={"csrf_token": csrf})
        assert r.status_code == 303
        assert "error=5" in r.headers["location"]

    def test_stop_impersonating_when_not_impersonating_is_noop(self, db: Session):
        client = self._client_as_admin(db)
        self._admin_csrf(client)
        csrf = client.cookies.get("pf_csrf", "")
        r = client.post("/admin/stop-impersonating", data={"csrf_token": csrf})
        assert r.status_code == 303
        assert r.headers["location"] == "/"
