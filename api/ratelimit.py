"""
Small in-memory sliding-window rate limiter for the public endpoints.

The chat and complaint endpoints need no login and each call can spend LLM
quota, so they are limited per client IP. State lives in process memory, which
is correct for the single API instance this runs as; behind several instances
it would need a shared store such as Redis.

The client IP is the last X-Forwarded-For entry, the one added by the nearest
proxy (Render's load balancer). Earlier entries can be written by the client,
so they are not trusted.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    def __init__(self, scope: str, calls: int, per_seconds: int) -> None:
        self.scope, self.calls, self.window = scope, calls, per_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def __call__(self, request: Request) -> None:
        now = time.monotonic()
        key = client_ip(request)
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.calls:
            retry = max(1, int(self.window - (now - hits[0])))
            raise HTTPException(
                status_code=429,
                detail="You're sending messages too quickly. Please wait a moment and try again.",
                headers={"Retry-After": str(retry)},
            )
        hits.append(now)
        if len(self._hits) > 10_000:
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                del self._hits[k]
