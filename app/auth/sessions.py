"""Signed, HttpOnly, SameSite session cookie backed by a DB session table.

* the cookie carries an opaque random token only - never the password
* the server stores a SHA-256 hash of the token; the DB is the source of
  truth, so logout can genuinely revoke a session
* every successful login creates a brand-new session (fixation-safe)
* expiry is enforced server-side on every request
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone


def _utcnow() -> datetime:
    """Naive UTC now (drop tzinfo). Stored datetimes stay naive on purpose so
    the existing schema keeps working without a migration, but the call site
    is no longer the deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

from fastapi import Request, Response
from sqlalchemy.orm import Session as SqlSession

from app.config import get_settings
from app.models.models import User, UserSession

SESSION_COOKIE = "pf_session"
SESSION_TTL_DAYS = 30
CSRF_COOKIE = "pf_csrf"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: SqlSession, user_id: int,
                   ttl_days: int = SESSION_TTL_DAYS) -> tuple[str, datetime]:
    """Persist a new session and return (raw_token, expires_at)."""
    token = secrets.token_urlsafe(32)
    expires_at = _utcnow() + timedelta(days=ttl_days)
    db.add(UserSession(
        user_id=user_id, token_hash=_hash_token(token), expires_at=expires_at,
    ))
    db.commit()
    return token, expires_at


def get_session_user(db: SqlSession, token: str | None) -> User | None:
    """Resolve a session token to an active user, or None."""
    if not token:
        return None
    row = db.query(UserSession).filter(
        UserSession.token_hash == _hash_token(token)
    ).first()
    if row is None or row.revoked_at is not None:
        return None
    if row.expires_at < _utcnow():
        return None
    user = db.query(User).filter(User.id == row.user_id).first()
    if user is None or not user.is_active:
        return None
    return user


def invalidate_session(db: SqlSession, token: str | None) -> None:
    """Revoke a session so it can never authenticate again."""
    if not token:
        return
    row = db.query(UserSession).filter(
        UserSession.token_hash == _hash_token(token)
    ).first()
    if row is not None and row.revoked_at is None:
        row.revoked_at = _utcnow()
        db.commit()


def resolve_request_user(request: Request, db: SqlSession) -> User | None:
    """Convenience: read the cookie and resolve it to a user (or None)."""
    return get_session_user(db, request.cookies.get(SESSION_COOKIE))


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE, value=token,
        max_age=SESSION_TTL_DAYS * 86400,
        httponly=True, samesite="lax", secure=settings.is_production,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def set_csrf_cookie(response: Response, token: str | None = None) -> str:
    """Set a double-submit CSRF cookie and return its value for the form.

    ``token`` may be supplied when the page was rendered with the value
    already embedded (so the hidden field and cookie always match).
    """
    settings = get_settings()
    token = token or secrets.token_urlsafe(24)
    response.set_cookie(
        key=CSRF_COOKIE, value=token,
        max_age=SESSION_TTL_DAYS * 86400,
        httponly=False, samesite="lax", secure=settings.is_production,
        path="/",
    )
    return token


def csrf_ok(cookie: str | None, sent: str | None) -> bool:
    """Constant-time double-submit check for state-changing form posts."""
    if not cookie or not sent:
        return False
    return secrets.compare_digest(cookie, sent)