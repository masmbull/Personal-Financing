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


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, username: str, password: str, is_admin: bool = False) -> User:
    """Create an active user. Username is normalized to lowercase."""
    uname = username.strip().lower()
    if get_by_username(db, uname):
        raise UsernameTaken(f"Username '{uname}' already exists")
    user = User(
        username=uname,
        password_hash=hash_password(password),
        is_active=1,
        is_admin=1 if is_admin else 0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Created user id=%s (admin=%s)", user.id, is_admin)
    return user


def authenticate(db: Session, username: str, password: str) -> User | None:
    """Generic credential check - returns the user or None (never WHY)."""
    if not username or not password:
        return None
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
    existing = get_by_username(db, uname)
    if existing:
        # Ensure the bootstrap user is always an admin
        if not existing.is_admin:
            existing.is_admin = 1
            db.commit()
        return existing
    if db.query(User).count() == 0:
        try:
            return create_user(db, uname, password, is_admin=True)
        except UsernameTaken:
            return get_by_username(db, uname)
    return get_by_username(db, uname)


def set_admin(db: Session, user_id: int, is_admin: bool) -> User | None:
    """Promote or demote a user to/from admin."""
    user = get_by_id(db, user_id)
    if user is None:
        return None
    user.is_admin = 1 if is_admin else 0
    db.commit()
    db.refresh(user)
    logger.info("User id=%s admin=%s", user.id, is_admin)
    return user


def list_users(db: Session) -> list[User]:
    """List all users (admin only)."""
    return db.query(User).order_by(User.created_at).all()


def count_users(db: Session) -> int:
    """Count total users."""
    return db.query(User).count()
