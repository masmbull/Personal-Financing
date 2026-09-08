"""Admin web routes - HTML pages for the admin panel.

Only accessible to authenticated users with ``is_admin=1``. Other users
are redirected: anonymous -> /login, signed-in non-admin -> /. State-changing
POSTs require a valid double-submit CSRF token.
"""
import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.sessions import CSRF_COOKIE, csrf_ok, resolve_request_user, set_csrf_cookie
from app.database.db import get_db
from app.models.models import Account, Transaction, User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _gate(request: Request, db: Session) -> tuple[User | None, RedirectResponse | None]:
    """Return ``(user, None)`` when admin; otherwise ``(None, redirect)``.

    FastAPI does NOT short-circuit when a dependency returns a Response, so
    we can't rely on ``Depends`` for the redirect - each endpoint must
    inspect this tuple and return the redirect itself.
    """
    user = resolve_request_user(request, db)
    if user is None:
        return None, RedirectResponse(url="/login", status_code=303)
    if not user.is_admin:
        return None, RedirectResponse(url="/", status_code=303)
    return user, None


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    """Admin overview with user list and system stats."""
    admin, redirect = _gate(request, db)
    if redirect is not None:
        return redirect

    users = db.query(User).order_by(User.created_at.desc()).all()
    stats = {
        "total_users": db.query(User).count(),
        "active_users": db.query(User).filter(User.is_active == 1).count(),
        "inactive_users": db.query(User).filter(User.is_active == 0).count(),
        "total_transactions": db.query(Transaction).count(),
        "total_accounts": db.query(Account).count(),
        "admin_count": db.query(User).filter(User.is_admin == 1).count(),
    }
    token = secrets.token_urlsafe(24)
    resp = templates.TemplateResponse(request, "admin/dashboard.html", {
        "users": users,
        "stats": stats,
        "csrf_token": token,
        "current_user": admin,
    })
    set_csrf_cookie(resp, token)
    return resp


@router.post("/admin/users/{user_id}/make-admin")
def make_admin(
    user_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    """Grant admin role to another user."""
    admin, redirect = _gate(request, db)
    if redirect is not None:
        return redirect
    if not csrf_ok(request.cookies.get(CSRF_COOKIE), csrf_token):
        return RedirectResponse(url="/admin", status_code=303)
    user = db.query(User).filter(User.id == user_id).first()
    if user is not None and user.id != admin.id:
        user.is_admin = 1
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/revoke-admin")
def revoke_admin(
    user_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    """Revoke admin role from another user."""
    admin, redirect = _gate(request, db)
    if redirect is not None:
        return redirect
    if not csrf_ok(request.cookies.get(CSRF_COOKIE), csrf_token):
        return RedirectResponse(url="/admin", status_code=303)
    user = db.query(User).filter(User.id == user_id).first()
    if user is not None and user.id != admin.id:
        user.is_admin = 0
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/activate")
def activate_user(
    user_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    """Activate a user account."""
    admin, redirect = _gate(request, db)
    if redirect is not None:
        return redirect
    if not csrf_ok(request.cookies.get(CSRF_COOKIE), csrf_token):
        return RedirectResponse(url="/admin", status_code=303)
    user = db.query(User).filter(User.id == user_id).first()
    if user is not None and user.id != admin.id:
        user.is_active = 1
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/users/{user_id}/deactivate")
def deactivate_user(
    user_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    """Deactivate a user account."""
    admin, redirect = _gate(request, db)
    if redirect is not None:
        return redirect
    if not csrf_ok(request.cookies.get(CSRF_COOKIE), csrf_token):
        return RedirectResponse(url="/admin", status_code=303)
    user = db.query(User).filter(User.id == user_id).first()
    if user is not None and user.id != admin.id:
        user.is_active = 0
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)