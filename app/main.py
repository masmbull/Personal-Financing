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
                ("Lainnya", "\U0001f4cb", "OTHER"),
            ]
            income_cats = [
                ("Gaji", "\U0001f4b0", "SALARY"),
                ("Bonus", "\U0001f381", "BONUS"),
                ("Freelance", "\U0001f4bb", "FREELANCE"),
                ("Penjualan", "\U0001f3f7\ufe0f", "OTHER"),
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
                ("BCA", AccountType.BANK, "\U0001f3e6", "BCA"),
                ("Mandiri", AccountType.BANK, "\U0001f3e6", "Mandiri"),
                ("DANA", AccountType.E_WALLET, "\U0001f4f1", "DANA"),
                ("GoPay", AccountType.E_WALLET, "\U0001f4f1", "GoPay"),
            ]
            for name, atype, icon, inst in defaults:
                db.add(Account(name=name, type=atype, initial_balance=0, current_balance=0, icon=icon, institution=inst))
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_default_data()
    from app.database.db import SessionLocal as _SL
    from app.services.reports import record_daily_snapshot
    _db = _SL()
    try:
        record_daily_snapshot(_db)
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

register_exception_handlers(app)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# REST API - primary interface
app.include_router(api_v1_router)

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

