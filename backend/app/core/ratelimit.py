"""Small in-process sliding-window rate limiter, keyed per user.

It protects model CPU time and third-party API quotas (e.g. USDA's per-key hourly limit). It is
per-process: with several workers each has its own window. Use a shared store (Redis) if the app
is ever scaled out; the interface would stay the same.
"""

import threading
import time
from collections import defaultdict, deque

from app.core.errors import RateLimitedError


class SlidingWindowLimiter:
    def __init__(self, name: str, limit: int, window_seconds: float = 60.0) -> None:
        self.name = name
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                retry = int(self.window - (now - hits[0])) + 1
                raise RateLimitedError(
                    f"Too many {self.name} requests. Please wait {retry} seconds and try again.",
                    retry_after=retry,
                )
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
