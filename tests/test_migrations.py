"""Migration idempotency tests.

Each migration MUST be safe to run repeatedly on a database that already
has the new schema (no errors, no destructive changes). This file proves
that the Commit B institution-FK migration is idempotent and non-destructive.

Strategy:
- Use an in-memory SQLite engine to isolate from the shared test.db.
- Simulate a LEGACY accounts table (without the FK column), run the
  migration, assert the column is added.
- Run it again on the now-migrated DB, assert no-op (returns False) and
  no error.
- Assert the _pf_migrations marker is inserted exactly once (INSERT OR
  IGNORE).
"""
from sqlalchemy import create_engine, inspect, text

from app.migrations import run_institution_fk_migration, _MARKER_TABLE


_LEGACY_ACCOUNTS_DDL = """
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(20) NOT NULL,
    initial_balance INTEGER DEFAULT 0,
    current_balance INTEGER DEFAULT 0
);
"""


def _fresh_engine():
    return create_engine("sqlite:///:memory:",
                         connect_args={"check_same_thread": False})


def _columns(engine, table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_institution_fk_migration_adds_missing_column_to_legacy_db():
    """Legacy accounts (no institution_id) -> migration adds the FK column."""
    eng = _fresh_engine()
    with eng.begin() as conn:
        conn.execute(text(_LEGACY_ACCOUNTS_DDL))
    assert "institution_id" not in _columns(eng, "accounts")

    changed = run_institution_fk_migration(eng)

    assert changed is True
    assert "institution_id" in _columns(eng, "accounts")


def test_institution_fk_migration_is_noop_on_fresh_db():
    """DB that already has institution_id: migration is a no-op (returns False)."""
    eng = _fresh_engine()
    with eng.begin() as conn:
        conn.execute(text(_LEGACY_ACCOUNTS_DDL))
        conn.execute(text(
            "ALTER TABLE accounts ADD COLUMN institution_id INTEGER"
        ))
    assert "institution_id" in _columns(eng, "accounts")

    changed = run_institution_fk_migration(eng)

    assert changed is False


def test_institution_fk_migration_is_idempotent_repeat_runs():
    """Run the migration 3x; only the first changes the schema; rest are no-op."""
    eng = _fresh_engine()
    with eng.begin() as conn:
        conn.execute(text(_LEGACY_ACCOUNTS_DDL))

    first = run_institution_fk_migration(eng)
    second = run_institution_fk_migration(eng)
    third = run_institution_fk_migration(eng)

    assert first is True
    assert second is False
    assert third is False
    assert "institution_id" in _columns(eng, "accounts")


def test_institution_fk_migration_creates_index_on_institution_id():
    """Migration creates ix_accounts_institution_id for FK lookups."""
    eng = _fresh_engine()
    with eng.begin() as conn:
        conn.execute(text(_LEGACY_ACCOUNTS_DDL))

    run_institution_fk_migration(eng)

    indexes = {ix["name"] for ix in inspect(eng).get_indexes("accounts")}
    assert "ix_accounts_institution_id" in indexes


def test_institution_fk_migration_records_marker_exactly_once():
    """_pf_migrations marker is INSERT OR IGNORE: marker exists once even
    after multiple runs (proves no duplicate, no error)."""
    eng = _fresh_engine()
    with eng.begin() as conn:
        conn.execute(text(_LEGACY_ACCOUNTS_DDL))

    run_institution_fk_migration(eng)
    run_institution_fk_migration(eng)

    with eng.connect() as conn:
        rows = conn.execute(text(
            f"SELECT name FROM {_MARKER_TABLE} WHERE name='institution_fk'"
        )).fetchall()
    assert len(rows) == 1


def test_institution_fk_migration_preserves_existing_rows():
    """Existing account rows survive migration (non-destructive)."""
    eng = _fresh_engine()
    with eng.begin() as conn:
        conn.execute(text(_LEGACY_ACCOUNTS_DDL))
        conn.execute(text(
            "INSERT INTO accounts (id, user_id, name, type, initial_balance, "
            "current_balance) VALUES (1, 1, 'BCA', 'BANK', 1000000, 1000000)"
        ))

    run_institution_fk_migration(eng)

    with eng.connect() as conn:
        row = conn.execute(text(
            "SELECT id, name, current_balance, institution_id FROM accounts "
            "WHERE id = 1"
        )).first()
    assert row is not None
    assert row[1] == "BCA"
    assert row[2] == 1_000_000
    assert row[3] is None  # institution_id NULL (not set), row preserved


def test_institution_fk_migration_safe_when_table_missing():
    """If accounts table doesn't exist yet, migration returns False cleanly."""
    eng = _fresh_engine()
    # No tables created at all
    assert "accounts" not in inspect(eng).get_table_names()

    changed = run_institution_fk_migration(eng)

    assert changed is False