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
from app.services.users import UsernameTaken, authenticate, create_user

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


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...), password: str = Form(...),
    next: str = Form(""), csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if not csrf_ok(request.cookies.get(CSRF_COOKIE), csrf_token):
        return RedirectResponse(url="/login?error=1", status_code=303)
    user = authenticate(db, username, password)
    if user is None:
        resp = RedirectResponse(url="/login?error=1", status_code=303)
        resp.delete_cookie(CSRF_COOKIE, path="/")
        return resp
    token, _ = create_session(db, user.id)
    # Never reuse an existing session; login always issues a fresh token.
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
    if len(password) < 8:
        return RedirectResponse(url="/register?error=1", status_code=303)
    if password != password2:
        return RedirectResponse(url="/register?error=1", status_code=303)
    try:
        user = create_user(db, username, password)
    except UsernameTaken:
        return RedirectResponse(url="/register?error=1", status_code=303)
    token, _ = create_session(db, user.id)
    resp = RedirectResponse(url="/", status_code=303)
    set_session_cookie(resp, token)
    resp.delete_cookie(CSRF_COOKIE, path="/")
    return resp


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    """POST-only logout. SameSite=Lax blocks cross-site POSTs so an attacker
    cannot drive a victim's browser into this without both cookies."""
    token = request.cookies.get(SESSION_COOKIE)
    if resolve_request_user(request, db) is None:
        return RedirectResponse(url="/login", status_code=303)
    from app.auth.sessions import invalidate_session
    invalidate_session(db, token)
    resp = RedirectResponse(url="/login", status_code=303)
    clear_session_cookie(resp)
    resp.delete_cookie(CSRF_COOKIE, path="/")
    return resp