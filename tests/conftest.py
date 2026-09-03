"""Shared test fixtures - ONE overridden database for every test module."""
import os
import shutil

# Point uploads at a scratch dir BEFORE app.config is imported anywhere.
os.environ.setdefault("RECEIPT_UPLOAD_DIR", "data/receipts_test")
# Fast test hashing - production default (600k iterations) is untouched.
os.environ.setdefault("PF_PBKDF2_ITERATIONS", "2000")
# Disable AI vision probe in tests (no Ollama available; would hang on timeout)
os.environ.setdefault("RECEIPT_AI_TIMEOUT_SEC", "1")
os.environ.setdefault("RECEIPT_AI_BASE_URL", "http://127.0.0.1:11435/v1")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import CurrentUser, get_current_user
from app.auth.security import hash_password
from app.database.db import Base, get_db
from app.main import app
from app.models.models import (
    Account, AccountType, Category, TransactionType, User,
)

# Disable AI vision probe network calls in tests (no Ollama available;
# would hang on TCP timeout even with short timeout). Patched before any
# receipt path can trigger build_scanner() -> _probe_service().
import app.services.receipt_ai as _ai_mod
_ai_mod._probe_service = lambda: None
_ai_mod.AIVisionReceiptScannerService.available = lambda self: False

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

# Default users used by the shared test client. PBKDF2 is intentionally
# hashed ONCE at import to keep the suite fast; real login flows in
# tests/test_auth.py re-verify against this same hash.
DEFAULT_USER = "bob"
DEFAULT_USER_2 = "alice"
TEST_PASSWORD = "testpass-123"
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)


def _default_user_ctx(user_id: int) -> CurrentUser:
    return CurrentUser(id=user_id, username=DEFAULT_USER,
                       display_name="Bob (test)")


def default_user_id() -> int:
    """Resolve the default test user's id against the CURRENT fresh DB."""
    db = TestingSessionLocal()
    uid = db.query(User).filter(User.username == DEFAULT_USER).first().id
    db.close()
    return uid


@pytest.fixture(autouse=True)
def setup_db():
    from app.rate_limit import RateLimitMiddleware
    RateLimitMiddleware.reset()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    shutil.rmtree(RECEIPT_TEST_DIR, ignore_errors=True)
    db = TestingSessionLocal()
    bob = User(username=DEFAULT_USER, password_hash=TEST_PASSWORD_HASH, is_active=1)
    alice = User(username=DEFAULT_USER_2, password_hash=TEST_PASSWORD_HASH, is_active=1)
    db.add_all([bob, alice])
    db.flush()
    _bob_id = bob.id  # capture before commit/close; ORM attrs die with the session
    db.add(Category(name="Makan & Minum", type=TransactionType.EXPENSE, icon="X"))
    db.add(Category(name="Transportasi", type=TransactionType.EXPENSE, icon="X"))
    db.add(Category(name="Belanja", type=TransactionType.EXPENSE, icon="X"))
    db.add(Category(name="BBM", type=TransactionType.EXPENSE, icon="X"))
    db.add(Category(name="Gaji", type=TransactionType.INCOME, icon="Y"))
    db.add(Category(name="Freelance", type=TransactionType.INCOME, icon="Y"))
    db.add(Account(name="BCA", user_id=bob.id, type=AccountType.BANK,
                   initial_balance=1_000_000, current_balance=1_000_000))
    db.add(Account(name="Cash", user_id=bob.id, type=AccountType.CASH,
                   initial_balance=500_000, current_balance=500_000))
    db.add(Account(name="DANA", user_id=bob.id, type=AccountType.E_WALLET,
                   initial_balance=0, current_balance=0))
    db.commit()
    db.close()

    # Seed master data (institutions, e-wallet providers)
    from app.services.seed_master import (
        seed_financial_institutions, seed_ewallet_providers,
    )
    seed_db = TestingSessionLocal()
    seed_financial_institutions(seed_db)
    seed_ewallet_providers(seed_db)
    seed_db.commit()
    seed_db.close()

    # Existing tests were written pre-auth; keep them green by letting the
    # whole suite run as the default user. test_auth.py exercises REAL auth.
    app.dependency_overrides[get_current_user] = lambda: _default_user_ctx(_bob_id)
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
