"""Tests for brand_profile module."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.brand_profile import (
    BrandProfile,
    BrandPromptOverrides,
    save_profile,
    load_profile,
    list_profiles,
    build_custom_rules_block,
)


@pytest.fixture(autouse=True)
def tmp_profiles_dir(tmp_path, monkeypatch):
    """Redirect profile storage to a temp directory for test isolation."""
    import core.brand_profile as bp_module
    monkeypatch.setattr(bp_module, "_PROFILES_DIR", tmp_path / "profiles")


class TestBrandProfileRoundtrip:
    def test_save_then_load_preserves_all_fields(self):
        profile = BrandProfile(
            brand_name="Stanley AU",
            store_url="https://stanley.com.au",
            brand_usps=["BUILT FOR LIFE", "Lifetime warranty"],
            voice_notes="Direct, confident tone.",
            target_market="AU",
            faq_count=5,
            prompt_overrides=BrandPromptOverrides(
                brand_custom_rules="Always mention warranty.",
                voice_examples="Shop the range.",
            ),
        )
        save_profile(profile)
        loaded = load_profile("Stanley AU")
        assert loaded is not None
        assert loaded.brand_name == "Stanley AU"
        assert loaded.store_url == "https://stanley.com.au"
        assert loaded.brand_usps == ["BUILT FOR LIFE", "Lifetime warranty"]
        assert loaded.faq_count == 5
        assert loaded.prompt_overrides.brand_custom_rules == "Always mention warranty."

    def test_save_then_load_preserves_faq_count(self):
        save_profile(BrandProfile(brand_name="Stanley", faq_count=5))
        loaded = load_profile("Stanley")
        assert loaded.faq_count == 5

    def test_faq_count_defaults_to_4(self):
        p = BrandProfile(brand_name="X")
        assert p.faq_count == 4

    def test_from_dict_defaults_missing_faq_count(self):
        data = {"brand_name": "Y", "brand_usps": []}
        p = BrandProfile.from_dict(data)
        assert p.faq_count == 4

    def test_load_returns_none_when_not_found(self):
        assert load_profile("NonExistentBrand") is None

    def test_alt_text_overrides_persist(self):
        profile = BrandProfile(
            brand_name="X",
            prompt_overrides=BrandPromptOverrides(
                alt_text_rules="Always mention colour first.",
                alt_text_examples="Charcoal stainless steel tumbler",
            ),
        )
        save_profile(profile)
        loaded = load_profile("X")
        assert loaded.prompt_overrides.alt_text_rules == "Always mention colour first."
        assert loaded.prompt_overrides.alt_text_examples == "Charcoal stainless steel tumbler"

    def test_list_profiles_returns_saved_names(self):
        save_profile(BrandProfile(brand_name="Alpha"))
        save_profile(BrandProfile(brand_name="Beta"))
        names = list_profiles()
        assert "Alpha" in names
        assert "Beta" in names


class TestPastFeedback:
    def test_save_then_load_preserves_past_feedback(self):
        save_profile(BrandProfile(
            brand_name="Stanley",
            past_feedback="Client rejected 'perfect for' twice. Stop using it."
        ))
        loaded = load_profile("Stanley")
        assert "perfect for" in loaded.past_feedback

    def test_past_feedback_appears_in_brand_context(self):
        from core.brand_profile import build_brand_custom_context
        ctx = build_brand_custom_context({
            "past_feedback": "Don't use 'discover our range' — rejected.",
            "prompt_overrides": {},
        })
        assert "PAST FEEDBACK" in ctx
        assert "discover our range" in ctx

    def test_empty_past_feedback_no_section(self):
        from core.brand_profile import build_brand_custom_context
        ctx = build_brand_custom_context({"past_feedback": "", "prompt_overrides": {}})
        assert "PAST FEEDBACK" not in ctx

    def test_banned_phrases_appear_in_context(self):
        from core.brand_profile import build_brand_custom_context
        ctx = build_brand_custom_context({
            "past_feedback": "",
            "prompt_overrides": {"banned_phrases": ["perfect for", "discover our range"]},
        })
        assert "BRAND-BANNED PHRASES" in ctx
        assert "perfect for" in ctx

    def test_empty_banned_phrases_no_section(self):
        from core.brand_profile import build_brand_custom_context
        ctx = build_brand_custom_context({"past_feedback": "", "prompt_overrides": {"banned_phrases": []}})
        assert "BRAND-BANNED PHRASES" not in ctx

    def test_from_dict_defaults_missing_past_feedback(self):
        data = {"brand_name": "Y", "brand_usps": []}
        p = BrandProfile.from_dict(data)
        assert p.past_feedback == ""

    def test_banned_phrases_round_trip(self):
        profile = BrandProfile(
            brand_name="X",
            prompt_overrides=BrandPromptOverrides(
                banned_phrases=["perfect for", "discover our range"],
            ),
        )
        save_profile(profile)
        loaded = load_profile("X")
        assert loaded.prompt_overrides.banned_phrases == ["perfect for", "discover our range"]


class TestBuildCustomRulesBlock:
    def test_alt_text_uses_alt_fields(self):
        overrides = BrandPromptOverrides(
            alt_text_rules="Mention colour.",
            alt_text_examples="Red t-shirt with pocket",
        )
        block = build_custom_rules_block(overrides, "alt_text")
        assert "Mention colour." in block
        assert "Red t-shirt with pocket" in block
        assert "BRAND-SPECIFIC RULES" not in block

    def test_other_element_uses_brand_fields(self):
        overrides = BrandPromptOverrides(
            brand_custom_rules="Always mention warranty.",
            voice_examples="Shop the range.",
        )
        block = build_custom_rules_block(overrides, "bottom_copy")
        assert "Always mention warranty." in block
        assert "Shop the range." in block

    def test_empty_overrides_returns_empty_string(self):
        overrides = BrandPromptOverrides()
        assert build_custom_rules_block(overrides, "alt_text") == ""
        assert build_custom_rules_block(overrides, "full_brief") == ""
