import asyncio
import pytest
from providers.retry import (
    compute_backoff_delay,
    is_transient_error,
    get_retry_params,
    DEFAULT_RETRIES,
    DEFAULT_INITIAL_DELAY,
    DEFAULT_MAX_DELAY,
    DEFAULT_BACKOFF_FACTOR
)


def test_compute_backoff_delay_formula_and_ceiling():
    # Deterministic check without jitter
    d1 = compute_backoff_delay(attempt=1, initial_delay=1.0, max_delay=30.0, backoff_factor=2.0, jitter=False)
    assert d1 == 1.0

    d2 = compute_backoff_delay(attempt=2, initial_delay=1.0, max_delay=30.0, backoff_factor=2.0, jitter=False)
    assert d2 == 2.0

    d3 = compute_backoff_delay(attempt=3, initial_delay=1.0, max_delay=30.0, backoff_factor=2.0, jitter=False)
    assert d3 == 4.0

    d4 = compute_backoff_delay(attempt=4, initial_delay=1.0, max_delay=30.0, backoff_factor=2.0, jitter=False)
    assert d4 == 8.0

    # Max ceiling check
    d8 = compute_backoff_delay(attempt=8, initial_delay=1.0, max_delay=30.0, backoff_factor=2.0, jitter=False)
    assert d8 == 30.0


def test_compute_backoff_delay_with_jitter():
    for attempt in range(1, 6):
        expected_base = min(1.0 * (2.0 ** (attempt - 1)), 30.0)
        delay = compute_backoff_delay(attempt=attempt, initial_delay=1.0, max_delay=30.0, backoff_factor=2.0, jitter=True)
        assert 0.5 * expected_base <= delay <= expected_base


def test_is_transient_error_classification():
    class MockStatusError(Exception):
        def __init__(self, status_code):
            self.status_code = status_code

    # Transient status codes
    assert is_transient_error(MockStatusError(429)) is True
    assert is_transient_error(MockStatusError(500)) is True
    assert is_transient_error(MockStatusError(502)) is True
    assert is_transient_error(MockStatusError(503)) is True
    assert is_transient_error(MockStatusError(504)) is True

    # Fatal / Non-transient status codes
    assert is_transient_error(MockStatusError(400)) is False
    assert is_transient_error(MockStatusError(401)) is False
    assert is_transient_error(MockStatusError(403)) is False
    assert is_transient_error(MockStatusError(404)) is False

    # Connection and timeout errors
    assert is_transient_error(TimeoutError("Connection timed out after 15s")) is True
    assert is_transient_error(ConnectionResetError("Connection reset by peer")) is True
    assert is_transient_error(Exception("Rate limit exceeded. Please try again later.")) is True

    # Control flow cancellations
    assert is_transient_error(KeyboardInterrupt()) is False
    assert is_transient_error(asyncio.CancelledError()) is False


def test_get_retry_params_from_config(mock_engine):
    retries, initial_delay, max_delay, backoff_factor, jitter = get_retry_params(mock_engine.config_mgr)
    assert retries == 3
    assert initial_delay == 1.0
    assert max_delay == 30.0
    assert backoff_factor == 2.0
    assert jitter is True
