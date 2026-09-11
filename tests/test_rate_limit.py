import time

import pytest
from fastapi import HTTPException

from src.api.rate_limit import RateLimiter


@pytest.fixture
def limiter():
    return RateLimiter(window_seconds=60, max_requests=3)


def test_allows_requests_under_the_limit(limiter):
    for _ in range(3):
        limiter.check("1.2.3.4")  # should not raise


def test_rejects_requests_over_the_limit(limiter):
    for _ in range(3):
        limiter.check("1.2.3.4")

    with pytest.raises(HTTPException) as exc_info:
        limiter.check("1.2.3.4")
    assert exc_info.value.status_code == 429


def test_different_clients_have_independent_limits(limiter):
    for _ in range(3):
        limiter.check("1.2.3.4")

    limiter.check("5.6.7.8")  # different client, should not raise


def test_window_expiry_allows_requests_again():
    limiter = RateLimiter(window_seconds=0.05, max_requests=1)
    limiter.check("1.2.3.4")

    time.sleep(0.1)
    limiter.check("1.2.3.4")  # window expired, should not raise


def test_reset_clears_all_state(limiter):
    for _ in range(3):
        limiter.check("1.2.3.4")

    limiter.reset()

    limiter.check("1.2.3.4")  # should not raise after reset
