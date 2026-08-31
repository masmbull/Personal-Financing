"""Idempotent SQLite migration for adding user-scoped columns.

Strategy:
* every startup runs ALTER TABLE ADD COLUMN user_id for any legacy table
  that lacks it (SQLite supports ADD COLUMN cheaply, no table rewrite)
* the model layer declares user_id NOT NULL for NEW databases; existing
  databases get a nullable column whose rows are assigned to the bootstrap
  admin user (when one exists) so no legacy data is ever dropped
* the migration records which tables were altered; legacy NULL rows are
  claimed ONLY when a bootstrap admin exists, and only on the first run
  (the marker table ``_pf_migrations`` makes the whole flow idempotent)
"""
import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

logger = logging.getLogger("app.migrations")

USER_OWNED_TABLES = [
    "accounts",
    "transactions",
    "debts",
    "debt_payments",
    "bills",
    "bill_payments",
    "savings_goals",
    "savings_goal_transactions",
    "budgets",
    "asset_records",
    "investments",
    "receipts",
    "net_worth_snapshots",
]

_MARKER_TABLE = "_pf_migrations"


def run_migrations(engine: Engine) -> bool:
    """Apply missing user_id columns. Returns True when legacy ALTERs ran."""
    insp = inspect(engine)
    altered = False
    with engine.begin() as conn:
        for table in USER_OWNED_TABLES:
            if table not in insp.get_table_names():
                continue
            cols = {c["name"] for c in insp.get_columns(table)}
            if "user_id" in cols:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER"))
            altered = True
            logger.info("Migrated %s: added user_id", table)
    if altered:
        with engine.begin() as conn:
            conn.execute(text(
                f"CREATE TABLE IF NOT EXISTS {_MARKER_TABLE}"
                " (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            ))
            conn.execute(text(
                f"INSERT OR IGNORE INTO {_MARKER_TABLE} (name, applied_at) "
                "VALUES ('legacy_user_id_migration', datetime('now'))"
            ))
    return altered


# Columns added to a pre-existing categories table by the hierarchy phase.
# SQLite supports ADD COLUMN cheaply with no table rewrite; existing rows
# keep their NULL parent_id (they stay valid root categories) and get a NULL
# slug (never overwritten by the idempotent seed, which matches on slug).
_CATEGORY_HIERARCHY_COLUMNS = ["parent_id", "slug"]


def run_category_hierarchy_migration(engine: Engine) -> bool:
    """Add category hierarchy columns (parent_id, slug) idempotently.

    No-op on fresh databases (create_all already defined them) and on
    repeated startups. Never drops or rewrites the table, so existing
    categories are preserved untouched.
    """
    insp = inspect(engine)
    if "categories" not in insp.get_table_names():
        return False
    existing = {c["name"] for c in insp.get_columns("categories")}
    missing = [c for c in _CATEGORY_HIERARCHY_COLUMNS if c not in existing]
    if not missing:
        return False
    with engine.begin() as conn:
        for col in missing:
            if col == "parent_id":
                conn.execute(text(
                    "ALTER TABLE categories ADD COLUMN parent_id INTEGER"
                ))
            else:
                conn.execute(text(
                    "ALTER TABLE categories ADD COLUMN slug VARCHAR(100)"
                ))
            logger.info("Migrated categories: added %s", col)
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_categories_parent_id "
            "ON categories(parent_id)"
        ))
        conn.execute(text(
            f"CREATE TABLE IF NOT EXISTS {_MARKER_TABLE}"
            " (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        ))
        conn.execute(text(
            f"INSERT OR IGNORE INTO {_MARKER_TABLE} (name, applied_at) "
            "VALUES ('category_hierarchy_migration', datetime('now'))"
        ))
    return True


def claim_legacy_rows(db: Session, user_id: int) -> None:
    """Assign legacy (user_id NULL) rows to a bootstrap owner.

    Runs only when legacy ALTERs happened and an admin exists. The seeded
    GLOBAL master accounts (user_id NULL, fresh install) are never claimed
    because on a fresh install no legacy migration ran. Only tables that
    actually exist are touched (partial legacy schemas stay safe).
    """
    existing = {
        r[0] for r in db.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ))
    }
    for table in USER_OWNED_TABLES:
        if table not in existing:
            continue
        db.execute(text(
            f"UPDATE {table} SET user_id = :uid WHERE user_id IS NULL"
        ), {"uid": user_id})
    db.commit()