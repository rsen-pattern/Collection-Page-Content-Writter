"""Tests for core.content_cache."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.content_cache import (
    diff_inputs,
    hash_inputs,
    load_from_cache,
    save_to_cache,
)
import core.content_cache as cc


@pytest.fixture(autouse=True)
def tmp_cache_dir(tmp_path, monkeypatch):
    """Redirect cache storage to a tmp directory for test isolation."""
    monkeypatch.setattr(cc, "_CACHE_DIR", tmp_path / "content_cache")


class _Brief:
    """Stand-in for ContentBrief — only the attributes hash_inputs reads."""

    def __init__(self, secondary_keywords=None, brand_usps=None, voice_notes="", past_feedback=""):
        self.secondary_keywords = list(secondary_keywords or [])
        self.brand_usps = list(brand_usps or [])
        self.voice_notes = voice_notes
        self.past_feedback = past_feedback


class TestSaveAndLoad:
    def test_round_trip(self):
        payload = {"description": "Hello", "approved": False}
        inputs = {"secondary_kws_hash": "x", "usps_hash": "y", "voice_hash": "", "past_feedback_hash": ""}
        path = save_to_cache("Test Brand", "https://x.com/collections/y", "primary kw", payload, inputs)
        assert path.exists()

        loaded = load_from_cache("Test Brand", "https://x.com/collections/y", "primary kw")
        assert loaded is not None
        assert loaded["content"] == payload
        assert loaded["inputs"] == inputs

    def test_load_returns_none_for_missing_cache(self):
        assert load_from_cache("X", "https://x.com/collections/missing", "kw") is None

    def test_safe_filename_for_unicode_brand(self):
        # Should not raise. Unicode brand collapsed via _safe_brand_name.
        save_to_cache("Pâtisserie Ü 🥐", "https://x.com/collections/y", "kw", {"x": 1}, {})
        loaded = load_from_cache("Pâtisserie Ü 🥐", "https://x.com/collections/y", "kw")
        assert loaded is not None

    def test_primary_keyword_case_insensitive(self):
        # Lowercased before hashing — "X" and "x" land in the same cache slot.
        save_to_cache("B", "https://x.com/collections/y", "Tumblers", {"v": "upper"}, {})
        loaded = load_from_cache("B", "https://x.com/collections/y", "tumblers")
        assert loaded is not None
        assert loaded["content"] == {"v": "upper"}


class TestHashInputs:
    def test_returns_all_four_hashes(self):
        brief = _Brief(
            secondary_keywords=["a", "b"],
            brand_usps=["U1", "U2"],
            voice_notes="warm",
            past_feedback="past",
        )
        result = hash_inputs(brief)
        assert set(result.keys()) == {"secondary_kws_hash", "usps_hash", "voice_hash", "past_feedback_hash"}
        for v in result.values():
            assert len(v) == 16

    def test_order_independence_of_lists(self):
        a = _Brief(secondary_keywords=["a", "b", "c"])
        b = _Brief(secondary_keywords=["c", "b", "a"])
        assert hash_inputs(a)["secondary_kws_hash"] == hash_inputs(b)["secondary_kws_hash"]


class TestDiffInputs:
    def test_returns_labels_for_changed_fields(self):
        old = {"secondary_kws_hash": "a", "usps_hash": "u", "voice_hash": "v", "past_feedback_hash": "p"}
        new = {"secondary_kws_hash": "b", "usps_hash": "u", "voice_hash": "DIFF", "past_feedback_hash": "p"}
        assert diff_inputs(old, new) == ["secondary keywords", "voice notes"]

    def test_no_changes_returns_empty(self):
        old = {"secondary_kws_hash": "a", "usps_hash": "u", "voice_hash": "v", "past_feedback_hash": "p"}
        assert diff_inputs(old, old) == []
