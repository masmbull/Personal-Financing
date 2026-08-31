"""Soft authentication context for templates.

Sets ``request.state.user`` when a valid session cookie is present. This is
NOT the enforcement layer - routes still depend on get_current_user(), which
raises NotAuthenticated. This middleware only feeds the shared navigation.
"""
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.deps import get_current_user
from app.auth.sessions import SESSION_COOKIE, resolve_request_user
from app.database.db import SessionLocal

PUBLIC_PREFIXES = ("/static", "/login", "/register")


class UserContextMiddleware(BaseHTTPMiddleware):
    """Soft auth context for templates (never blocks a request).

    Uses the dependency-override user when one is active (tests run as a
    pre-authenticated user); otherwise resolves the real session cookie.
    """

    async def dispatch(self, request, call_next):
        request.state.user = None
        path = request.url.path
        overrides = getattr(request.app, "dependency_overrides", {})
        override = overrides.get(get_current_user)
        if override is not None:
            try:
                request.state.user = override()
            except Exception:  # pragma: no cover - defensive
                request.state.user = None
        elif (not path.startswith(PUBLIC_PREFIXES)
                and path != "/api/v1/health"
                and SESSION_COOKIE in request.cookies):
            db = SessionLocal()
            try:
                request.state.user = resolve_request_user(request, db)
            except Exception:  # never let context resolution crash a request
                request.state.user = None
            finally:
                db.close()
        return await call_next(request)