"""Self-service change-password flow regression tests."""
import re

from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.main import app
from app.models.models import User
from tests.conftest import DEFAULT_USER, TEST_PASSWORD, TEST_PASSWORD_HASH

from app.auth.security import verify_password


def _fresh_client() -> TestClient:
    app.dependency_overrides.pop(get_current_user, None)
    return TestClient(app, follow_redirects=False)


def _csrf(client, path="/settings"):
    r = client.get(path)
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    assert m, "csrf_token not found"
    return m.group(1)


def _login(client, username, password):
    return client.post("/login", data={
        "username": username, "password": password,
        "csrf_token": _csrf(client, "/login"), "next": "/",
    })


def _new_user(username):
    from app.database.db import SessionLocal
    db = SessionLocal()
    u = User(username=username, password_hash=TEST_PASSWORD_HASH, is_active=1)
    db.add(u)
    db.commit()
    db.refresh(u)
    uid = u.id
    db.close()
    return uid


def test_settings_page_requires_login():
    c = _fresh_client()
    r = c.get("/settings")
    assert r.status_code in (303, 307)
    assert "/login" in r.headers.get("location", "")


def test_change_password_success_and_revokes_others():
    c = _fresh_client()
    _login(c, DEFAULT_USER, TEST_PASSWORD)
    token = _csrf(c)
    r = c.post("/settings/change-password", data={
        "current_password": TEST_PASSWORD,
        "new_password": "BrandNewPass99",
        "confirm_password": "BrandNewPass99",
        "csrf_token": token,
    })
    assert r.status_code in (303, 307)
    assert "done=1" in r.headers.get("location", "")

    # New password verified, old rejected.
    from app.database.db import SessionLocal
    db = SessionLocal()
    u = db.query(User).filter(User.username == DEFAULT_USER).first()
    assert verify_password("BrandNewPass99", u.password_hash)
    assert not verify_password(TEST_PASSWORD, u.password_hash)
    db.close()

    # Can log in with the new password.
    c2 = _fresh_client()
    login = _login(c2, DEFAULT_USER, "BrandNewPass99")
    assert login.status_code in (303, 307)


def test_change_password_wrong_current():
    c = _fresh_client()
    _login(c, DEFAULT_USER, TEST_PASSWORD)
    token = _csrf(c)
    r = c.post("/settings/change-password", data={
        "current_password": "wrongpass",
        "new_password": "BrandNewPass99",
        "confirm_password": "BrandNewPass99",
        "csrf_token": token,
    })
    assert "error=current" in r.headers.get("location", "")


def test_change_password_mismatch():
    c = _fresh_client()
    _login(c, DEFAULT_USER, TEST_PASSWORD)
    token = _csrf(c)
    r = c.post("/settings/change-password", data={
        "current_password": TEST_PASSWORD,
        "new_password": "BrandNewPass99",
        "confirm_password": "Different99",
        "csrf_token": token,
    })
    assert "error=mismatch" in r.headers.get("location", "")


def test_change_password_weak_rejected():
    c = _fresh_client()
    _login(c, DEFAULT_USER, TEST_PASSWORD)
    token = _csrf(c)
    r = c.post("/settings/change-password", data={
        "current_password": TEST_PASSWORD,
        "new_password": "short",
        "confirm_password": "short",
        "csrf_token": token,
    })
    assert "error=weak" in r.headers.get("location", "")
