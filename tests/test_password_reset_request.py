"""Password reset request flow: submit + admin list/resolve."""
from fastapi.testclient import TestClient

from app.database.db import Base, engine
from app.main import app
from app.models.models import PasswordResetRequest


def _client():
    Base.metadata.create_all(bind=engine)
    return TestClient(app, follow_redirects=False)


def test_forgot_password_submit_records_request():
    client = _client()
    r = client.get("/forgot-password")
    csrf = r.cookies.get("pf_csrf", "")
    r = client.post("/forgot-password", data={
        "username": "someuser", "csrf_token": csrf,
    })
    assert r.status_code == 303
    assert r.headers["location"].endswith("/forgot-password?sent=1")


def test_admin_sees_and_resolves_request():
    from app.database.db import SessionLocal
    from app.services.users import create_user
    db = SessionLocal()
    try:
        admin = create_user(db, "resetadmin", "AdminPass123", is_admin=True)
        db.add(PasswordResetRequest(username="someuser"))
        db.commit()
    finally:
        db.close()

    client = _client()
    # login as admin
    r = client.get("/login")
    csrf = r.cookies.get("pf_csrf", "")
    r = client.post("/login", data={
        "username": "resetadmin", "password": "AdminPass123",
        "csrf_token": csrf, "next": "",
    })
    # admin dashboard shows pending notice
    r = client.get("/admin")
    assert r.status_code == 200
    assert "permintaan reset password" in r.text

    r = client.get("/admin/reset-requests")
    assert r.status_code == 200
    assert "someuser" in r.text

    csrf = r.cookies.get("pf_csrf", "")
    rid = db.query(PasswordResetRequest).first().id
    r = client.post(f"/admin/reset-requests/{rid}/resolve", data={"csrf_token": csrf})
    assert r.status_code == 303

    db = SessionLocal()
    try:
        assert db.query(PasswordResetRequest).first().status == "resolved"
    finally:
        db.close()


def test_forgot_password_requires_csrf():
    client = _client()
    r = client.post("/forgot-password", data={"username": "x"})
    assert r.status_code == 303
    assert r.headers["location"].endswith("/forgot-password?error=1")
