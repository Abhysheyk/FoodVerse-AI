"""Named per-user rate limiters shared across requests (in-process; see ratelimit.py)."""

from app.core.ratelimit import SlidingWindowLimiter

_limiters: dict[str, SlidingWindowLimiter] = {}


def limiter(name: str, limit: int) -> SlidingWindowLimiter:
    existing = _limiters.get(name)
    if existing is None or existing.limit != limit:
        existing = _limiters[name] = SlidingWindowLimiter(name, limit)
    return existing


def reset_limiters() -> None:
    for item in _limiters.values():
        item.reset()
