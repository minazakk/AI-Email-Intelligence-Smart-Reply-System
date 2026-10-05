"""In-memory sliding-window rate limiter.

This is a deliberately small, dependency-free implementation that is correct
for a single process. When the API is scaled horizontally, swap this class for
a Redis-backed implementation that keeps the same ``allow()`` signature - the
``rate_limit()`` FastAPI dependency does not need to change.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.core.config import settings
from app.core.errors import RateLimitedError

_MAX_TRACKED_KEYS = 10_000


class SlidingWindowRateLimiter:
    def __init__(self, window_seconds: int = 60) -> None:
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, *, now: float | None = None) -> bool:
        if limit <= 0:
            return False
        current = time.monotonic() if now is None else now
        cutoff = current - self.window_seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(current)
            if len(self._hits) > _MAX_TRACKED_KEYS:
                # Bound memory: drop the oldest idle keys.
                for stale in [k for k, v in self._hits.items() if not v][:1000]:
                    self._hits.pop(stale, None)
            return True

    def remaining(self, key: str, limit: int, *, now: float | None = None) -> int:
        current = time.monotonic() if now is None else now
        cutoff = current - self.window_seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            return max(0, limit - len(bucket))

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowRateLimiter(window_seconds=60)


def client_key(request, bucket: str) -> str:
    forwarded = request.headers.get("x-forwarded-for", "") if settings.trust_proxy_headers else ""
    host = forwarded.split(",")[0].strip() if forwarded else (request.client.host or "unknown")
    return f"{bucket}:{host}"


def enforce_rate_limit(request, bucket: str, limit: int) -> None:
    if not settings.rate_limit_enabled:
        return
    key = client_key(request, bucket)
    if not limiter.allow(key, limit):
        retry_after = limiter.window_seconds
        raise RateLimitedError(
            "Too many requests for this endpoint. Please retry later.",
            details={"retry_after_seconds": retry_after},
        )
