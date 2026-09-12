#!/usr/bin/env python3
"""Manual password reset for an existing FINANCE user (admin tool).

Usage (run from repo root):
    python reset_password.py <username> <new_password>

The script auto-detects a suitable interpreter: if run under Python 2 it
re-execs with python3, and if SQLAlchemy is missing (e.g. run outside the
app venv) it searches for a nearby virtualenv python that has it. No
plaintext password is ever printed or logged.

Uses the app's own PBKDF2 hashing so the new hash is compatible with
app.auth.security.verify_password.
"""
import os
import sys


def _reexec(candidate):
    """Replace the current process with `candidate` running this script."""
    os.execvp(candidate, [candidate, os.path.abspath(__file__)] + sys.argv[1:])


# 1) Under Python 2, re-exec with the first available python3.
if sys.version_info[0] < 3:
    import subprocess
    for cand in ("python3", "python3.11", "python3.12", "python3.10"):
        if subprocess.run([cand, "--version"],
                          stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0:
            _reexec(cand)
    sys.stderr.write("ERROR: Python 3 is required to run this script.\n")
    sys.exit(1)


def _find_venv_python():
    """Walk up from the script dir and cwd looking for a venv python that
    can import sqlalchemy and the app package. Returns path or None."""
    import subprocess
    roots = []
    here = os.path.dirname(os.path.abspath(__file__))
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
                exe = os.path.join(root, vn, sub, "python")
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
                    out = subprocess.run([exe, "-c", probe],
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL,
                                         timeout=15).stdout.decode().strip()
                except Exception:
                    continue
                if out == "OK":
                    return exe
    return None


# 2) Ensure dependencies are importable (run inside the app venv).
try:
    import sqlalchemy  # noqa: F401  (proves the venv has app deps)
except ImportError:
    venv_py = _find_venv_python()
    if venv_py:
        _reexec(venv_py)
    sys.stderr.write(
        "ERROR: SQLAlchemy not found. Run this inside the app virtualenv, e.g.\n"
        "    source /opt/finance/venv/bin/activate\n"
        "    python reset_password.py <username> <new_password>\n"
    )
    sys.exit(1)


import sys as _sys  # re-import for argv access after the guard above
from app.auth.security import hash_password
from app.database.db import SessionLocal
from app.models.models import User

if len(_sys.argv) != 3:
    _sys.stderr.write("Usage: python reset_password.py <username> <new_password>\n")
    _sys.exit(2)

username = _sys.argv[1].strip().lower()
new_password = _sys.argv[2]

if len(new_password) < 8:
    _sys.stderr.write("ERROR: password must be at least 8 characters\n")
    _sys.exit(1)

db = SessionLocal()
try:
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        _sys.stderr.write("ERROR: user '%s' not found\n" % username)
        _sys.exit(1)
    user.password_hash = hash_password(new_password)
    db.commit()
    print("OK: password for '%s' (id=%s) has been reset." % (username, user.id))
finally:
    db.close()
