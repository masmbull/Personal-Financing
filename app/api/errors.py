"""Centralised API error handling - consistent envelope, no internal leaks."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError

from app.auth.errors import NotAuthenticated

logger = logging.getLogger("app.api.errors")


class ApiError(Exception):
    """Raise anywhere in the API layer for a controlled error response."""

    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


# Service-layer sentinel exceptions -> stable API codes.
_NOT_FOUND_MAP = []


def _map_exceptions():
    from app.services.transactions import TransactionNotFound
    from app.services.accounts import AccountNotFound, AccountInUse
    from app.services.categories import (
        CategoryNotFound, CategoryInUse, CategoryInvalidParent,
    )
    from app.services.debts import DebtNotFound, PaymentError
    from app.services.bills import BillNotFound
    from app.services.budgets import BudgetNotFound
    from app.services.savings import GoalNotFound, SavingsOperationError
    from app.services.assets import AssetNotFound
    from app.services.investments import InvestmentNotFound
    from app.services.receipts import (
        ReceiptValidationError, ReceiptNotFound, ReceiptAlreadyConfirmed,
    )

    return {
        AccountNotFound: (404, "ACCOUNT_NOT_FOUND"),
        TransactionNotFound: (404, "TRANSACTION_NOT_FOUND"),
        CategoryNotFound: (404, "CATEGORY_NOT_FOUND"),
        DebtNotFound: (404, "DEBT_NOT_FOUND"),
        BillNotFound: (404, "BILL_NOT_FOUND"),
        BudgetNotFound: (404, "BUDGET_NOT_FOUND"),
        GoalNotFound: (404, "GOAL_NOT_FOUND"),
        AssetNotFound: (404, "ASSET_NOT_FOUND"),
        InvestmentNotFound: (404, "INVESTMENT_NOT_FOUND"),
        AccountInUse: (409, "ACCOUNT_IN_USE"),
        CategoryInUse: (409, "CATEGORY_IN_USE"),
        CategoryInvalidParent: (400, "CATEGORY_INVALID_PARENT"),
        PaymentError: (400, "PAYMENT_INVALID"),
        SavingsOperationError: (400, "SAVINGS_OPERATION_INVALID"),
        ReceiptValidationError: (400, "RECEIPT_INVALID"),
        ReceiptNotFound: (404, "RECEIPT_NOT_FOUND"),
        ReceiptAlreadyConfirmed: (409, "RECEIPT_ALREADY_CONFIRMED"),
    }


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(NotAuthenticated, _handle_not_authenticated)
    app.add_exception_handler(RequestValidationError, _handle_validation)
    app.add_exception_handler(IntegrityError, _handle_integrity)
    app.add_exception_handler(ValueError, _handle_value_error)
    for exc_class, (status_code, code) in _map_exceptions().items():
        def _make(sc=status_code, c=code):
            def handler(request: Request, exc) -> JSONResponse:
                return _error(sc, c, str(exc))
            return handler
        # Specific handlers win over the generic ValueError handler (MRO).
        app.add_exception_handler(exc_class, _make())
    app.add_exception_handler(Exception, _handle_unexpected)


def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    return _error(exc.status_code, exc.code, exc.message)


def _handle_not_authenticated(request: Request, exc: NotAuthenticated):
    """HTML pages redirect to /login; API endpoints get a 401 JSON envelope."""
    if request.url.path.startswith("/api/"):
        return _error(401, "UNAUTHENTICATED", "Authentication required")
    from urllib.parse import quote
    next_path = quote(request.url.path)
    return RedirectResponse(url=f"/login?next={next_path}", status_code=303)


def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    msg = f"{loc}: {first.get('msg', 'invalid input')}" if loc else "Invalid request body"
    return _error(422, "VALIDATION_ERROR", msg)


def _handle_integrity(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning("IntegrityError on %s: %s", request.url.path, exc.orig)
    return _error(409, "CONFLICT", "Permintaan bertentangan dengan data yang ada")


def _handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
    return _error(400, "INVALID_REQUEST", str(exc))


def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s", request.url.path)
    return _error(500, "INTERNAL_ERROR", "Terjadi kesalahan internal server")
