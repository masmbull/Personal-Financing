"""API v1 - aggregates all domain routers under /api/v1."""
from fastapi import APIRouter

from app.api import (
    accounts, assets, bills, budgets, categories, credit_cards, dashboard, debts,
    ewallet, fuel, health, institutions, investments, merchants, payment_methods,
    receipts, reports, savings, transactions, transfers,
)

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(health.router)
api_v1_router.include_router(dashboard.router)
api_v1_router.include_router(accounts.router)
api_v1_router.include_router(transactions.router)
api_v1_router.include_router(transfers.router)
api_v1_router.include_router(categories.router)
api_v1_router.include_router(debts.router)
api_v1_router.include_router(bills.router)
api_v1_router.include_router(budgets.router)
api_v1_router.include_router(savings.router)
api_v1_router.include_router(assets.router)
api_v1_router.include_router(investments.router)
api_v1_router.include_router(reports.router)
api_v1_router.include_router(receipts.router)
api_v1_router.include_router(merchants.router)
api_v1_router.include_router(payment_methods.router)
api_v1_router.include_router(fuel.router)
api_v1_router.include_router(credit_cards.router)
api_v1_router.include_router(institutions.router)
api_v1_router.include_router(ewallet.router)

__all__ = ["api_v1_router"]
