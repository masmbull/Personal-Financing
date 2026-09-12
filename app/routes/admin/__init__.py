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

from app.auth.sessions import (
    CSRF_COOKIE, SESSION_COOKIE, create_session, csrf_ok, resolve_impersonation,
    resolve_request_user, set_csrf_cookie, set_session_cookie,
)
from app.database.db import get_db
from app.models.models import Account, Transaction, User, PasswordResetRequest

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
        "pending_resets": _pending_reset_count(db),
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


def _validate_impersonation_target(db: Session, admin: User, user_id: int) -> str | None:
    """Return an error code (or None) for an admin impersonating ``user_id``.

    Guards: no self-impersonation, target must exist, must not be an admin,
    must be active. Codes match the messages rendered in ``admin/index.html``.
    """
    if user_id == admin.id:
        return "6"
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        return "3"
    if target.is_admin:
        return "4"
    if not target.is_active:
        return "5"
    return None


@router.get("/admin/users", response_class=HTMLResponse)
def admin_users_page(request: Request, db: Session = Depends(get_db)):
    """User management page with per-user support (impersonate) actions."""
    admin, redirect = _gate(request, db)
    if redirect is not None:
        return redirect

    users = db.query(User).order_by(User.created_at.desc()).all()
    token = secrets.token_urlsafe(24)
    resp = templates.TemplateResponse(request, "admin/index.html", {
        "users": users,
        "user_count": len(users),
        "current": admin,
        "csrf_token": token,
        "error": request.query_params.get("error", ""),
    })
    set_csrf_cookie(resp, token)
    return resp


@router.get("/admin/users/{user_id}/impersonate", response_class=HTMLResponse)
def impersonate_confirm(
    user_id: int, request: Request, db: Session = Depends(get_db),
):
    """Confirmation page before an admin logs in as a user (support)."""
    admin, redirect = _gate(request, db)
    if redirect is not None:
        return redirect
    error = _validate_impersonation_target(db, admin, user_id)
    if error is not None:
        return RedirectResponse(url=f"/admin/users?error={error}", status_code=303)
    target = db.query(User).filter(User.id == user_id).first()
    token = secrets.token_urlsafe(24)
    resp = templates.TemplateResponse(request, "admin/impersonate.html", {
        "target_user": target,
        "csrf_token": token,
    })
    set_csrf_cookie(resp, token)
    return resp


@router.post("/admin/users/{user_id}/impersonate")
def impersonate_start(
    user_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    """Create an impersonation session and switch the admin's cookie to it."""
    admin, redirect = _gate(request, db)
    if redirect is not None:
        return redirect
    if not csrf_ok(request.cookies.get(CSRF_COOKIE), csrf_token):
        return RedirectResponse(url="/admin/users?error=1", status_code=303)
    error = _validate_impersonation_target(db, admin, user_id)
    if error is not None:
        return RedirectResponse(url=f"/admin/users?error={error}", status_code=303)
    token, _ = create_session(db, user_id, impersonator_user_id=admin.id)
    resp = RedirectResponse(url="/", status_code=303)
    set_session_cookie(resp, token)
    # Keep a CSRF cookie live so the global "return to admin" banner can POST.
    set_csrf_cookie(resp)
    return resp


@router.post("/admin/stop-impersonating")
def stop_impersonating(
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    """End an impersonation session and return the admin to their own session."""
    if not csrf_ok(request.cookies.get(CSRF_COOKIE), csrf_token):
        return RedirectResponse(url="/", status_code=303)
    new_token, _ = resolve_impersonation(db, request.cookies.get(SESSION_COOKIE))
    if new_token is None:
        # Not impersonating: don't log anyone out, just send home.
        return RedirectResponse(url="/", status_code=303)
    resp = RedirectResponse(url="/admin/users", status_code=303)
    set_session_cookie(resp, new_token)
    set_csrf_cookie(resp)
    return resp


def _pending_reset_count(db: Session) -> int:
    return db.query(PasswordResetRequest).filter(
        PasswordResetRequest.status == "pending"
    ).count()


@router.get("/admin/reset-requests", response_class=HTMLResponse)
def admin_reset_requests_page(request: Request, db: Session = Depends(get_db)):
    """List pending password reset requests for the admin to action."""
    admin, redirect = _gate(request, db)
    if redirect is not None:
        return redirect
    requests = (
        db.query(PasswordResetRequest)
        .filter(PasswordResetRequest.status == "pending")
        .order_by(PasswordResetRequest.created_at.desc())
        .all()
    )
    token = secrets.token_urlsafe(24)
    resp = templates.TemplateResponse(request, "admin/reset_requests.html", {
        "requests": requests,
        "csrf_token": token,
    })
    set_csrf_cookie(resp, token)
    return resp


@router.post("/admin/reset-requests/{request_id}/resolve")
def admin_reset_request_resolve(
    request_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    """Mark a reset request as resolved (admin has reset the password)."""
    admin, redirect = _gate(request, db)
    if redirect is not None:
        return redirect
    if not csrf_ok(request.cookies.get(CSRF_COOKIE), csrf_token):
        return RedirectResponse(url="/admin/reset-requests", status_code=303)
    req = db.query(PasswordResetRequest).filter(
        PasswordResetRequest.id == request_id
    ).first()
    if req is not None and req.status == "pending":
        from app.models.models import _utcnow
        req.status = "resolved"
        req.resolved_at = _utcnow()
        db.commit()
    return RedirectResponse(url="/admin/reset-requests", status_code=303)