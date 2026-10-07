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
from sqlalchemy.pool import NullPool

from app.migrations import run_institution_fk_migration, _MARKER_TABLE
from app.migrations import run_category_slug_unique_migration
from app.migrations import backup_database, rotate_backups


_LEGACY_CATEGORIES_DDL = """
CREATE TABLE categories (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(20) NOT NULL,
    slug VARCHAR(100)
);
"""


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
    # StaticPool maintains a single connection so the in-memory SQLite database
    # is shared across all calls to engine.connect() / engine.begin().
    # NullPool would create a fresh in-memory DB per connection, breaking tests
    # that create a table in one connection and query it from another.
    from sqlalchemy.pool import StaticPool
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    return eng


def _dispose_engine(eng):
    """Dispose of an engine created by _fresh_engine, closing all connections."""
    eng.dispose()


def _columns(engine, table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_institution_fk_migration_adds_missing_column_to_legacy_db():
    """Legacy accounts (no institution_id) -> migration adds the FK column."""
    eng = _fresh_engine()
    try:
        with eng.begin() as conn:
            conn.execute(text(_LEGACY_ACCOUNTS_DDL))
        assert "institution_id" not in _columns(eng, "accounts")

        changed = run_institution_fk_migration(eng)

        assert changed is True
        assert "institution_id" in _columns(eng, "accounts")
    finally:
        eng.dispose()


def test_institution_fk_migration_is_noop_on_fresh_db():
    """DB that already has institution_id: migration is a no-op (returns False)."""
    eng = _fresh_engine()
    try:
        with eng.begin() as conn:
            conn.execute(text(_LEGACY_ACCOUNTS_DDL))
            conn.execute(text(
                "ALTER TABLE accounts ADD COLUMN institution_id INTEGER"
            ))
        assert "institution_id" in _columns(eng, "accounts")

        changed = run_institution_fk_migration(eng)

        assert changed is False
    finally:
        eng.dispose()


def test_institution_fk_migration_is_idempotent_repeat_runs():
    """Run the migration 3x; only the first changes the schema; rest are no-op."""
    eng = _fresh_engine()
    try:
        with eng.begin() as conn:
            conn.execute(text(_LEGACY_ACCOUNTS_DDL))

        first = run_institution_fk_migration(eng)
        second = run_institution_fk_migration(eng)
        third = run_institution_fk_migration(eng)

        assert first is True
        assert second is False
        assert third is False
        assert "institution_id" in _columns(eng, "accounts")
    finally:
        eng.dispose()


def test_institution_fk_migration_creates_index_on_institution_id():
    """Migration creates ix_accounts_institution_id for FK lookups."""
    eng = _fresh_engine()
    try:
        with eng.begin() as conn:
            conn.execute(text(_LEGACY_ACCOUNTS_DDL))

        run_institution_fk_migration(eng)

        indexes = {ix["name"] for ix in inspect(eng).get_indexes("accounts")}
        assert "ix_accounts_institution_id" in indexes
    finally:
        eng.dispose()


def test_institution_fk_migration_records_marker_exactly_once():
    """_pf_migrations marker is INSERT OR IGNORE: marker exists once even
    after multiple runs (proves no duplicate, no error)."""
    eng = _fresh_engine()
    try:
        with eng.begin() as conn:
            conn.execute(text(_LEGACY_ACCOUNTS_DDL))

        run_institution_fk_migration(eng)
        run_institution_fk_migration(eng)

        with eng.connect() as conn:
            rows = conn.execute(text(
                f"SELECT name FROM {_MARKER_TABLE} WHERE name='institution_fk'"
            )).fetchall()
        assert len(rows) == 1
    finally:
        eng.dispose()


def test_institution_fk_migration_preserves_existing_rows():
    """Existing account rows survive migration (non-destructive)."""
    eng = _fresh_engine()
    try:
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
    finally:
        eng.dispose()


def test_institution_fk_migration_safe_when_table_missing():
    """If accounts table doesn't exist yet, migration returns False cleanly."""
    eng = _fresh_engine()
    try:
        # No tables created at all
        assert "accounts" not in inspect(eng).get_table_names()

        changed = run_institution_fk_migration(eng)

        assert changed is False
    finally:
        eng.dispose()


def test_category_slug_unique_migration_adds_index():
    """Legacy categories without the unique index -> migration adds it."""
    eng = _fresh_engine()
    try:
        with eng.begin() as conn:
            conn.execute(text(_LEGACY_CATEGORIES_DDL))
            conn.execute(text(
                "INSERT INTO categories (id, name, type, slug) "
                "VALUES (1, 'Makanan', 'EXPENSE', 'food'), "
                "(2, 'Gaji', 'INCOME', 'salary')"
            ))
        assert "uq_categories_type_slug" not in {
            i["name"] for i in inspect(eng).get_indexes("categories")}

        changed = run_category_slug_unique_migration(eng)

        assert changed is True
        assert "uq_categories_type_slug" in {
            i["name"] for i in inspect(eng).get_indexes("categories")}
    finally:
        eng.dispose()


def test_category_slug_unique_migration_is_idempotent():
    """Second run is a no-op once the index exists."""
    eng = _fresh_engine()
    try:
        with eng.begin() as conn:
            conn.execute(text(_LEGACY_CATEGORIES_DDL))
        assert run_category_slug_unique_migration(eng) is True
        assert run_category_slug_unique_migration(eng) is False
    finally:
        eng.dispose()


def test_category_slug_unique_migration_skips_on_duplicates():
    """Duplicate (type, slug) rows -> index skipped rather than crash startup."""
    eng = _fresh_engine()
    try:
        with eng.begin() as conn:
            conn.execute(text(_LEGACY_CATEGORIES_DDL))
            conn.execute(text(
                "INSERT INTO categories (id, name, type, slug) "
                "VALUES (1, 'A', 'EXPENSE', 'dup'), (2, 'B', 'EXPENSE', 'dup')"
            ))
        changed = run_category_slug_unique_migration(eng)
        assert changed is False
        assert "uq_categories_type_slug" not in {
            i["name"] for i in inspect(eng).get_indexes("categories")}
    finally:
        eng.dispose()
def _file_engine(tmp_path):
    """A file-backed SQLite engine (backup needs a real file, not :memory:)."""
    db_file = tmp_path / "finance.db"
    eng = create_engine(f"sqlite:///{db_file}",
                        connect_args={"check_same_thread": False})
    return eng, db_file


def test_backup_database_writes_wal_safe_snapshot(tmp_path):
    """Snapshot copies committed data and is queryable standalone."""
    eng, db_file = _file_engine(tmp_path)
    try:
        with eng.begin() as conn:
            conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)"))
            conn.execute(text("INSERT INTO t (v) VALUES ('hello')"))

        dest = backup_database(eng, backup_dir=str(tmp_path / "backups"))

        assert dest is not None and dest.exists()
        import sqlite3 as _sqlite3
        check = _sqlite3.connect(str(dest))
        try:
            row = check.execute("SELECT v FROM t").fetchone()
        finally:
            check.close()
        assert row == ("hello",)  # snapshot is queryable, data intact
    finally:
        eng.dispose()


def test_backup_database_skips_memory_and_non_sqlite(tmp_path):
    """In-memory and non-SQLite engines are no-ops (return None)."""
    mem = _fresh_engine()
    try:
        assert backup_database(mem, backup_dir=str(tmp_path)) is None
    finally:
        mem.dispose()

    class _FakeUrl:
        def get_backend_name(self):
            return "postgresql"

    class _FakeEngine:
        url = _FakeUrl()

    assert backup_database(_FakeEngine(), backup_dir=str(tmp_path)) is None


def test_rotate_backups_keeps_newest(tmp_path):
    """Only the newest ``keep`` snapshots survive rotation."""
    for i in range(5):
        (tmp_path / f"finance_2020010{i}_000000.db.bak").write_text("x")
    rotate_backups(str(tmp_path), "finance", keep=2)
    left = sorted(p.name for p in tmp_path.glob("finance_*.db.bak"))
    assert left == ["finance_20200103_000000.db.bak",
                    "finance_20200104_000000.db.bak"]