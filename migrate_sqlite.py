"""SQLite migration helper: adds columns introduced by the finance upgrade
to an existing database without losing data.

Usage:
    python migrate_sqlite.py

Safe to run multiple times - each ALTER TABLE is skipped if the column
already exists. New tables are created automatically by create_all.
"""
import sqlite3

from sqlalchemy import inspect, text

from app.database.db import engine, Base
from app.models import models  # noqa: F401 - ensure models are registered


# table -> list of (column_name, column_type_sql)
NEW_COLUMNS = {
    "accounts": [
        ("institution", "VARCHAR(100)"),
        ("account_number", "VARCHAR(50)"),
        ("color", "VARCHAR(7)"),
        ("icon", "VARCHAR(10)"),
    ],
    "categories": [
        ("group", "VARCHAR(50)"),
        ("icon", "VARCHAR(10)"),
        ("is_default", "INTEGER"),
    ],
    "transactions": [
        ("merchant", "VARCHAR(200)"),
        ("notes", "TEXT"),
    ],
    "receipts": [
        ("transaction_id", "INTEGER"),
        ("file_hash", "VARCHAR(64)"),
        ("ocr_data", "TEXT"),
    ],
}


def get_existing_columns(conn, table):
    result = conn.execute(text(f"PRAGMA table_info({table})"))
    return {row[1] for row in result}


def table_exists(conn, table):
    result = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
        {"t": table},
    )
    return result.first() is not None


def main():
    # 1. Create any missing tables (new models)
    Base.metadata.create_all(bind=engine)

    # 2. Add missing columns to existing tables
    with engine.connect() as conn:
        migrated = []
        for table, columns in NEW_COLUMNS.items():
            if not table_exists(conn, table):
                continue
            existing = get_existing_columns(conn, table)
            for col_name, col_type in columns:
                if col_name not in existing:
                    stmt = f'ALTER TABLE {table} ADD COLUMN "{col_name}" {col_type}'
                    print(f"  + {stmt}")
                    conn.execute(text(stmt))
                    migrated.append(f"{table}.{col_name}")
                else:
                    print(f"  . {table}.{col_name} already exists")
        if migrated:
            conn.commit()

    print("\nMigration complete.")
    if not migrated:
        print("No changes were needed.")


if __name__ == "__main__":
    main()
