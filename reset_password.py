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
    print("ERROR: password must be at least 8 characters", file=sys.stderr)
    sys.exit(1)

db = SessionLocal()
try:
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        print(f"ERROR: user '{username}' not found", file=sys.stderr)
        sys.exit(1)
    user.password_hash = hash_password(new_password)
    db.commit()
    print(f"OK: password for '{username}' (id={user.id}) has been reset.")
finally:
    db.close()
