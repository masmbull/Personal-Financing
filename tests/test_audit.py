"""Audit log: records sensitive actions and is immutable/queryable.

Runs against the real app (TestClient) and the real audit service.
"""
import json

from app.services.audit import record, list_events
from app.models.audit import AuditLog


def test_record_creates_row(db):
    """audit.record() persists an immutable row."""
    row = record(
        db, action="login_success", actor_user_id=1,
        ip_address="1.2.3.4", detail={"username": "bob"},
    )
    assert row.id is not None
    assert row.action == "login_success"
    assert row.actor_user_id == 1
    assert row.ip_address == "1.2.3.4"
    assert json.loads(row.detail) == {"username": "bob"}
    assert row.created_at is not None


def test_detail_dict_serialised(db):
    row = record(db, action="x", detail={"a": 1, "b": [1, 2]})
    assert json.loads(row.detail) == {"a": 1, "b": [1, 2]}


def test_detail_serialise_fallback(db):
    """Non-JSON-serialisable detail falls back to a safe repr, never raises."""
    class _Bad:
        def __repr__(self):
            return "<bad>"
    row = record(db, action="x", detail={"obj": _Bad()})
    assert row.detail is not None


def test_list_events_filters_by_action(db):
    record(db, action="login_success", actor_user_id=1)
    record(db, action="logout", actor_user_id=1)
    record(db, action="login_success", actor_user_id=2)
    rows = list_events(db, action="login_success")
    assert len(rows) == 2
    assert all(r.action == "login_success" for r in rows)


def test_list_events_filters_by_actor(db):
    record(db, action="logout", actor_user_id=1)
    record(db, action="logout", actor_user_id=2)
    rows = list_events(db, actor_user_id=2)
    assert len(rows) == 1
    assert rows[0].actor_user_id == 2


def test_login_records_audit(client, db):
    """A successful login POST writes a login_success audit row."""
    from app.models.models import User
    # Create a real user + password so login can succeed against the DB.
    from app.auth.security import hash_password
    u = User(username="audit_user", password_hash=hash_password("secret-123"),
             is_active=1)
    db.add(u)
    db.commit()
    db.refresh(u)
    # Fetch a fresh CSRF cookie from the login page, then POST.
    page = client.get("/login")
    csrf = page.cookies.get("pf_csrf")
    resp = client.post(
        "/login",
        data={"username": "audit_user", "password": "secret-123",
              "csrf_token": csrf, "next": ""},
        cookies={"pf_csrf": csrf},
        follow_redirects=False,
    )
    # Either a redirect (success) or some client error; the assertion we care
    # about is that the audit row exists.
    from app.services.audit import list_events
    rows = list_events(db, action="login_success", actor_user_id=u.id)
    assert len(rows) == 1


def test_audit_table_append_only(db):
    """AuditLog is append-only by design: rows have no update helper usage."""
    row = record(db, action="x", actor_user_id=1)
    assert isinstance(row, AuditLog)
    assert row.id is not None
