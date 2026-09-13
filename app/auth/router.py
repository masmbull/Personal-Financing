"""Authentication web routes - /login, /register, /logout.

All state-changing forms carry a double-submit CSRF token. Password or
username failures produce the same generic message (no enumeration).
"""
import secrets
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates

from app.auth.sessions import (
    CSRF_COOKIE, SESSION_COOKIE, clear_session_cookie, create_session,
    csrf_ok, resolve_request_user, set_csrf_cookie, set_session_cookie,
)
from app.database.db import get_db
from app.models.models import AccountType, PasswordResetRequest
from app.services import accounts as accounts_service
from app.auth.security import verify_password
from app.services.users import (
    UsernameTaken, authenticate, change_password, create_user,
    invalidate_other_sessions,
)
from app.validation import validate_username, validate_password, validate_amount, validate_account_name

templates = Jinja2Templates(directory="app/templates")
router = APIRouter()

GENERIC_LOGIN_ERROR = "Username atau password salah."


def _safe_next(next_url: str | None) -> str:
    """Return an internal path only - blocks open redirects."""
    if not next_url:
        return "/"
    ref = urlparse(next_url)
    if (not ref.scheme and not ref.netloc
            and ref.path.startswith("/") and not ref.path.startswith("//")):
        return next_url
    return "/"


def _render_auth(request: Request, template: str, **extra):
    token = secrets.token_urlsafe(24)
    resp = templates.TemplateResponse(
        request, template, {"csrf_token": token, **extra}
    )
    set_csrf_cookie(resp, token)
    return resp


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db),
               next: str = "", error: str = ""):
    if resolve_request_user(request, db) is not None:
        return RedirectResponse(url="/", status_code=303)
    return _render_auth(request, "auth/login.html", next=_safe_next(next),
                        error=(error == "1"))


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request, db: Session = Depends(get_db),
                         sent: str = "", error: str = ""):
    if resolve_request_user(request, db) is not None:
        return RedirectResponse(url="/", status_code=303)
    return _render_auth(request, "auth/forgot_password.html",
                        sent=(sent == "1"), error=(error == "1"))


@router.post("/forgot-password")
def forgot_password_submit(
    request: Request,
    username: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    """Record a password reset request for the admin to action out-of-band.

    No email is sent and no enumeration is exposed: the same confirmation is
    shown regardless of whether the username exists.
    """
    if not csrf_ok(request.cookies.get(CSRF_COOKIE), csrf_token):
        resp = RedirectResponse(url="/forgot-password?error=1", status_code=303)
        resp.delete_cookie(CSRF_COOKIE, path="/")
        return resp
    uname = (username or "").strip().lower()
    req = PasswordResetRequest(username=uname)
    db.add(req)
    db.commit()
    resp = RedirectResponse(url="/forgot-password?sent=1", status_code=303)
    resp.delete_cookie(CSRF_COOKIE, path="/")
    return resp



@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...), password: str = Form(...),
    next: str = Form(""), csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if not csrf_ok(request.cookies.get(CSRF_COOKIE), csrf_token):
        return RedirectResponse(url="/login?error=1", status_code=303)
    
    # Validate input
    valid, err = validate_username(username)
    if not valid:
        return RedirectResponse(url="/login?error=1", status_code=303)
    
    user = authenticate(db, username, password)
    if user is None:
        resp = RedirectResponse(url="/login?error=1", status_code=303)
        resp.delete_cookie(CSRF_COOKIE, path="/")
        return resp
    token, _ = create_session(db, user.id)
    # Never reuse an existing session; login always issues a fresh token.
    from app.services.audit import record
    record(
        db, action="login_success", actor_user_id=user.id,
        ip_address=request.client.host if request.client else None,
        detail={"username": user.username},
    )
    resp = RedirectResponse(url=_safe_next(next) or "/", status_code=303)
    set_session_cookie(resp, token)
    resp.delete_cookie(CSRF_COOKIE, path="/")
    return resp


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, db: Session = Depends(get_db)):
    if resolve_request_user(request, db) is not None:
        return RedirectResponse(url="/", status_code=303)
    return _render_auth(request, "auth/register.html", error="")


