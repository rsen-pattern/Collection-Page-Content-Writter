"""Tests for core.session_state — the typed session state schema."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.session_state import (
    AppState,
    AuditEntry,
    AuditInputSnapshot,
    ClientProfile,
    CollectionGroupModel,
    PERSISTENT_FIELDS,
    PromptOverrides,
    client_profile_from_brand_profile,
    collection_group_to_model,
    parse_lenient,
    prompt_overrides_from_brand_overrides,
)


class TestAppStateDefaults:
    def test_empty_app_state_builds(self):
        state = AppState()
        assert state.client_profile.brand_name == ""
        assert state.collection_groups == []
        assert state.generated_content == {}
        assert state.faq_count_or_default() if hasattr(state, "faq_count_or_default") else True

    def test_defaults_are_independent_per_instance(self):
        a = AppState()
        b = AppState()
        a.batch_faq_topics.append("x")
        assert b.batch_faq_topics == []

    def test_persistent_fields_match_actual_field_names(self):
        for name in PERSISTENT_FIELDS:
            assert name in AppState.model_fields, f"PERSISTENT_FIELDS lists unknown field {name!r}"


class TestParseLenient:
    def test_accepts_valid_dict(self):
        state = parse_lenient({"bifrost_api_key": "sk-test", "humanize_enabled": True})
        assert state.bifrost_api_key == "sk-test"
        assert state.humanize_enabled is True

    def test_accepts_extra_keys_without_error(self):
        state = parse_lenient({"bifrost_api_key": "sk-test", "_unknown_key": "x"})
        assert state.bifrost_api_key == "sk-test"
        # Extra keys are silently ignored — no exception.

    def test_coerces_invalid_faq_count_via_field_recovery(self):
        with patch("core.session_state.log_event") as mock_log:
            state = parse_lenient({"client_profile": {"faq_count": "not_a_number"}})
        # FAQ count should fall back to default since coercion failed.
        assert state.client_profile.faq_count == 4
        # Telemetry recorded the recovery.
        events = [call.args[0] for call in mock_log.call_args_list]
        assert "session_state_parse_failed" in events or "session_state_field_coerced" in events

    def test_recovers_field_by_field_when_full_parse_fails(self):
        # ``faq_count`` outside [3, 8] triggers validation failure.
        raw = {
            "bifrost_api_key": "sk-keep",
            "client_profile": {"faq_count": 99},
        }
        with patch("core.session_state.log_event"):
            state = parse_lenient(raw)
        # The good field is preserved even though the bad one was coerced.
        assert state.bifrost_api_key == "sk-keep"


class TestInvariants:
    def test_batch_without_collections_is_cleared(self):
        with patch("core.session_state.log_event") as mock_log:
            state = AppState.model_validate({
                "collection_groups": [],
                "batch_collections": [{"collection_url": "u1"}],
            })
        assert state.batch_collections == []
        events = [call.args[0] for call in mock_log.call_args_list]
        assert "session_state_invariant_violated" in events

    def test_batch_with_collections_survives(self):
        state = AppState.model_validate({
            "collection_groups": [{"collection_url": "u1"}],
            "batch_collections": [{"collection_url": "u1"}],
        })
        assert len(state.batch_collections) == 1

    def test_orphan_generated_content_logs_but_keeps_data(self):
        with patch("core.session_state.log_event") as mock_log:
            state = AppState.model_validate({
                "collection_groups": [{"collection_url": "u1"}],
                "batch_collections": [{"collection_url": "u1"}],
                "generated_content": {
                    "u1": {"description": "in batch"},
                    "u_orphan": {"description": "from prior batch"},
                },
            })
        # Both entries survive — orphan_generated_content only logs.
        assert len(state.generated_content) == 2
        events = [call.args[0] for call in mock_log.call_args_list]
        rules = [c.kwargs.get("rule") for c in mock_log.call_args_list]
        assert "orphan_generated_content" in rules

    def test_audit_entry_without_result_is_dropped(self):
        with patch("core.session_state.log_event") as mock_log:
            state = AppState.model_validate({
                "audit_results": {
                    "u1": {"result": "ok", "input": {"seo_title": "T"}},
                    "u_bad": {"result": None, "input": {"seo_title": "T"}},
                },
            })
        assert "u1" in state.audit_results
        assert "u_bad" not in state.audit_results
        rules = [c.kwargs.get("rule") for c in mock_log.call_args_list]
        assert "audit_missing_result" in rules


class TestConversionHelpers:
    def _make_brand_profile(self):
        from core.brand_profile import BrandProfile, BrandPromptOverrides
        return BrandProfile(
            brand_name="Stanley",
            store_url="https://stanley.com",
            brand_usps=["BUILT FOR LIFE", "Lifetime warranty"],
            voice_notes="Direct.",
            target_market="AU",
            faq_count=5,
            past_feedback="Stop using 'perfect for'.",
            humanize_by_default=True,
            sitemap_url="https://stanley.com/sitemap.xml",
            sitemap_parsed={"products": []},
            sitemap_fetched_at="2026-05-11T12:00:00Z",
            prompt_overrides=BrandPromptOverrides(
                brand_custom_rules="rule",
                voice_examples="ex",
                alt_text_rules="alt rule",
                alt_text_examples="alt ex",
                banned_phrases=["perfect for"],
                dedup_overrides={"shirts": "shirts-distinct"},
            ),
        )

    def test_client_profile_from_brand_profile_round_trip(self):
        bp = self._make_brand_profile()
        cp = client_profile_from_brand_profile(bp)
        assert cp.brand_name == "Stanley"
        assert cp.brand_usps == ["BUILT FOR LIFE", "Lifetime warranty"]
        assert cp.faq_count == 5
        assert cp.humanize_by_default is True
        assert cp.sitemap_url == "https://stanley.com/sitemap.xml"
        assert cp.sitemap_parsed == {"products": []}
        assert cp.sitemap_fetched_at == "2026-05-11T12:00:00Z"
        assert cp.past_feedback == "Stop using 'perfect for'."

    def test_prompt_overrides_from_brand_overrides_round_trip(self):
        bp = self._make_brand_profile()
        po = prompt_overrides_from_brand_overrides(bp.prompt_overrides)
        assert po.brand_custom_rules == "rule"
        assert po.banned_phrases == ["perfect for"]
        assert po.dedup_overrides == {"shirts": "shirts-distinct"}

    def test_prompt_overrides_handles_missing_dedup_overrides(self):
        from core.brand_profile import BrandPromptOverrides
        bo = BrandPromptOverrides()  # no dedup_overrides set
        po = prompt_overrides_from_brand_overrides(bo)
        assert po.dedup_overrides == {}

    def test_collection_group_to_model_from_dataclass(self):
        from core.data_ingestion import CollectionGroup
        cg = CollectionGroup(
            collection_url="https://x.com/collections/y",
            collection_name="Y",
            primary_keyword="y",
            secondary_keywords=[{"keyword": "y2", "search_volume": 100}],
            total_volume=500,
        )
        model = collection_group_to_model(cg)
        assert model.collection_url == "https://x.com/collections/y"
        assert model.primary_keyword == "y"
        assert model.total_volume == 500
        assert model.secondary_keywords == [{"keyword": "y2", "search_volume": 100}]

    def test_collection_group_to_model_pass_through(self):
        model = CollectionGroupModel(collection_url="u", collection_name="N", primary_keyword="k")
        assert collection_group_to_model(model) is model

    def test_collection_group_to_model_from_dict(self):
        result = collection_group_to_model(
            {"collection_url": "u", "collection_name": "N", "primary_keyword": "k"}
        )
        assert isinstance(result, CollectionGroupModel)
        assert result.collection_url == "u"
