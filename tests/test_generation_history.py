"""Tests for core.generation_history — snapshot, append, restore."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.generation_history import (
    MAX_HISTORY,
    SNAPSHOT_FIELDS,
    append_snapshot,
    has_meaningful_content,
    restore_snapshot,
)


def _sample_content(suffix=""):
    return {
        "seo_title": f"Title{suffix}",
        "collection_title": f"H1{suffix}",
        "description": f"Desc{suffix}",
        "meta_description": f"Meta{suffix}",
        "faqs": [{"question": f"Q{suffix}", "answer": "A"}],
        "suggested_headings": [f"Heading{suffix}"],
        "suggested_tags": [f"tag{suffix}"],
        "approved": False,
    }


class TestAppendSnapshot:
    def test_appends_entry_with_metadata(self):
        content = _sample_content("v1")
        append_snapshot(
            content,
            generation_type="full",
            model_used="anthropic/claude-sonnet-4-6",
            humanized=True,
            timestamp="2026-05-11T14:32:00Z",
        )
        assert len(content["history"]) == 1
        entry = content["history"][0]
        assert entry["model_used"] == "anthropic/claude-sonnet-4-6"
        assert entry["generation_type"] == "full"
        assert entry["humanized"] is True
        assert entry["timestamp"] == "2026-05-11T14:32:00Z"

    def test_snapshot_captures_only_snapshot_fields(self):
        content = _sample_content("v1")
        content["approved"] = True
        content["_internal_metadata"] = "leak?"
        append_snapshot(content, generation_type="full")
        snapshot = content["history"][0]["snapshot"]
        # Every captured key is a known snapshot field — nothing else
        # leaks in. (Fields absent from `content` are simply not present
        # in the snapshot; that's expected.)
        assert set(snapshot.keys()).issubset(set(SNAPSHOT_FIELDS))
        # Non-snapshot fields are not recursively captured.
        assert "approved" not in snapshot
        assert "_internal_metadata" not in snapshot
        assert "history" not in snapshot

    def test_caps_at_max_history(self):
        content = _sample_content("v0")
        for i in range(MAX_HISTORY + 5):
            content["description"] = f"v{i}"
            append_snapshot(content, generation_type="full")
        assert len(content["history"]) == MAX_HISTORY
        # Most recent entry's snapshot reflects the most recent description
        # (one before the final overwrite). The final append captures the
        # description at the point of the call — i.e. v(MAX_HISTORY + 4).
        assert content["history"][-1]["snapshot"]["description"] == f"v{MAX_HISTORY + 4}"

    def test_handles_missing_history_key(self):
        content = _sample_content("v1")
        assert "history" not in content
        append_snapshot(content, generation_type="full")
        assert content["history"]

    def test_none_content_is_no_op(self):
        # Should not raise.
        append_snapshot(None, generation_type="full")


class TestRestoreSnapshot:
    def test_restore_brings_back_snapshot_fields(self):
        content = _sample_content("current")
        snapshot = _sample_content("old")
        # Filter snapshot to only snapshot fields, like append_snapshot does.
        snapshot_clean = {k: snapshot[k] for k in SNAPSHOT_FIELDS if k in snapshot}
        restore_snapshot(content, snapshot_clean)
        assert content["seo_title"] == "Titleold"
        assert content["description"] == "Descold"

    def test_restore_preserves_history(self):
        content = _sample_content("current")
        content["history"] = [{"timestamp": "2026-05-01T00:00:00Z", "snapshot": {}}]
        snapshot = {"seo_title": "old", "description": "old desc"}
        restore_snapshot(content, snapshot)
        # History list survives the restore so the action is itself reversible.
        assert content["history"]
        assert content["history"][0]["timestamp"] == "2026-05-01T00:00:00Z"
        assert content["seo_title"] == "old"

    def test_restore_with_empty_snapshot_is_no_op(self):
        content = _sample_content("current")
        before = dict(content)
        restore_snapshot(content, {})
        for key in before:
            assert content[key] == before[key]


class TestHasMeaningfulContent:
    def test_returns_true_when_any_snapshot_field_set(self):
        assert has_meaningful_content({"description": "x"})
        assert has_meaningful_content({"seo_title": "x"})

    def test_returns_false_when_empty(self):
        assert not has_meaningful_content({})
        assert not has_meaningful_content({"approved": True})  # not a snapshot field

    def test_returns_false_when_all_snapshot_fields_falsy(self):
        empty = {key: "" for key in SNAPSHOT_FIELDS}
        empty["faqs"] = []
        empty["suggested_headings"] = []
        empty["suggested_tags"] = []
        assert not has_meaningful_content(empty)
