"""Reusable audit decorator for API routes.

Wraps a FastAPI endpoint so that, after the handler runs successfully, an
audit row is appended. The wrapper preserves the original signature exactly
(functools.wraps + inspect) so FastAPI's dependency injection keeps working.

Usage:
    @router.post("/x")
    @audit_action(action="tx_create", entity="transaction")
    def create_x(...): ...
"""
import functools
import inspect
import logging

from app.database.db import SessionLocal
from app.services.audit import record as _record

logger = logging.getLogger("app.api.audit_decorator")


def _client_ip(request):
    if request is None:
        return None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def audit_action(action: str, entity: str | None = None):
    """Record an audit event after the wrapped endpoint returns successfully.

    Reads `db` (Session), `user` (CurrentUser) and optional `request`
    (Request) from the wrapped function's resolved kwargs. Any failure in
    audit logging is swallowed so it can never break the primary request.
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            try:
                db = kwargs.get("db")
                user = kwargs.get("user") or kwargs.get("admin")
                request = kwargs.get("request")
                entity_id = None
                # Prefer the created id from the result, fall back to any
                # singular path param like transaction_id / account_id.
                if isinstance(result, dict) and "id" in result:
                    entity_id = result.get("id")
                if entity_id is None:
                    # Pydantic / ORM models also expose an `id` attribute.
                    if hasattr(result, "id"):
                        entity_id = getattr(result, "id")
                if entity_id is None:
                    for key in ("transaction_id", "account_id", "category_id",
                                "budget_id", "debt_id", "bill_id", "goal_id",
                                "asset_id", "investment_id", "provider_id",
                                "institution_id", "merchant_id", "pm_id",
                                "receipt_id", "occurrence_id"):
                        if key in kwargs:
                            entity_id = kwargs[key]
                            break
                if db is not None and user is not None:
                    _record(
                        db,
                        action=action,
                        actor_user_id=getattr(user, "id", None),
                        entity_type=entity,
                        entity_id=entity_id,
                        ip_address=_client_ip(request),
                    )
            except Exception as e:  # audit must never break the request
                logger.warning("audit_action failed for %s: %s", action, e)
            return result

        # Keep FastAPI's signature/param model intact.
        wrapper.__signature__ = inspect.signature(fn)
        return wrapper

    return decorator
