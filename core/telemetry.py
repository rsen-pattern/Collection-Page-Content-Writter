"""Minimal observability — structured JSON log lines emitted to stdout.

Streamlit Cloud's log viewer captures stdout, so this is enough for an
internal tool's production observability without external infrastructure.

Never logs raw prompts, raw responses, API keys, or user-entered USPs /
voice notes. Only operational metadata: model id, generation type, tier
name, duration, success / error class.

If ``print`` fails (closed stdout, weird embedded env), the error is
swallowed silently — telemetry must never break a user request.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Optional


def _sample_rate() -> float:
    """Sample rate read on every call so tests can monkeypatch the env var."""
    try:
        return float(os.environ.get("TELEMETRY_SAMPLE_RATE", "1.0"))
    except (TypeError, ValueError):
        return 1.0


def new_correlation_id() -> str:
    """Generate a short opaque ID for grouping related events.

    12 hex chars is plenty for in-session uniqueness without dominating
    the log line. Use one per logical operation (one full generation,
    one humaniser pass, one batch).
    """
    return uuid.uuid4().hex[:12]


def log_event(event_type: str, correlation_id: str = "", **fields: Any) -> None:
    """Emit one structured log line to stdout.

    ``event_type`` should be a short canonical string (``bifrost_call``,
    ``model_fallback``, ``scrape_attempt``, ``feedback_extraction``).
    ``correlation_id`` groups related events from the same logical operation.

    Honours ``TELEMETRY_SAMPLE_RATE`` env var (0.0 silences everything, 1.0
    emits everything, intermediate values drop a random fraction).

    Errors are swallowed — telemetry must not interrupt a user request.
    """
    try:
        rate = _sample_rate()
        if rate < 1.0 and random.random() >= rate:
            return
        payload: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "event": event_type,
        }
        if correlation_id:
            payload["correlation_id"] = correlation_id
        payload.update(fields)
        print(json.dumps(payload, default=str), file=sys.stdout, flush=True)
    except Exception:
        # Closed stdout, locked file, or anything else — swallow silently.
        pass


@contextmanager
def timed(
    event_type: str,
    correlation_id: str = "",
    **fields: Any,
) -> Iterator[None]:
    """Context manager that emits a timing event on exit.

    On success: emits ``status=ok`` with ``duration_ms``.
    On exception: emits ``status=error`` with ``error=str(e)``, then re-raises.
    ``correlation_id`` is propagated onto the event payload.
    """
    start = time.monotonic()
    try:
        yield
    except Exception as e:
        log_event(
            event_type,
            correlation_id=correlation_id,
            duration_ms=int((time.monotonic() - start) * 1000),
            status="error",
            error=str(e),
            error_type=type(e).__name__,
            **fields,
        )
        raise
    else:
        log_event(
            event_type,
            correlation_id=correlation_id,
            duration_ms=int((time.monotonic() - start) * 1000),
            status="ok",
            **fields,
        )


__all__ = ["log_event", "timed", "new_correlation_id"]
