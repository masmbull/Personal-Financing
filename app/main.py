import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database.db import engine, Base, SessionLocal
from app.models.models import Account, Category, AccountType, TransactionType
from app.routes import dashboard, transactions, categories, reports, transfer, debts, bills, budgets, savings, assets_list, investments, receipts_ui, misc, export, admin, help
from app.api.router import api_v1_router
from app.api.errors import register_exception_handlers
from app.auth.router import router as auth_router
from app.middleware import UserContextMiddleware
from app.rate_limit import RateLimitMiddleware
from app.config import get_settings

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")


def seed_default_data():
    """Seed reference data only. No default accounts: the Akun menu starts
    EMPTY (just the "+ Akun" button); users add their own real accounts."""
    db = SessionLocal()
    try:
        from app.services.seed_categories import seed_categories
        seed_categories(db)
    finally:
        db.close()


def _validate_production_config(s) -> None:
    """Fail-fast: refuse to boot in production with unsafe defaults.

    Extracted from lifespan so it can be unit-tested without spinning up
    TestClient lifespan. Mutates DEBUG=False if it was left on.
    """
    if not s.is_production:
        return
    if s.SECRET_KEY == "change-me-in-production":
        raise RuntimeError(
            "SECRET_KEY must be overridden via env when APP_ENV=production"
        )
    if s.DEBUG:
        logger.warning("DEBUG=true forced off because APP_ENV=production")
        s.DEBUG = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_production_config(settings)

    Base.metadata.create_all(bind=engine)
    # Legacy DB safety: add user_id columns where missing (idempotent),
    # then claim legacy rows for the bootstrap admin when one exists.
    from app.migrations import claim_legacy_rows, run_migrations, run_category_hierarchy_migration
    legacy_altered = run_migrations(engine)
    run_category_hierarchy_migration(engine)
    from app.migrations import run_bill_occurrence_migration
    run_bill_occurrence_migration(engine)
    from app.migrations import run_domain_expansion_migration
    run_domain_expansion_migration(engine)
    from app.migrations import run_admin_column_migration
    run_admin_column_migration(engine)
    from app.migrations import run_impersonation_migration
    run_impersonation_migration(engine)
    from app.migrations import run_institution_fk_migration
    run_institution_fk_migration(engine)
    from app.migrations import run_password_reset_request_migration
    run_password_reset_request_migration(engine)
    seed_default_data()
    try:
        from app.services.seed_master import seed_master_data
        _s = SessionLocal()
        try:
            seed_master_data(_s)
        finally:
            _s.close()
    except Exception as e:
        # Master data seed is nice-to-have, not critical. Allow tests to continue.
        logger.warning("Master data seed failed: %s", e)

    from app.database.db import SessionLocal as _SL
    from app.services.users import bootstrap_admin
    _db = _SL()
    try:
        admin = bootstrap_admin(_db)
        if legacy_altered and admin is not None:
            claim_legacy_rows(_db, admin.id)
        # Daily jobs: bill occurrences + net-worth snapshots for ALL users.
        from app.services.jobs import run_bill_auto_post, run_daily_net_worth_snapshots
        run_bill_auto_post(_db)
        run_daily_net_worth_snapshots(_db)
    finally:
        _db.close()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Personal finance backend. The REST API under `/api/v1` is the "
        "primary business interface for web/PWA/mobile clients; the Jinja "
        "pages remain as the current web UI. All financial calculations live "
        "in the service layer shared by both."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - configurable via CORS_ORIGINS env var; never wildcard in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
# Soft session context for templates (enforcement happens in route deps).
app.add_middleware(UserContextMiddleware)
# Brute-force protection on auth + upload endpoints (in-memory, per-IP).
app.add_middleware(RateLimitMiddleware)

register_exception_handlers(app)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# REST API - primary interface
app.include_router(api_v1_router)

# Authentication pages
app.include_router(auth_router)

# Legacy Jinja web UI - kept for backward compatibility
app.include_router(dashboard.router)
app.include_router(receipts_ui.router)
app.include_router(misc.router)
app.include_router(transactions.router)
app.include_router(categories.router)
app.include_router(reports.router)
app.include_router(transfer.router)
app.include_router(debts.router)
app.include_router(bills.router)
app.include_router(budgets.router)
app.include_router(savings.router)
app.include_router(assets_list.router)
app.include_router(investments.router)
app.include_router(export.router)

# Admin panel
app.include_router(admin)

# Help/knowledge base
app.include_router(help)

