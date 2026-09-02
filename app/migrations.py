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
    "bill_occurrences",
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

_BO_TABLE_SQL = (
    "CREATE TABLE IF NOT EXISTS bill_occurrences ("
    "id INTEGER NOT NULL PRIMARY KEY, "
    "user_id INTEGER NOT NULL, "
    "bill_id INTEGER NOT NULL, "
    "due_date DATE NOT NULL, "
    "amount INTEGER NOT NULL, "
    "status VARCHAR(20) NOT NULL, "
    "bill_payment_id INTEGER, "
    "created_at DATETIME"
    ")"
)


def run_bill_occurrence_migration(engine: Engine) -> bool:
    """Backfill the bill_occurrences table + unique index for EXISTING DBs.

    Fresh databases get the table (with UNIQUE(bill_id, due_date)) straight
    from create_all; this idempotent helper covers databases created before
    the scheduler existed. The unique index enforces the idempotency
    guarantee at the schema level.
    """
    insp = inspect(engine)
    if "bill_occurrences" not in insp.get_table_names():
        return False
    idx = {i["name"] for i in insp.get_indexes("bill_occurrences")}
    if "uq_bill_occurrence" in idx:
        return False
    with engine.begin() as conn:
        conn.execute(text(_BO_TABLE_SQL))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_bill_occurrence "
            "ON bill_occurrences(bill_id, due_date)"
        ))
        conn.execute(text(
            f"CREATE TABLE IF NOT EXISTS {_MARKER_TABLE}"
            " (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        ))
        conn.execute(text(
            f"INSERT OR IGNORE INTO {_MARKER_TABLE} (name, applied_at) "
            "VALUES ('bill_occurrence_table', datetime('now'))"
        ))
    return True


# ── Domain-expansion migration (merchant / payment-method / fuel / credit) ──
# Fresh databases get everything from create_all. Existing databases need the
# new columns on `transactions` and `accounts`, plus the new tables. All
# additions are non-destructive and idempotent.

_TRANSACTION_NEW_COLUMNS = [
    ("merchant_id", "INTEGER"),
    ("payment_method_id", "INTEGER"),
    ("fuel_product_id", "INTEGER"),
    ("quantity_liters", "FLOAT"),
    ("price_per_liter", "INTEGER"),
]

_ACCOUNT_NEW_COLUMNS = [
    ("credit_limit", "INTEGER"),
    ("statement_date", "INTEGER"),
    ("payment_due_day", "INTEGER"),
    ("interest_rate_pct", "FLOAT"),
    ("annual_fee", "INTEGER"),
    ("card_network", "VARCHAR(20)"),
]


def run_domain_expansion_migration(engine: Engine) -> bool:
    """Add domain columns idempotently. New tables are handled by create_all."""
    insp = inspect(engine)
    changed = False
    with engine.begin() as conn:
        if "transactions" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("transactions")}
            for name, typ in _TRANSACTION_NEW_COLUMNS:
                if name not in cols:
                    conn.execute(text(
                        f"ALTER TABLE transactions ADD COLUMN {name} {typ}"
                    ))
                    changed = True
                    logger.info("Migrated transactions: added %s", name)
            db_ok = "merchants" in insp.get_table_names()
            if db_ok:
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_transactions_merchant_id "
                    "ON transactions(merchant_id)"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_transactions_payment_method_id "
                    "ON transactions(payment_method_id)"
                ))
        if "accounts" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("accounts")}
            for name, typ in _ACCOUNT_NEW_COLUMNS:
                if name not in cols:
                    conn.execute(text(
                        f"ALTER TABLE accounts ADD COLUMN {name} {typ}"
                    ))
                    changed = True
                    logger.info("Migrated accounts: added %s", name)
        # Mark migration applied (for the log, not functionally required).
        conn.execute(text(
            f"CREATE TABLE IF NOT EXISTS {_MARKER_TABLE}"
            " (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        ))
        conn.execute(text(
            f"INSERT OR IGNORE INTO {_MARKER_TABLE} (name, applied_at) "
            "VALUES ('domain_expansion', datetime('now'))"
        ))
    return changed
