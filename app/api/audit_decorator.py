"""Reusable audit decorator for API + HTML form routes.

Wraps a FastAPI endpoint so that, after the handler runs successfully, an
audit row is appended. Works for both sync and async handlers. The wrapper
preserves the original signature exactly (functools.wraps + inspect) so
FastAPI's dependency injection keeps working.

Usage:
    @router.post("/x")
    @audit_action(action="tx_create", entity="transaction")
    def create_x(...): ...
"""
import asyncio
import contextvars
import functools
import inspect
import logging

from app.services.audit import record as _record

logger = logging.getLogger("app.api.audit_decorator")

# Set by the wrapper each call so nested helpers (and the sync IP fallback)
# can read the inbound request without threading it through every signature.
_request_ctx: contextvars.ContextVar["object | None"] = contextvars.ContextVar(
    "audit_request", default=None
)


def _client_ip(request):
    if request is None:
        return None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


# Recognised entity-id lookups, in priority order. Path params (tx_id, cat_id,
# inv_id, user_id, ...) win over the created-object id, then singular names.
_ENTITY_KEYS = (
    "transaction_id", "tx_id", "account_id", "category_id", "cat_id",
    "investment_id", "inv_id", "asset_id", "debt_id", "budget_id",
    "bill_id", "goal_id", "merchant_id", "payment_method_id", "pm_id",
    "provider_id", "institution_id", "receipt_id", "occurrence_id",
    "user_id", "target_user_id",
)


def audit_action(action: str, entity: str | None = None):
    """Record an audit event after the wrapped endpoint returns successfully.

    Reads ``db`` (Session), ``user`` (CurrentUser) / ``admin`` and optional
    ``request`` (Request) from the resolved kwargs. Any failure in audit
    logging is swallowed so it can never break the primary request.
    """

    def decorator(fn):
        is_async = asyncio.iscoroutinefunction(fn)

        def _entity_id(result, kwargs):
            if isinstance(result, dict) and isinstance(result.get("id"), int):
                return result["id"]
            rid = getattr(result, "id", None)
            if isinstance(rid, int):
                return rid
            for key in _ENTITY_KEYS:
                val = kwargs.get(key)
                if isinstance(val, int) and not isinstance(val, bool):
                    return val
            return None

        def _do_record(kwargs, result):
            try:
                db = kwargs.get("db")
                user = kwargs.get("user") or kwargs.get("admin")
                request = kwargs.get("request") or _request_ctx.get()
                if db is not None and user is not None:
                    _record(
                        db,
                        action=action,
                        actor_user_id=getattr(user, "id", None),
                        entity_type=entity,
                        entity_id=_entity_id(result, kwargs),
                        ip_address=_client_ip(request),
                    )
            except Exception as e:  # audit must never break the request
                logger.warning("audit_action failed for %s: %s", action, e)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            token = _request_ctx.set(kwargs.get("request"))
            try:
                result = fn(*args, **kwargs)
            finally:
                _request_ctx.reset(token)
            _do_record(kwargs, result)
            return result

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            token = _request_ctx.set(kwargs.get("request"))
            try:
                result = await fn(*args, **kwargs)
            finally:
                _request_ctx.reset(token)
            _do_record(kwargs, result)
            return result

        chosen = async_wrapper if is_async else wrapper
        # Keep FastAPI's signature/param model intact.
        chosen.__signature__ = inspect.signature(fn)
        return chosen

    return decorator
