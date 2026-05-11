"""Adaptive token-bucket rate limiter for Bifrost requests.

Token bucket sized from ``BIFROST_RATE_LIMIT_RPM`` (default 5). When a
caller reports a 429 via ``record_429``, the effective rate is halved
until the recovery window elapses. Thread-safe so Streamlit's threaded
reruns don't trample each other.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Callable, Optional


def _default_rpm() -> int:
    try:
        return max(int(os.environ.get("BIFROST_RATE_LIMIT_RPM", "5")), 1)
    except (TypeError, ValueError):
        return 5


class AdaptiveRateLimiter:
    """Token bucket with adaptive backoff on 429 responses.

    Construction is intentionally cheap — the limiter holds only a
    monotonic-time deque of recent call timestamps and a lock.
    """

    def __init__(
        self,
        initial_rpm: Optional[int] = None,
        recovery_window: float = 60.0,
        time_source: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._configured_rpm = initial_rpm if initial_rpm is not None else _default_rpm()
        self._current_rpm = self._configured_rpm
        self._call_times: deque[float] = deque()
        self._lock = threading.Lock()
        # None when no 429 has been recorded; otherwise the monotonic timestamp.
        self._last_429_at: Optional[float] = None
        self._recovery_window = recovery_window
        self._time = time_source
        self._sleep = sleep

    @property
    def configured_rpm(self) -> int:
        return self._configured_rpm

    @property
    def current_rpm(self) -> int:
        return self._current_rpm

    @property
    def current_interval(self) -> float:
        """Seconds between calls at the current effective rate."""
        return 60.0 / max(self._current_rpm, 1)

    def acquire(self, on_wait: Optional[Callable[[float], None]] = None) -> float:
        """Block until a request slot is available. Returns wait seconds.

        ``on_wait`` is called with the wait duration before sleeping, so
        callers can surface "throttling — waiting Ns" UI status.
        """
        with self._lock:
            self._maybe_recover_locked()
            now = self._time()
            # Drop calls older than 60 seconds from the rolling window.
            while self._call_times and (now - self._call_times[0]) > 60.0:
                self._call_times.popleft()

            if len(self._call_times) < self._current_rpm:
                self._call_times.append(now)
                return 0.0

            oldest = self._call_times[0]
            wait = 60.0 - (now - oldest) + 0.05  # small buffer

        if wait > 0 and on_wait is not None:
            try:
                on_wait(wait)
            except Exception:
                # UI callbacks must never break the limiter.
                pass
        if wait > 0:
            self._sleep(wait)

        with self._lock:
            self._call_times.append(self._time())
        return wait

    def record_429(self) -> None:
        """Mark that a 429 response was received. Halves the effective rate."""
        with self._lock:
            self._last_429_at = self._time()
            self._current_rpm = max(self._configured_rpm // 2, 1)

    def _maybe_recover_locked(self) -> None:
        """Restore the configured RPM after the recovery window. Called under lock."""
        if self._last_429_at is None:
            return
        if (self._time() - self._last_429_at) > self._recovery_window:
            self._current_rpm = self._configured_rpm
            self._last_429_at = None


_limiter: Optional[AdaptiveRateLimiter] = None
_limiter_lock = threading.Lock()


def get_limiter() -> AdaptiveRateLimiter:
    """Return the process-wide limiter, constructing it on first access."""
    global _limiter
    if _limiter is None:
        with _limiter_lock:
            if _limiter is None:
                _limiter = AdaptiveRateLimiter()
    return _limiter


def reset_limiter() -> None:
    """Test hook: drop the module-level limiter so the next get_limiter() builds fresh."""
    global _limiter
    with _limiter_lock:
        _limiter = None


__all__ = ["AdaptiveRateLimiter", "get_limiter", "reset_limiter"]
