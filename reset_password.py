"""Manual password reset for an existing FINANCE user.

Usage (from repo root, venv active):
    python reset_password.py <username> <new_password>

Uses the app's own PBKDF2 hashing so the new hash is byte-compatible with
app.auth.security.verify_password. No plaintext is ever printed or logged.
"""
import sys

from app.auth.security import hash_password
from app.database.db import SessionLocal
from app.models.models import User

if len(sys.argv) != 3:
    print("Usage: python reset_password.py <username> <new_password>")
    sys.exit(2)

username = sys.argv[1].strip().lower()
new_password = sys.argv[2]

if len(new_password) < 8:
    sys.stderr.write("ERROR: password must be at least 8 characters\n")
    sys.exit(1)

db = SessionLocal()
try:
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        sys.stderr.write("ERROR: user '%s' not found\n" % username)
        sys.exit(1)
    user.password_hash = hash_password(new_password)
    db.commit()
    print("OK: password for '%s' (id=%s) has been reset." % (username, user.id))
finally:
    db.close()
