import pytest
from fastapi import HTTPException

from api.ratelimit import RateLimiter, client_ip


class FakeRequest:
    def __init__(self, forwarded=None, host="10.0.0.1"):
        self.headers = {"x-forwarded-for": forwarded} if forwarded else {}
        self.client = type("C", (), {"host": host})()


def test_blocks_after_the_limit_and_reports_retry_after():
    limiter = RateLimiter("t", calls=3, per_seconds=60)
    req = FakeRequest()
    for _ in range(3):
        limiter(req)
    with pytest.raises(HTTPException) as err:
        limiter(req)
    assert err.value.status_code == 429
    assert int(err.value.headers["Retry-After"]) >= 1


def test_limits_each_client_separately():
    limiter = RateLimiter("t", calls=1, per_seconds=60)
    limiter(FakeRequest(host="1.1.1.1"))
    limiter(FakeRequest(host="2.2.2.2"))
    with pytest.raises(HTTPException):
        limiter(FakeRequest(host="1.1.1.1"))


def test_uses_the_last_forwarded_entry_not_one_the_client_can_forge():
    assert client_ip(FakeRequest(forwarded="6.6.6.6, 203.0.113.9")) == "203.0.113.9"
    limiter = RateLimiter("t", calls=1, per_seconds=60)
    limiter(FakeRequest(forwarded="1.1.1.1, 203.0.113.9"))
    with pytest.raises(HTTPException):
        limiter(FakeRequest(forwarded="2.2.2.2, 203.0.113.9"))
