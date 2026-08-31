"""Password hashing - PBKDF2-HMAC-SHA256 from the Python standard library.

Format: ``pbkdf2_sha256$<iterations>$<salt_b64>$<digest_b64>``

* random 16-byte salt per password
* iteration count from OWASP guidance for PBKDF2-HMAC-SHA256
* constant-time comparison via hmac.compare_digest
* no bespoke crypto, no MD5/SHA1/plain SHA256 used as a password hash
"""
import base64
import hashlib
import hmac
import os

# OWASP guidance for PBKDF2-HMAC-SHA256. Test suites may lower this via
# PF_PBKDF2_ITERATIONS to keep CI fast; production keeps the secure default
# and verification always honours the iteration count embedded in the hash.
PBKDF2_ITERATIONS = int(os.environ.get("PF_PBKDF2_ITERATIONS", "600000"))
_ALGO = "pbkdf2_sha256"
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Return a self-describing PBKDF2 hash string for ``password``."""
    salt = os.urandom(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return "$".join([
        _ALGO,
        str(PBKDF2_ITERATIONS),
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(dk).decode("ascii"),
    ])


def verify_password(password: str, encoded: str) -> bool:
    """Compare ``password`` against a hash produced by ``hash_password``.

    Constant-time on the digest comparison. Returns False for malformed
    hashes instead of raising.
    """
    try:
        algo, iterations, salt_b64, digest_b64 = encoded.split("$", 3)
        if algo != _ALGO:
            return False
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(digest_b64, validate=True)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)