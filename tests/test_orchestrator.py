"""Tests for core.orchestrator — the pure-Python batch generation driver."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.orchestrator import (
    GenerationConfig,
    GenerationResult,
    generate_for_batch,
)
from core.brief_builder import ContentBrief
from core.content_generator import GeneratedContent


def _brief(url, name="N"):
    return ContentBrief(
        collection_url=url,
        collection_name=name,
        primary_keyword="kw",
    )


def _fake_generate(api_key, brief, generation_type, model, base_url, batch_faq_topics, on_wait=None, **kwargs):
    return (
        GeneratedContent(
            collection_url=brief.collection_url,
            collection_name=brief.collection_name,
            seo_title=f"T-{brief.collection_url}",
            collection_title=f"H-{brief.collection_url}",
            description=f"D-{brief.collection_url}",
            meta_description="M",
            faqs=[{"question": "Q", "answer": "A"}],
            suggested_headings=["H1"],
            suggested_tags=["t"],
        ),
        model,
    )


@pytest.fixture
def patched_generate(monkeypatch):
    """Replace network-touching content_generator functions with fakes."""
    import core.orchestrator as orchestrator_mod
    # Patch the names as imported inside _generate_one via lazy import.
    import core.content_generator as cg_mod
    monkeypatch.setattr(cg_mod, "generate_content", _fake_generate)

    def _fake_humanize(api_key, content_text, brand_name, voice_notes, model, base_url, on_wait=None):
        return content_text + " [humanised]", model

    monkeypatch.setattr(cg_mod, "humanize_content", _fake_humanize)
    return orchestrator_mod


class TestGenerateForBatch:
    def test_processes_each_brief_in_order(self, patched_generate):
        config = GenerationConfig(api_key="sk-x", model="m")
        briefs = [_brief("u1"), _brief("u2"), _brief("u3")]
        results = generate_for_batch(briefs, config)
        assert [r.brief.collection_url for r in results] == ["u1", "u2", "u3"]
        assert all(r.success for r in results)
        assert all(not r.skipped for r in results)

    def test_skips_already_generated_unless_force(self, patched_generate):
        config = GenerationConfig(api_key="sk-x")
        briefs = [_brief("u1"), _brief("u2")]
        existing = {"u1": {"seo_title": "Existing"}}
        results = generate_for_batch(briefs, config, already_generated=existing)
        # u1 skipped (success=True but skipped=True, content carried from cache)
        assert results[0].success and results[0].skipped
        assert results[0].content == {"seo_title": "Existing"}
        # u2 ran normally
        assert results[1].success and not results[1].skipped

    def test_force_regenerate_overrides_skip(self, patched_generate):
        config = GenerationConfig(api_key="sk-x", force_regenerate=True)
        briefs = [_brief("u1")]
        existing = {"u1": {"seo_title": "Old"}}
        results = generate_for_batch(briefs, config, already_generated=existing)
        assert not results[0].skipped
        assert results[0].content["seo_title"] == "T-u1"  # freshly generated

    def test_humanize_runs_when_enabled(self, patched_generate):
        config = GenerationConfig(api_key="sk-x", humanize_enabled=True)
        results = generate_for_batch([_brief("u1")], config)
        assert results[0].content["description"].endswith("[humanised]")

    def test_cancel_check_short_circuits(self, patched_generate):
        config = GenerationConfig(api_key="sk-x")
        briefs = [_brief("u1"), _brief("u2"), _brief("u3")]
        results = generate_for_batch(
            briefs, config, cancel_check=lambda: True
        )
        assert all(r.cancelled for r in results)
        assert all(not r.success for r in results)
        # Order is preserved even when cancelled.
        assert [r.brief.collection_url for r in results] == ["u1", "u2", "u3"]

    def test_callbacks_fire_in_order(self, patched_generate):
        config = GenerationConfig(api_key="sk-x")
        briefs = [_brief("u1"), _brief("u2")]
        events = []
        generate_for_batch(
            briefs,
            config,
            on_start=lambda b, i, t: events.append(("start", b.collection_url, i, t)),
            on_progress=lambda r, i, t: events.append(("progress", r.brief.collection_url, i, t)),
        )
        # Each brief fires start then progress, in batch order.
        assert events == [
            ("start", "u1", 0, 2),
            ("progress", "u1", 0, 2),
            ("start", "u2", 1, 2),
            ("progress", "u2", 1, 2),
        ]

    def test_generation_failure_packed_into_result(self, monkeypatch):
        def _raises(*args, **kwargs):
            raise RuntimeError("boom")
        import core.content_generator as cg_mod
        monkeypatch.setattr(cg_mod, "generate_content", _raises)

        config = GenerationConfig(api_key="sk-x")
        results = generate_for_batch([_brief("u1")], config)
        assert not results[0].success
        assert "boom" in results[0].error
        assert results[0].content == {}

    def test_callback_exceptions_swallowed(self, patched_generate):
        """A broken callback must not stop the batch."""
        config = GenerationConfig(api_key="sk-x")
        briefs = [_brief("u1"), _brief("u2")]

        def boom(*args, **kwargs):
            raise RuntimeError("ui broke")

        results = generate_for_batch(briefs, config, on_progress=boom)
        # Both still ran successfully despite the callback raising.
        assert len(results) == 2
        assert all(r.success for r in results)
