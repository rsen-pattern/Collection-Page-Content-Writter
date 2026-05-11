"""Tests for core.telemetry."""

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.telemetry import log_event, timed


def _capture_stdout(fn, *args, **kwargs):
    buf = io.StringIO()
    with patch("sys.stdout", buf):
        result = fn(*args, **kwargs)
    return result, buf.getvalue()


class TestLogEvent:
    def test_emits_valid_json_with_event_and_ts(self):
        _, out = _capture_stdout(log_event, "bifrost_call", model="m", status="ok")
        line = out.strip()
        # Single line of JSON
        assert "\n" not in line
        payload = json.loads(line)
        assert payload["event"] == "bifrost_call"
        assert payload["model"] == "m"
        assert payload["status"] == "ok"
        assert "ts" in payload and payload["ts"].endswith("Z")

    def test_serialises_unusual_types(self):
        _, out = _capture_stdout(log_event, "x", value={1, 2}, path=Path("/tmp/x"))
        payload = json.loads(out.strip())
        # Sets serialise to their repr via default=str
        assert payload["event"] == "x"
        assert "value" in payload
        assert "path" in payload

    def test_swallows_print_exception(self):
        """A broken stdout must not propagate as an error to the caller."""
        bad = io.StringIO()
        bad.close()
        with patch("sys.stdout", bad):
            # Should not raise
            log_event("x", foo="bar")


class TestTimed:
    def test_emits_status_ok_on_success(self):
        with patch("sys.stdout", io.StringIO()) as buf:
            with timed("scrape_attempt", tier="direct"):
                pass
        payload = json.loads(buf.getvalue().strip())
        assert payload["event"] == "scrape_attempt"
        assert payload["status"] == "ok"
        assert payload["tier"] == "direct"
        assert "duration_ms" in payload

    def test_emits_status_error_and_reraises(self):
        with patch("sys.stdout", io.StringIO()) as buf:
            with pytest.raises(RuntimeError, match="boom"):
                with timed("scrape_attempt", tier="direct"):
                    raise RuntimeError("boom")
        payload = json.loads(buf.getvalue().strip())
        assert payload["status"] == "error"
        assert payload["error"] == "boom"
        assert payload["error_type"] == "RuntimeError"
