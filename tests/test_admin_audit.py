"""Admin audit endpoints + admin-action audit hooks (real auth)."""
import re

from app.main import app
from app.models.models import User
from app.auth.security import hash_password
from app.services.audit import list_events
from app.api.deps import get_current_user


def _fresh_client():
    app.dependency_overrides.pop(get_current_user, None)
    from fastapi.testclient import TestClient
    return TestClient(app, follow_redirects=False)


def _csrf(client):
    r = client.get("/login")
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    return m.group(1) if m else ""


def _login(client, username, password="password123"):
    tok = _csrf(client)
    return client.post(
        "/login", data={"username": username, "password": password,
                        "csrf_token": tok},
        follow_redirects=False,
    )


def test_make_admin_records_audit(db):
    admin = User(username="boss", password_hash=hash_password("password123"),
                 is_active=1, is_admin=1)
    target = User(username="staff", password_hash=hash_password("password123"),
                  is_active=1, is_admin=0)
    db.add_all([admin, target])
    db.commit()
    db.refresh(admin)
    db.refresh(target)

    client = _fresh_client()
    _login(client, "boss")

    # Promote staff via API.
    resp = client.post(f"/api/v1/admin/users/{target.id}/make-admin")
    assert resp.status_code == 200

    rows = list_events(db, action="admin_make_admin", actor_user_id=admin.id)
    assert len(rows) == 1
    assert rows[0].target_user_id == target.id


def test_audit_log_endpoint_requires_admin(db):
    u = User(username="plain", password_hash=hash_password("password123"),
             is_active=1, is_admin=0)
    db.add(u)
    db.commit()
    db.refresh(u)
    client = _fresh_client()
    _login(client, "plain")
    # Non-admin cannot read the audit log (403 from NotAuthorized handler).
    resp = client.get("/api/v1/admin/audit-log")
    assert resp.status_code in (401, 403)


def test_audit_log_endpoint_returns_rows(db):
    admin = User(username="boss2", password_hash=hash_password("password123"),
                 is_active=1, is_admin=1)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    from app.services.audit import record
    record(db, action="login_success", actor_user_id=admin.id)

    client = _fresh_client()
    _login(client, "boss2")
    resp = client.get("/api/v1/admin/audit-log")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(i["action"] == "login_success" for i in items)


def test_audit_log_html_page_requires_admin(db):
    u = User(username="plain2", password_hash=hash_password("password123"),
             is_active=1, is_admin=0)
    db.add(u)
    db.commit()
    db.refresh(u)
    client = _fresh_client()
    _login(client, "plain2")
    resp = client.get("/admin/audit-log", follow_redirects=False)
    # Non-admin is redirected away from the admin panel.
    assert resp.status_code in (302, 303)
    assert "/admin/audit-log" not in (resp.headers.get("location", ""))


def test_audit_log_html_page_renders_for_admin(db):
    admin = User(username="boss3", password_hash=hash_password("password123"),
                 is_active=1, is_admin=1)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    from app.services.audit import record
    record(db, action="login_success", actor_user_id=admin.id,
           entity_type="account", entity_id=7)

    client = _fresh_client()
    _login(client, "boss3")
    resp = client.get("/admin/audit-log")
    assert resp.status_code == 200
    assert "login_success" in resp.text
    assert "account #7" in resp.text


def test_audit_log_html_pagination_links(db):
    admin = User(username="boss4", password_hash=hash_password("password123"),
                 is_active=1, is_admin=1)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    from app.services.audit import record
    for _ in range(55):
        record(db, action="tick", actor_user_id=admin.id)

    client = _fresh_client()
    _login(client, "boss4")
    first = client.get("/admin/audit-log")
    assert first.status_code == 200
    assert "Berikutnya" in first.text
    second = client.get("/admin/audit-log?page=2")
    assert second.status_code == 200
    assert "Sebelumnya" in second.text

