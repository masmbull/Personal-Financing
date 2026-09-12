#!/usr/bin/env python3
"""Create or promote an admin user for the FINANCE app (admin tool).

Usage (run from repo root):
    python create_admin.py <username> <password>   create/promote an admin
    python create_admin.py --list                  list all users + admins

If the user does not exist it is created with admin rights. If it already
exists its admin flag is set (and it is re-activated). Uses the app's own
PBKDF2 hashing so the new hash is compatible with app.auth.security.

Auto-detects a suitable interpreter (re-execs under python3, and into the
app venv if run outside it). No plaintext password is ever printed/logged.
"""
import os
import sys


def _reexec(candidate):
    os.execvp(candidate, [candidate, os.path.abspath(__file__)] + sys.argv[1:])


if sys.version_info[0] < 3:
    import subprocess
    devnull = open(os.devnull, "w")
    for cand in ("python3", "python3.11", "python3.12", "python3.10"):
        try:
            rc = subprocess.call([cand, "--version"], stdout=devnull, stderr=devnull)
        except OSError:
            rc = 1
        if rc == 0:
            _reexec(cand)
    sys.stderr.write("ERROR: Python 3 is required to run this script.\n")
    sys.exit(1)


def _find_venv_python():
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    roots = []
    d = here
    for _ in range(4):
        roots.append(d)
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    roots.append(os.getcwd())
    seen = set()
    for root in roots:
        for vn in ("venv", ".venv", "env", "virtualenv"):
            for sub in ("bin", "Scripts"):
                bindir = os.path.join(root, vn, sub)
                if not os.path.isdir(bindir):
                    continue
                for name in ("python", "python3", "python3.11", "python3.12",
                             "python3.10", "python3.9"):
                    exe = os.path.join(bindir, name)
                    if sys.platform == "win32":
                        exe += ".exe"
                    if exe in seen or not os.path.exists(exe):
                        continue
                    seen.add(exe)
                    probe = (
                        "import importlib.util as u;"
                        "print('OK' if u.find_spec('sqlalchemy') and u.find_spec('app') else 'NO')"
                    )
                    try:
                        out = subprocess.run([exe, "-c", probe], cwd=here,
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.DEVNULL,
                                             timeout=15).stdout.decode().strip()
                    except Exception:
                        continue
                    if out == "OK":
                        return exe
    return None


try:
    import sqlalchemy  # noqa: F401
except ImportError:
    venv_py = _find_venv_python()
    if venv_py:
        _reexec(venv_py)
    sys.stderr.write(
        "ERROR: SQLAlchemy not found. Run this inside the app virtualenv, e.g.\n"
        "    source /opt/finance/venv/bin/activate\n"
        "    python create_admin.py <username> <password>\n"
    )
    sys.exit(1)


import sys as _sys
from app.auth.security import hash_password
from app.database.db import SessionLocal
from app.models.models import User


def _validate_password(pw):
    if len(pw) < 8:
        _sys.stderr.write("ERROR: password must be at least 8 characters\n")
        _sys.exit(1)


def main():
    if len(_sys.argv) == 2 and _sys.argv[1] == "--list":
        # Diagnostics: print every user and their admin/active state so the
        # admin can see whether the account they are logging in with actually
        # has admin rights (and how sessions look).
        db = SessionLocal()
        try:
            users = db.query(User).order_by(User.id).all()
            if not users:
                print("Database users table is EMPTY.")
                print("After first boot with AUTH_BOOTSTRAP_USERNAME/PASSWORD")
                print("set, the app auto-creates that admin account.")
            for u in users:
                flag = "ADMIN" if u.is_admin else "user"
                state = "active" if u.is_active else "INACTIVE"
                created = u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "-"
                print("id=%s  %-20s %-6s %-8s created=%s"
                      % (u.id, u.username, flag, state, created))
            admins = [u for u in users if u.is_admin]
            print()
            if admins:
                print("Admin account(s): %s"
                      % ", ".join(u.username for u in admins))
                print("If login fails, reset the password:")
                print("    python %s <admin_username> <password_baru_min8>" % _sys.argv[0])
            else:
                print("NO ADMIN USER EXISTS. Create one:")
                print("    python %s <username> <password_baru_min8>" % _sys.argv[0])
        finally:
            db.close()
        return
    if len(_sys.argv) != 3:
        _sys.stderr.write("Usage: python create_admin.py <username> <password>\n")
        _sys.stderr.write("       python create_admin.py --list\n")
        _sys.exit(2)
    username = _sys.argv[1].strip().lower()
    password = _sys.argv[2]
    _validate_password(password)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            user = User(
                username=username,
                password_hash=hash_password(password),
                is_active=1,
                is_admin=1,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print("OK: created admin user '%s' (id=%s)." % (username, user.id))
        else:
            user.is_admin = 1
            user.is_active = 1
            if not user.password_hash:
                user.password_hash = hash_password(password)
            db.commit()
            print("OK: user '%s' (id=%s) is now admin." % (username, user.id))
    finally:
        db.close()


if __name__ == "__main__":
    main()
