"""Structured, secret-safe logging for the whole app.

* A ``structured_logger`` that emits ``key=value`` lines (parseable by any
  log shipper) instead of free-form strings.
* A redacting formatter that scrubs secrets/tokens/passwords from any log
  record before it hits the console or a file (defence-in-depth: even a
  careless ``logger.info(f"token={token}")`` is scrubbed).
"""
import logging
import re

# Matched case-insensitively; each group is replaced with KEY=[REDACTED].
_SECRET_KEYS = (
    r"password", r"passwd", r"pwd", r"token", r"secret", r"api[_-]?key",
    r"authorization", r"cookie", r"session", r"csrf", r"reset", r"otp",
)
_SECRET_RE = re.compile(
    r"(?i)(?P<k>" + "|".join(_SECRET_KEYS) + r")\s*[:=]\s*['\"]?(?P<v>\S+)",
)
_BEARER_RE = re.compile(r"(?i)Bearer\s+\S+")
_URL_CREDS_RE = re.compile(r"(?i)([a-z]+://)([^:@\s]+):([^@\s]+)@")


class RedactingFormatter(logging.Formatter):
    """Formatter that scrubs secret-shaped values from the message."""

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        msg = _URL_CREDS_RE.sub(r"\1\2:[REDACTED]@", msg)
        msg = _BEARER_RE.sub("Bearer [REDACTED]", msg)
        msg = _SECRET_RE.sub(r"\g<k>=[REDACTED]", msg)
        return msg


def get_logger(name: str) -> logging.Logger:
    """Return a module logger pre-configured with the redacting formatter."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_event(logger: logging.Logger, event: str, **fields) -> None:
    """Emit a structured ``event key=val key=val`` line (secrets scrubbed)."""
    parts = [f"event={event}"]
    for k, v in fields.items():
        if v is None:
            continue
        parts.append(f"{k}={v}")
    logger.info(" ".join(parts))
