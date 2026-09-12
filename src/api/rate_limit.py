"""In-memory per-IP rate limiting for the endpoints that trigger paid LLM calls.

Single-process, in-memory by design: this app runs as one instance, so a
dict-backed sliding window is enough -- a Redis-backed limiter would be premature
infrastructure for something not horizontally scaled. Revisit if that changes.

Known limitation: behind a reverse proxy, request.client.host is the proxy's IP for
every caller unless the proxy is configured to forward and this is updated to trust
X-Forwarded-For. Fine for direct/local deployment; document before fronting with a proxy.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

WINDOW_SECONDS = 60
MAX_REQUESTS_PER_WINDOW = 10

# Stricter window for public, unauthenticated endpoints -- no login barrier means no
# cost barrier either, so the quota has to do more work than the authenticated one.
PUBLIC_WINDOW_SECONDS = 60
PUBLIC_MAX_REQUESTS_PER_WINDOW = 3


class RateLimiter:
    def __init__(self, *, window_seconds: float, max_requests: int):
        self.window_seconds = window_seconds
        self.max_requests = max_requests
        self._request_log: dict[str, deque[float]] = defaultdict(deque)

    def check(self, client_key: str) -> None:
        now = time.monotonic()
        log = self._request_log[client_key]

        while log and now - log[0] > self.window_seconds:
            log.popleft()

        if len(log) >= self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: max {self.max_requests} requests per {self.window_seconds:.0f}s.",
            )
        log.append(now)

    def reset(self) -> None:
        """Test-only: clear all tracked state between test cases."""
        self._request_log.clear()


rate_limiter = RateLimiter(window_seconds=WINDOW_SECONDS, max_requests=MAX_REQUESTS_PER_WINDOW)
public_rate_limiter = RateLimiter(
    window_seconds=PUBLIC_WINDOW_SECONDS, max_requests=PUBLIC_MAX_REQUESTS_PER_WINDOW
)


def rate_limit(request: Request) -> None:
    client_key = request.client.host if request.client else "unknown"
    rate_limiter.check(client_key)


def public_rate_limit(request: Request) -> None:
    client_key = request.client.host if request.client else "unknown"
    public_rate_limiter.check(client_key)
