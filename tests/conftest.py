"""Shared test fixtures - ONE overridden database for every test module."""
import os
import shutil

# Point uploads at a scratch dir BEFORE app.config is imported anywhere.
os.environ.setdefault("RECEIPT_UPLOAD_DIR", "data/receipts_test")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.db import Base, get_db
from app.main import app
from app.models.models import Account, Category, AccountType, TransactionType

TEST_DB_URL = "sqlite:///./test.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

RECEIPT_TEST_DIR = "data/receipts_test"


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    shutil.rmtree(RECEIPT_TEST_DIR, ignore_errors=True)
    db = TestingSessionLocal()
    db.add(Category(name="Makan & Minum", type=TransactionType.EXPENSE, icon="X"))
    db.add(Category(name="Transportasi", type=TransactionType.EXPENSE, icon="X"))
    db.add(Category(name="Belanja", type=TransactionType.EXPENSE, icon="X"))
    db.add(Category(name="Gaji", type=TransactionType.INCOME, icon="Y"))
    db.add(Category(name="Freelance", type=TransactionType.INCOME, icon="Y"))
    db.add(Account(name="BCA", type=AccountType.BANK,
                   initial_balance=1_000_000, current_balance=1_000_000))
    db.add(Account(name="Cash", type=AccountType.CASH,
                   initial_balance=500_000, current_balance=500_000))
    db.add(Account(name="DANA", type=AccountType.E_WALLET,
                   initial_balance=0, current_balance=0))
    db.commit()
    db.close()
    yield
    shutil.rmtree(RECEIPT_TEST_DIR, ignore_errors=True)


def get_test_db():
    return TestingSessionLocal()


def valid_png_bytes(size: int = 8) -> bytes:
    """A tiny, genuinely decodable PNG (shifts by 1px from transparent to red)."""
    import struct
    import zlib

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    row = b"\x00" + (b"\xff\x00\x00\xff" * size)      # filter 0 + RGBA red
    raw = zlib.compress(row * size)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", raw) + chunk(b"IEND", b""))


PNG_BYTES = valid_png_bytes()
