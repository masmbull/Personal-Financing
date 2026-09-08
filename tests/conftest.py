"""Shared test fixtures - ONE overridden database for every test module."""
import os
import shutil
import warnings

# CRITICAL: Suppress anyio deprecation warning BEFORE any imports.
# anyio 4.14+ raises DeprecationWarning for BlockingPortal at import time,
# which happens before pytest filterwarnings rules are applied.
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*BlockingPortal.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"anyio.*")

# pytest-xdist: every worker gets its OWN database file and upload dir so
# parallel workers never contend for the same SQLite file. PYTEST_XDIST_WORKER
# is set by xdist in worker processes BEFORE this module is imported; in a
# normal (non-xdist) run it is absent and the legacy names are used.
_XDIST_WORKER = os.environ.get("PYTEST_XDIST_WORKER")
_WORKER_SUFFIX = f"_{_XDIST_WORKER}" if _XDIST_WORKER else ""
TEST_DB_PATH = f"test{_WORKER_SUFFIX}.db"
RECEIPT_TEST_DIR = f"data/receipts_test{_WORKER_SUFFIX}"

# Point uploads / DATABASE_URL at per-worker scratch locations BEFORE
# app.config is imported anywhere. DATABASE_URL pins the app's own engine
# (app.database.db) to the test database too, so no test can ever touch
# data/finance.db.
os.environ.setdefault("DATABASE_URL", f"sqlite:///./{TEST_DB_PATH}")
os.environ.setdefault("RECEIPT_UPLOAD_DIR", RECEIPT_TEST_DIR)
# Fast test hashing - production default (600k iterations) is untouched.
os.environ.setdefault("PF_PBKDF2_ITERATIONS", "2000")
# Disable AI vision (Ollama) in the broad suite: no Ollama is running in CI
# and we must not depend on it. The existing OCR (Tesseract) path is the
# source of truth here; Ollama is exercised in tests/test_receipt_ollama.py
# with mocked HTTP and an optional live smoke test (OLLAMA_INTEGRATION_TEST=1).
os.environ.setdefault("RECEIPT_AI_ENABLED", "false")
os.environ.setdefault("RECEIPT_AI_PROVIDER", "ollama")
os.environ.setdefault("RECEIPT_AI_TIMEOUT_SEC", "1")
os.environ.setdefault("RECEIPT_AI_BASE_URL", "http://127.0.0.1:11435/v1")

import pytest

# Wrap TestClient import with catch_warnings as extra protection
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
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

TEST_DB_URL = f"sqlite:///./{TEST_DB_PATH}"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
_client = TestClient(app)
# Module-level alias so `from tests.conftest import client` still works
# (some legacy tests use it directly instead of as a fixture).
client = _client


@pytest.fixture(name="client")
def _client_fixture() -> TestClient:
    """Shared test client for web/HTML routes (same instance as above)."""
    return _client


@pytest.fixture
def db():
    """A clean test database session, scoped to the calling test."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


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
    # Deterministically close pooled connections so nothing is left for the
    # garbage collector to warn about mid-run (ResourceWarning -> error under
    # filterwarnings=["error"]).
    engine.dispose()
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
