"""Soft authentication context for templates.

Sets ``request.state.user`` when a valid session cookie is present. This is
NOT the enforcement layer - routes still depend on get_current_user(), which
raises NotAuthenticated. This middleware only feeds the shared navigation.
"""
from dataclasses import dataclass
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.deps import get_current_user
from app.auth.sessions import (
    CSRF_COOKIE, SESSION_COOKIE, get_session_row, resolve_request_user,
)
from app.database.db import SessionLocal
from app.models.models import User

PUBLIC_PREFIXES = ("/static", "/login", "/register")


@dataclass
class UserContext:
    """Lightweight user context for templates."""
    id: int
    username: str
    is_admin: bool = False
    # Set when an admin created this session via the impersonate flow.
    # The banner middleware renders a "Mode dukungan" strip + return button.
    is_impersonating: bool = False
    impersonator_username: str | None = None


class UserContextMiddleware(BaseHTTPMiddleware):
    """Soft auth context for templates (never blocks a request).

    Uses the dependency-override user when one is active (tests run as a
    pre-authenticated user); otherwise resolves the real session cookie.
    """

    async def dispatch(self, request, call_next):
        request.state.user = None
        request.state.csrf_token = request.cookies.get(CSRF_COOKIE, "")
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
                    ctx = UserContext(
                        id=db_user.id,
                        username=db_user.username,
                        is_admin=bool(getattr(db_user, "is_admin", False)),
                    )
                    row = get_session_row(db, request.cookies.get(SESSION_COOKIE))
                    if row is not None and row.impersonator_user_id:
                        admin = db.query(User).filter(
                            User.id == row.impersonator_user_id
                        ).first()
                        if admin is not None:
                            ctx.is_impersonating = True
                            ctx.impersonator_username = admin.username
                    request.state.user = ctx
            except Exception:
                request.state.user = None
            finally:
                db.close()
        return await call_next(request)
