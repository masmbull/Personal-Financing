"""Soft authentication context for templates.

Sets ``request.state.user`` when a valid session cookie is present. This is
NOT the enforcement layer - routes still depend on get_current_user(), which
raises NotAuthenticated. This middleware only feeds the shared navigation.
"""
from dataclasses import dataclass
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.deps import get_current_user
from app.auth.sessions import SESSION_COOKIE, resolve_request_user
from app.database.db import SessionLocal

PUBLIC_PREFIXES = ("/static", "/login", "/register")


@dataclass
class UserContext:
    """Lightweight user context for templates."""
    id: int
    username: str
    is_admin: bool = False


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
                user = override()
                request.state.user = UserContext(
                    id=user.id,
                    username=user.username,
                    is_admin=bool(getattr(user, "is_admin", False)),
                )
            except Exception:
                request.state.user = None
        elif (not path.startswith(PUBLIC_PREFIXES)
                and path != "/api/v1/health"
                and SESSION_COOKIE in request.cookies):
            db = SessionLocal()
            try:
                db_user = resolve_request_user(request, db)
                if db_user:
                    request.state.user = UserContext(
                        id=db_user.id,
                        username=db_user.username,
                        is_admin=bool(getattr(db_user, "is_admin", False)),
                    )
            except Exception:
                request.state.user = None
            finally:
                db.close()
        return await call_next(request)
