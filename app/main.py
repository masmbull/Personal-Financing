import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database.db import engine, Base, SessionLocal
from app.models.models import Account, Category, AccountType, TransactionType
from app.routes import dashboard, transactions, categories, reports, transfer, debts, bills, budgets, savings, assets_list, investments, receipts_ui, misc
from app.api.router import api_v1_router
from app.api.errors import register_exception_handlers
from app.auth.router import router as auth_router
from app.middleware import UserContextMiddleware
from app.config import get_settings

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")


def seed_default_data():
    db = SessionLocal()
    try:
        existing_cats = db.query(Category).count()
        if existing_cats == 0:
            expense_cats = [
                ("Makan & Minum", "\U0001f35c", "FOOD & DINING"),
                ("Transportasi", "\u26fd", "TRANSPORTATION"),
                ("Belanja", "\U0001f6d2", "SHOPPING"),
                ("Tagihan", "\U0001f4c4", "HOUSING"),
                ("Hiburan", "\U0001f3ac", "ENTERTAINMENT"),
                ("Kesehatan", "\U0001f3e5", "HEALTH"),
                ("Rumah Tangga", "\U0001f3e0", "HOUSING"),
                ("Pendidikan", "\U0001f4da", "EDUCATION"),
                ("Kuliner Online", "\U0001f372", "FOOD & DINING"),
                ("Minimarket", "\U0001f6ed\ufe0f", "SHOPPING"),
                ("SPBU & Bensin", "\u26fd", "TRANSPORTATION"),
                ("Pulsa & Kuota", "\U0001f4f1", "UTILITIES"),
                ("Listrik & Air", "\U0001f4a1", "UTILITIES"),
                ("Internet & TV", "\U0001f4f6", "UTILITIES"),
                ("Asuransi", "\u2601\ufe0f", "INSURANCE"),
                ("Olahraga", "\U0001f3cb\ufe0f", "HEALTH"),
                ("Kado & Donasi", "\U0001f381", "OTHER"),
                ("Rokok", "\U0001f6ac", "OTHER"),
                ("Lainnya", "\U0001f4cb", "OTHER"),
            ]
            income_cats = [
                ("Gaji", "\U0001f4b0", "SALARY"),
                ("Bonus", "\U0001f381", "BONUS"),
                ("Freelance", "\U0001f4bb", "FREELANCE"),
                ("Penjualan", "\U0001f3f7\ufe0f", "OTHER"),
                ("Bisnis", "\U0001f4bc", "BUSINESS"),
                ("Investasi", "\U0001f4c8", "INVESTMENT"),
                ("Hadiah", "\U0001f389", "OTHER"),
                ("Lainnya", "\U0001f4cb", "OTHER"),
            ]
            for name, icon, group in expense_cats:
                db.add(Category(name=name, type=TransactionType.EXPENSE, icon=icon, group=group, is_default=1))
            for name, icon, group in income_cats:
                db.add(Category(name=name, type=TransactionType.INCOME, icon=icon, group=group, is_default=1))
            db.commit()
        existing_accs = db.query(Account).count()
        if existing_accs == 0:
            defaults = [
                ("Cash", AccountType.CASH, "\U0001f4b5", None),
                # Bank umum (retail)
                ("BCA", AccountType.BANK, "\U0001f3e6", "BCA"),
                ("Mandiri", AccountType.BANK, "\U0001f3e6", "Mandiri"),
                ("BNI", AccountType.BANK, "\U0001f3e6", "BNI"),
                ("BRI", AccountType.BANK, "\U0001f3e6", "BRI"),
                ("BTN", AccountType.BANK, "\U0001f3e6", "BTN"),
                ("CIMB Niaga", AccountType.BANK, "\U0001f3e6", "CIMB Niaga"),
                ("Danamon", AccountType.BANK, "\U0001f3e6", "Danamon"),
                ("Permata", AccountType.BANK, "\U0001f3e6", "Permata"),
                ("Maybank", AccountType.BANK, "\U0001f3e6", "Maybank"),
                ("OCBC NISP", AccountType.BANK, "\U0001f3e6", "OCBC NISP"),
                ("BTPN", AccountType.BANK, "\U0001f3e6", "BTPN"),
                ("Mega", AccountType.BANK, "\U0001f3e6", "Bank Mega"),
                ("Sinarmas", AccountType.BANK, "\U0001f3e6", "Bank Sinarmas"),
                # Bank digital
                ("Jago", AccountType.BANK, "\U0001f3e6", "Bank Jago"),
                ("SeaBank", AccountType.BANK, "\U0001f3e6", "SeaBank"),
                ("Blu", AccountType.BANK, "\U0001f3e6", "BCA Digital"),
                ("Neo Commerce", AccountType.BANK, "\U0001f3e6", "Bank Neo Commerce"),
                ("Allo Bank", AccountType.BANK, "\U0001f3e6", "Allo Bank"),
                # Bank syariah
                ("BSI", AccountType.BANK, "\U0001f3e6", "Bank Syariah Indonesia"),
                ("Muamalat", AccountType.BANK, "\U0001f3e6", "Bank Muamalat"),
                # E-wallet (uang elektronik berizin BI)
                ("DANA", AccountType.E_WALLET, "\U0001f4f1", "DANA"),
                ("GoPay", AccountType.E_WALLET, "\U0001f4f1", "GoPay"),
                ("OVO", AccountType.E_WALLET, "\U0001f4f1", "OVO"),
                ("ShopeePay", AccountType.E_WALLET, "\U0001f4f1", "ShopeePay"),
                ("LinkAja", AccountType.E_WALLET, "\U0001f4f1", "LinkAja"),
                ("i.Saku", AccountType.E_WALLET, "\U0001f4f1", "i.Saku"),
            ]
            for name, atype, icon, inst in defaults:
                db.add(Account(name=name, type=atype, initial_balance=0, current_balance=0, icon=icon, institution=inst))
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.models.models import User

    Base.metadata.create_all(bind=engine)
    # Legacy DB safety: add user_id columns where missing (idempotent),
    # then claim legacy rows for the bootstrap admin when one exists.
    from app.migrations import claim_legacy_rows, run_migrations
    legacy_altered = run_migrations(engine)
    seed_default_data()
    from app.database.db import SessionLocal as _SL
    from app.services.users import bootstrap_admin
    _db = _SL()
    try:
        admin = bootstrap_admin(_db)
        if legacy_altered and admin is not None:
            claim_legacy_rows(_db, admin.id)
        # Per-user daily net-worth snapshot for the oldest active user.
        first_user = _db.query(User).filter(
            User.is_active == 1
        ).order_by(User.id).first()
        if first_user is not None:
            from app.services.reports import record_daily_snapshot
            record_daily_snapshot(_db, first_user.id)
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

