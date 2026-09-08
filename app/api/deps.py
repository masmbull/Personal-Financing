"""Shared API dependencies.

get_current_user() resolves the signed session cookie to the real user and
raises NotAuthenticated when absent/invalid. Every protected endpoint adds
this dependency; the service layer receives ``user_id`` from it.
"""
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.errors import NotAuthenticated, NotAuthorized
from app.auth.sessions import resolve_request_user
from app.database.db import get_db  # re-exported for API modules


@dataclass
class CurrentUser:
    id: int
    username: str
    display_name: str
    is_admin: bool = False


def get_current_user(request: Request, db: Session = Depends(get_db)) -> CurrentUser:
    """Resolve the session cookie to the authenticated user."""
    user = resolve_request_user(request, db)
    if user is None:
        raise NotAuthenticated()
    return CurrentUser(id=user.id, username=user.username,
                       display_name=user.username,
                       is_admin=bool(user.is_admin))


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Dependency that ensures the user is an admin."""
    if not user.is_admin:
        raise NotAuthorized("Admin access required")
    return user


DbDep = Depends(get_db)
UserDep = Depends(get_current_user)
AdminDep = Depends(require_admin)