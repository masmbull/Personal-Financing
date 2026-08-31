"""User service - lookup, creation and authentication glue.

Passwords are hashed with PBKDF2 (app.auth.security); plaintext is never
stored or logged.
"""
import logging

from sqlalchemy.orm import Session

from app.auth.security import hash_password, verify_password
from app.models.models import User

logger = logging.getLogger("app.services.users")


class UsernameTaken(Exception):
    pass


def get_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(
        User.username == username.strip().lower()
    ).first()


def create_user(db: Session, username: str, password: str) -> User:
    """Create an active user. Username is normalized to lowercase."""
    uname = username.strip().lower()
    if get_by_username(db, uname):
        raise UsernameTaken(f"Username '{uname}' already exists")
    user = User(username=uname, password_hash=hash_password(password), is_active=1)
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Created user id=%s", user.id)
    return user


def authenticate(db: Session, username: str, password: str) -> User | None:
    """Generic credential check - returns the user or None (never WHY)."""
    user = get_by_username(db, username)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def bootstrap_admin(db: Session) -> User | None:
    """Create the first-run admin ONLY when env credentials are configured.

    No default password is ever used. Existing admins are never recreated.
    """
    from app.config import get_settings

    settings = get_settings()
    uname = (settings.AUTH_BOOTSTRAP_USERNAME or "").strip().lower()
    password = settings.AUTH_BOOTSTRAP_PASSWORD or ""
    if not uname or not password:
        return None
    if db.query(User).count() == 0:
        try:
            return create_user(db, uname, password)
        except UsernameTaken:
            return get_by_username(db, uname)
    return get_by_username(db, uname)