@router.post("/register")
def register_submit(
    request: Request,
    username: str = Form(...), password: str = Form(...),
    password2: str = Form(""), csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if not csrf_ok(request.cookies.get(CSRF_COOKIE), csrf_token):
        return RedirectResponse(url="/register?error=1", status_code=303)
    
    # Validate username
    valid, err = validate_username(username)
    if not valid:
        return RedirectResponse(url="/register?error=1", status_code=303)
    
    # Validate password
    valid, err = validate_password(password)
    if not valid:
        return RedirectResponse(url="/register?error=1", status_code=303)
    
    # Check password match
    if password != password2:
        return RedirectResponse(url="/register?error=1", status_code=303)
    
    try:
        user = create_user(db, username, password)
    except UsernameTaken:
        return RedirectResponse(url="/register?error=1", status_code=303)
    from app.services.audit import record
    record(
        db, action="register", actor_user_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    token, _ = create_session(db, user.id)
    resp = RedirectResponse(url="/setup", status_code=303)
    set_session_cookie(resp, token)
    resp.delete_cookie(CSRF_COOKIE, path="/")
    return resp


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    """POST-only logout. SameSite=Lax blocks cross-site POSTs so an attacker
    cannot drive a victim\'s browser into this without both cookies."""
    token = request.cookies.get(SESSION_COOKIE)
    user = resolve_request_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    from app.auth.sessions import invalidate_session
    from app.services.audit import record
    record(
        db, action="logout", actor_user_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    invalidate_session(db, token)
    resp = RedirectResponse(url="/login", status_code=303)
    clear_session_cookie(resp)
    resp.delete_cookie(CSRF_COOKIE, path="/")
    return resp


def _has_accounts(db: Session, user_id: int) -> bool:
    """Check whether a user owns at least one account."""
    from app.models.models import Account
    return db.query(Account.id).filter(Account.user_id == user_id).first() is not None


@router.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request, db: Session = Depends(get_db)):
    """Post-registration onboarding - user must create at least one account."""
    user = resolve_request_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    if _has_accounts(db, user.id):
        return RedirectResponse(url="/", status_code=303)
    return _render_auth(request, "auth/setup.html", error="")


@router.post("/setup")
def setup_submit(
    request: Request,
    name: str = Form(...),
    type: str = Form(...),
    initial_balance: str = Form("0"),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    """Create the first account during onboarding, then redirect to dashboard."""
    user = resolve_request_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not csrf_ok(request.cookies.get(CSRF_COOKIE), csrf_token):
        return RedirectResponse(url="/setup?error=1", status_code=303)
    if _has_accounts(db, user.id):
        return RedirectResponse(url="/", status_code=303)
    
    # Validate account name
    valid, err = validate_account_name(name)
    if not valid:
        resp = RedirectResponse(url="/setup?error=1", status_code=303)
        resp.delete_cookie(CSRF_COOKIE, path="/")
        return resp
    
    # Validate amount
    init_bal, err = validate_amount(initial_balance)
    if err:
        resp = RedirectResponse(url="/setup?error=1", status_code=303)
        resp.delete_cookie(CSRF_COOKIE, path="/")
        return resp
    
    try:
        accounts_service.create_account(
            db, user_id=user.id, name=name.strip(),
            type_=AccountType(type), initial_balance=init_bal,
        )
    except (ValueError, KeyError):
        resp = RedirectResponse(url="/setup?error=1", status_code=303)
        resp.delete_cookie(CSRF_COOKIE, path="/")
        return resp
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie(CSRF_COOKIE, path="/")
    return resp


@router.get("/setup/skip")
def setup_skip(request: Request, db: Session = Depends(get_db)):
    """Skip onboarding - create a default Cash account so dashboard works."""
    user = resolve_request_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not _has_accounts(db, user.id):
        accounts_service.create_account(
            db, user_id=user.id, name="Cash",
            type_=AccountType.CASH, initial_balance=0,
        )
    return RedirectResponse(url="/", status_code=303)


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    """Self-service account settings (change password)."""
    user = resolve_request_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    if request.state.user.is_impersonating:
        # Support sessions must not change credentials for the real user.
        return RedirectResponse(url="/", status_code=303)
    return _render_auth(request, "settings/change_password.html",
                        error=request.query_params.get("error", ""))


@router.post("/settings/change-password")
def change_password_submit(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    """Update the signed-in user's password after verifying the old one."""
    user = resolve_request_user(request, db)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    if not csrf_ok(request.cookies.get(CSRF_COOKIE), csrf_token):
        return RedirectResponse(url="/settings?error=csrf", status_code=303)

    if not verify_password(current_password, user.password_hash):
        resp = RedirectResponse(url="/settings?error=current", status_code=303)
        resp.delete_cookie(CSRF_COOKIE, path="/")
        return resp
    if new_password != confirm_password:
        resp = RedirectResponse(url="/settings?error=mismatch", status_code=303)
        resp.delete_cookie(CSRF_COOKIE, path="/")
        return resp
    valid, err = validate_password(new_password)
    if not valid:
        resp = RedirectResponse(url="/settings?error=weak", status_code=303)
        resp.delete_cookie(CSRF_COOKIE, path="/")
        return resp

    change_password(db, user, new_password)
    # Keep only the current session; revoke every other device.
    invalidate_other_sessions(db, user.id, request.cookies.get(SESSION_COOKIE))
    from app.services.audit import record
    record(
        db, action="password_change", actor_user_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    return RedirectResponse(url="/settings?done=1", status_code=303)

