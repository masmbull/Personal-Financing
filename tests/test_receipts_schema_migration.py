"""Regression: /receipts 500 on servers whose receipts table predates the
size_bytes/ocr_status/ocr_data/file_hash columns. The startup migration must
repair the old schema so the list page works again."""
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.migrations import run_receipts_columns_migration
from app.database.db import Base


MISSING_COLS = {
    "original_filename",
    "size_bytes",
    "ocr_status",
    "ocr_data",
    "transaction_id",
    "file_hash",
}


@pytest.fixture
def legacy_receipts_engine(tmp_path):
    """A SQLite DB whose receipts table has only the original columns.

    The full model metadata is created minus the receipts table, so the
    migration's `inspect` sees a real legacy table.
    """
    from sqlalchemy import create_engine
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    eng = create_engine(url)
    Base.metadata.create_all(bind=eng)
    with eng.begin() as conn:
        insp = inspect(conn)
        old = [
            c["name"] for c in insp.get_columns("receipts")
            if c["name"] not in MISSING_COLS
        ]
        # Rebuild receipts without the late-arrival columns.
        conn.execute(text("DROP TABLE receipts"))
        cols = ", ".join(f"{c} {t}" for c, t in [
            ("id", "INTEGER PRIMARY KEY"),
            ("user_id", "INTEGER"),
            ("stored_path", "VARCHAR(500) NOT NULL"),
            ("mime_type", "VARCHAR(100) NOT NULL"),
            ("created_at", "DATETIME"),
        ])
        conn.execute(text(f"CREATE TABLE receipts ({cols})"))
    yield eng
    eng.dispose()


def test_migration_adds_missing_receipt_columns(legacy_receipts_engine: Engine):
    from app.models.models import Receipt
    # Sanity: the model still expects the columns we are about to add.
    model_cols = {c.name for c in Receipt.__table__.columns}
    assert MISSING_COLS <= model_cols

    changed = run_receipts_columns_migration(legacy_receipts_engine)
    assert changed is True

    present = {c["name"] for c in inspect(legacy_receipts_engine).get_columns("receipts")}
    assert MISSING_COLS <= present

    # Idempotent: second run is a no-op.
    assert run_receipts_columns_migration(legacy_receipts_engine) is False


def test_receipts_list_works_after_migration():
    """End-to-end repair: test DB receives an old-shaped receipts table, the
    migration fixes it, and /receipts returns 200 (not 500)."""
    from fastapi.testclient import TestClient
    from app.main import app
    from tests.conftest import engine as test_engine
    from tests.conftest import DEFAULT_USER
    from app.database.db import SessionLocal
    from app.api.deps import get_current_user
    from app.models.models import User

    # 1) Rebuild the test DB's receipts table into the OLD minimal shape.
    with test_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS receipts"))
        conn.execute(text(
            "CREATE TABLE receipts ("
            "  id INTEGER PRIMARY KEY,"
            "  user_id INTEGER,"
            "  stored_path VARCHAR(500) NOT NULL,"
            "  mime_type VARCHAR(100) NOT NULL,"
            "  created_at DATETIME"
            ")"
        ))

    # 2) Seed a legacy-shaped receipt row for the default test user (bob).
    db = SessionLocal()
    uid = db.query(User).filter(User.username == DEFAULT_USER).first().id
    db.close()
    with test_engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO receipts (user_id, stored_path, mime_type, created_at) "
            "VALUES (:uid, 'x.png', 'image/png', datetime('now'))"
        ).bindparams(uid=uid))

    # 3) The startup migration repairs the schema, then the page must load.
    assert run_receipts_columns_migration(test_engine) is True

    from app.api.deps import CurrentUser
    app.dependency_overrides[get_current_user] = (
        lambda: CurrentUser(id=uid, username=DEFAULT_USER,
                            display_name=DEFAULT_USER))
    try:
        client = TestClient(app, follow_redirects=False)
        r = client.get("/receipts")
        assert r.status_code == 200
        assert "struk" in r.text.lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)

def test_migration_backfills_null_size_bytes_and_list_renders():
    """Server case: receipts table ALREADY has the late-arrival columns (so
    no ALTER is needed) but legacy rows hold NULL size_bytes/ocr_status.
    round(None / 1024) crashed GET /receipts with a 500.  The migration must
    backfill the NULLs and the list page must render."""
    from fastapi.testclient import TestClient
    from app.main import app
    from tests.conftest import engine as test_engine
    from tests.conftest import DEFAULT_USER
    from app.database.db import SessionLocal
    from app.api.deps import get_current_user, CurrentUser
    from app.models.models import User

    db = SessionLocal()
    uid = db.query(User).filter(User.username == DEFAULT_USER).first().id
    db.close()

    with test_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS receipts"))
        conn.execute(text(
            "CREATE TABLE receipts ("
            "  id INTEGER PRIMARY KEY,"
            "  user_id INTEGER,"
            "  original_filename VARCHAR(255),"
            "  stored_path VARCHAR(500) NOT NULL,"
            "  mime_type VARCHAR(100) NOT NULL,"
            "  size_bytes INTEGER,"
            "  ocr_status VARCHAR(16),"
            "  ocr_data TEXT,"
            "  transaction_id INTEGER,"
            "  file_hash VARCHAR(64),"
            "  created_at DATETIME"
            ")"
        ))
        conn.execute(text(
            "INSERT INTO receipts (user_id, stored_path, mime_type, "
            "size_bytes, ocr_status, created_at) "
            "VALUES (:uid, 'null-size.png', 'image/png', NULL, NULL, datetime('now'))"
        ).bindparams(uid=uid))

    # Columns exist -> no ALTER, but NULL backfill counts as a change.
    assert run_receipts_columns_migration(test_engine) is True
    with test_engine.begin() as conn:
        row = conn.execute(text(
            "SELECT size_bytes, ocr_status FROM receipts "
            "WHERE stored_path = 'null-size.png'"
        )).fetchone()
        assert row.size_bytes == 0
        assert row.ocr_status == "PENDING"

    # Idempotent: repaired rows are not rewritten on the next boot.
    assert run_receipts_columns_migration(test_engine) is False

    app.dependency_overrides[get_current_user] = (
        lambda: CurrentUser(id=uid, username=DEFAULT_USER,
                            display_name=DEFAULT_USER))
    try:
        client = TestClient(app, follow_redirects=False)
        r = client.get("/receipts")
        assert r.status_code == 200, r.text[:500]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
