"""In-memory sliding window rate limiter middleware.

Tracks request counts per (IP, path-group) tuple. No external dependencies.
Eviction: old entries are pruned on every check so memory stays bounded
(self-healing — no background thread needed).
"""
import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse

# Sliding window (seconds) and max requests within that window.
_WINDOW = 60
_LIMITS: dict[str, int] = {
    "auth": 5,       # login + register
    "upload": 10,     # receipt upload
}

# Map path prefixes → rate-limit bucket name.
_PATH_BUCKETS: list[tuple[str, str]] = [
    ("/login", "auth"),
    ("/register", "auth"),
    ("/receipts/upload", "upload"),
]


def _bucket_for(path: str) -> str | None:
    for prefix, bucket in _PATH_BUCKETS:
        if path.startswith(prefix):
            return bucket
    return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Lightweight per-IP, per-bucket sliding-window rate limiter.

    Only fires for paths that match a defined bucket — all other requests
    pass through unconditionally with zero overhead.
    """

    _active_instance = None  # set on __init__; used by reset() for tests

    def __init__(self, app, window: int = _WINDOW, limits: dict | None = None):
        super().__init__(app)
        self._window = window
        self._limits = limits or _LIMITS
        # {bucket: {ip: [timestamps]}}
        self._hits: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        RateLimitMiddleware._active_instance = self

    @classmethod
    def reset(cls) -> None:
        """Clear all counters. Called by the test harness between tests so
        one test's requests cannot trip the limiter for the next test."""
        if cls._active_instance is not None:
            cls._active_instance._hits.clear()

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _prune(self, bucket: str, ip: str) -> None:
        cutoff = time.monotonic() - self._window
        self._hits[bucket][ip] = [
            t for t in self._hits[bucket][ip] if t > cutoff
        ]

    async def dispatch(self, request: Request, call_next) -> Response:
        bucket = _bucket_for(request.url.path)
        if bucket is None or request.method != "POST":
            return await call_next(request)

        ip = self._client_ip(request)
        self._prune(bucket, ip)
        if len(self._hits[bucket][ip]) >= self._limits[bucket]:
            return JSONResponse(
                {"detail": "Terlalu banyak percobaan. Coba lagi nanti."},
                status_code=429,
            )
        self._hits[bucket][ip].append(time.monotonic())
        return await call_next(request)
