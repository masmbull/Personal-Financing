"""Shared API dependencies.

get_current_user() is the single seam where authentication will be added.
Business logic never hardcodes a user - it receives this context instead.
"""
from dataclasses import dataclass

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database.db import get_db  # re-exported for API modules


@dataclass
class CurrentUser:
    id: int = 1
    username: str = "local"
    display_name: str = "Local User"


def get_current_user() -> CurrentUser:
    """Local single-user context for now.

    Future: validate a JWT/session here and return the real user; every
    protected endpoint simply adds this dependency - no other changes needed.
    """
    return CurrentUser()


DbDep = Depends(get_db)
UserDep = Depends(get_current_user)
