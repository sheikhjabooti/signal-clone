from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import threading
import time


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def expires_in(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="milliseconds")


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def random_token() -> str:
    return secrets.token_urlsafe(32)


@dataclass(frozen=True)
class Identity:
    user_id: int
    token_hash: str
    csrf_token: str
    expires_at: str


class RateLimiter:
    """A process-local rate limit, appropriate to the one-worker demo."""
    def __init__(self):
        self.windows: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str, limit: int, window: float = 60):
        tick = time.monotonic()
        with self.lock:
            if len(self.windows) > 10000:
                self.windows = defaultdict(deque, {k: v for k, v in self.windows.items() if v and v[-1] > tick - 300})
            times = self.windows[key]
            while times and times[0] <= tick - window:
                times.popleft()
            if len(times) >= limit:
                raise AppError(429, "rate_limit", "A few too many requests. Try again in a moment.")
            times.append(tick)
