"""API v1 - aggregates all domain routers under /api/v1."""
from fastapi import APIRouter

from app.api import (
    accounts, assets, bills, budgets, categories, dashboard, debts,
    health, investments, receipts, reports, savings, transactions, transfers,
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

__all__ = ["api_v1_router"]
