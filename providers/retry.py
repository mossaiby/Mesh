import asyncio
import random
from typing import Tuple, Optional, Any
from theme import console

# Named default constants - no magic numbers
DEFAULT_RETRIES = 3
DEFAULT_INITIAL_DELAY = 1.0
DEFAULT_MAX_DELAY = 30.0
DEFAULT_BACKOFF_FACTOR = 2.0
DEFAULT_JITTER = True

# HTTP status codes indicating transient / retryable errors
TRANSIENT_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524})

# Substrings in exception messages indicating transient failures
TRANSIENT_ERROR_SUBSTRINGS = (
    "rate limit", "ratelimit", "too many requests", "429",
    "timeout", "timed out", "connection error", "connection reset",
    "connection refused", "econnreset", "econnrefused", "service unavailable",
    "bad gateway", "gateway timeout", "500", "502", "503", "504",
    "server error", "overloaded", "capacity", "temporary", "temporarily unavailable"
)


def compute_backoff_delay(
    attempt: int,
    initial_delay: float = DEFAULT_INITIAL_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    jitter: bool = DEFAULT_JITTER
) -> float:
    """
    Calculates exponential backoff delay with optional randomized jitter:
    delay = min(initial_delay * (backoff_factor ** (attempt - 1)), max_delay)
    """
    exponent = max(0, attempt - 1)
    delay = min(initial_delay * (backoff_factor ** exponent), max_delay)
    if jitter:
        # Full jitter between 50% and 100% of calculated exponential delay
        delay = delay * (0.5 + random.random() * 0.5)
    return delay


def is_transient_error(exc: Exception) -> bool:
    """
    Determines whether an exception represents a transient failure (e.g. rate limit,
    server outage, network timeout) that can be safely retried.
    """
    if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError)):
        return False

    status_code = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status_code is not None:
        try:
            code = int(status_code)
            if code in TRANSIENT_STATUS_CODES:
                return True
            if 400 <= code < 500 and code not in (408, 429):
                return False
        except (ValueError, TypeError):
            pass

    cls_name = exc.__class__.__name__.lower()
    if any(k in cls_name for k in ("connection", "timeout", "ratelimit", "servererror", "temporarily")):
        return True

    msg = str(exc).lower()
    return any(p in msg for p in TRANSIENT_ERROR_SUBSTRINGS)


def get_retry_params(config_mgr: Optional[Any] = None) -> Tuple[int, float, float, float, bool]:
    """
    Extracts configured retry and backoff parameters from config_mgr without magic numbers.
    Returns (retries, initial_delay, max_delay, backoff_factor, jitter).
    """
    if config_mgr and hasattr(config_mgr, "config") and hasattr(config_mgr.config, "retry_settings"):
        rc = config_mgr.config.retry_settings
        return (
            getattr(rc, "retries", DEFAULT_RETRIES),
            getattr(rc, "initial_delay", DEFAULT_INITIAL_DELAY),
            getattr(rc, "max_delay", DEFAULT_MAX_DELAY),
            getattr(rc, "backoff_factor", DEFAULT_BACKOFF_FACTOR),
            getattr(rc, "jitter", DEFAULT_JITTER)
        )
    return DEFAULT_RETRIES, DEFAULT_INITIAL_DELAY, DEFAULT_MAX_DELAY, DEFAULT_BACKOFF_FACTOR, DEFAULT_JITTER
