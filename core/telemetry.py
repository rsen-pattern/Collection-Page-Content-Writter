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
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator


def log_event(event_type: str, **fields: Any) -> None:
    """Emit one structured log line to stdout.

    ``event_type`` should be a short canonical string (``bifrost_call``,
    ``model_fallback``, ``scrape_attempt``, ``feedback_extraction``).
    Anything passed in ``fields`` is JSON-encoded as the payload, with
    non-serialisable values stringified via ``default=str``.

    Errors are swallowed — telemetry must not interrupt a user request.
    """
    try:
        payload = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "event": event_type,
            **fields,
        }
        print(json.dumps(payload, default=str), file=sys.stdout, flush=True)
    except Exception:
        # Closed stdout, locked file, or anything else — swallow silently.
        pass


@contextmanager
def timed(event_type: str, **fields: Any) -> Iterator[None]:
    """Context manager that emits a timing event on exit.

    On success: emits ``status=ok`` with ``duration_ms``.
    On exception: emits ``status=error`` with ``error=str(e)``, then re-raises.
    """
    start = time.monotonic()
    try:
        yield
    except Exception as e:
        log_event(
            event_type,
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
            duration_ms=int((time.monotonic() - start) * 1000),
            status="ok",
            **fields,
        )


__all__ = ["log_event", "timed"]
