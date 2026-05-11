"""Tests for core.rate_limiter.AdaptiveRateLimiter.

Uses fake time and sleep functions so tests run instantly with deterministic
behaviour, no real waiting.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.rate_limiter import AdaptiveRateLimiter


class _Clock:
    """Manually advanced clock + sleep accumulator."""

    def __init__(self):
        self.t = 0.0
        self.slept = 0.0

    def now(self):
        return self.t

    def sleep(self, seconds: float):
        self.slept += seconds
        self.t += seconds  # sleep advances the clock


def _limiter(rpm, clock):
    return AdaptiveRateLimiter(
        initial_rpm=rpm,
        recovery_window=60.0,
        time_source=clock.now,
        sleep=clock.sleep,
    )


class TestAcquire:
    def test_first_n_calls_return_immediately(self):
        clock = _Clock()
        lim = _limiter(rpm=3, clock=clock)
        assert lim.acquire() == 0.0
        assert lim.acquire() == 0.0
        assert lim.acquire() == 0.0
        # Three slots consumed, no sleep so far.
        assert clock.slept == 0.0

    def test_fourth_call_at_rpm_3_waits(self):
        clock = _Clock()
        lim = _limiter(rpm=3, clock=clock)
        for _ in range(3):
            lim.acquire()
        wait = lim.acquire()
        # The oldest of the three slots was at t=0, now is also t=0, so the
        # bucket waits ~60s for the oldest call to leave the rolling window.
        assert wait > 59
        assert wait < 61

    def test_on_wait_callback_fired(self):
        clock = _Clock()
        lim = _limiter(rpm=1, clock=clock)
        lim.acquire()
        waits = []
        lim.acquire(on_wait=waits.append)
        assert len(waits) == 1
        assert waits[0] > 0


class TestRecord429:
    def test_record_429_halves_rate(self):
        clock = _Clock()
        lim = _limiter(rpm=10, clock=clock)
        assert lim.current_rpm == 10
        lim.record_429()
        assert lim.current_rpm == 5

    def test_recovery_after_window(self):
        clock = _Clock()
        lim = _limiter(rpm=10, clock=clock)
        lim.record_429()
        assert lim.current_rpm == 5
        # Advance past the recovery window so the next acquire triggers recovery.
        clock.t += 61.0
        lim.acquire()
        assert lim.current_rpm == 10

    def test_429_floor_is_1(self):
        clock = _Clock()
        lim = _limiter(rpm=1, clock=clock)
        lim.record_429()
        # Even at rpm=1, halving floors to 1 — never zero.
        assert lim.current_rpm == 1


class TestConfig:
    def test_default_rpm_from_env(self, monkeypatch):
        from core.rate_limiter import _default_rpm
        monkeypatch.setenv("BIFROST_RATE_LIMIT_RPM", "12")
        assert _default_rpm() == 12

    def test_default_rpm_invalid_falls_back(self, monkeypatch):
        from core.rate_limiter import _default_rpm
        monkeypatch.setenv("BIFROST_RATE_LIMIT_RPM", "not-a-number")
        assert _default_rpm() == 5

    def test_module_level_get_limiter_is_singleton(self):
        from core.rate_limiter import get_limiter, reset_limiter
        reset_limiter()
        a = get_limiter()
        b = get_limiter()
        assert a is b
        reset_limiter()
