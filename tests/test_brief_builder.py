"""Tests for brief_builder: KD-scaled word counts and brief construction."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.brief_builder import (
    calculate_target_word_counts,
    calculate_target_word_count,
    build_brief,
    build_briefs_for_batch,
)


class TestCalculateTargetWordCounts:
    def test_low_kd_keeps_bottom_short(self):
        _, bottom = calculate_target_word_counts(15)
        assert bottom == 125

    def test_medium_kd_returns_standard(self):
        _, bottom = calculate_target_word_counts(30)
        assert bottom == 250

    def test_medium_high_kd_returns_substantial(self):
        _, bottom = calculate_target_word_counts(45)
        assert bottom == 500

    def test_high_kd_returns_deep(self):
        _, bottom = calculate_target_word_counts(70)
        assert bottom == 800

    def test_no_kd_returns_safe_midpoint(self):
        _, bottom = calculate_target_word_counts(None)
        assert bottom == 200

    def test_top_target_unchanged_at_low_kd(self):
        top, _ = calculate_target_word_counts(15)
        # low KD → top_min + 5 = 55
        assert top == 55

    def test_boundary_kd_60_returns_deep(self):
        _, bottom = calculate_target_word_counts(60)
        assert bottom == 800

    def test_boundary_kd_40_returns_substantial(self):
        _, bottom = calculate_target_word_counts(40)
        assert bottom == 500

    def test_boundary_kd_20_returns_standard(self):
        _, bottom = calculate_target_word_counts(20)
        assert bottom == 250

    def test_boundary_kd_19_returns_short(self):
        _, bottom = calculate_target_word_counts(19)
        assert bottom == 125


class TestCalculateTargetWordCountBackwardCompat:
    def test_returns_bottom_target(self):
        assert calculate_target_word_count(70) == 800

    def test_none_returns_midpoint(self):
        assert calculate_target_word_count(None) == 200


class TestBuildBrief:
    def _make_brief(self, kd=None, faq_count=4):
        return build_brief(
            collection_url="https://x.com/collections/y",
            collection_name="Y",
            primary_keyword="y keyword",
            primary_keyword_volume=1000,
            secondary_keywords=[],
            brand_usps=["Quality"],
            brand_name="Brand",
            store_url="https://x.com",
            keyword_difficulty=kd,
            faq_count=faq_count,
        )

    def test_target_bottom_word_count_set_for_high_kd(self):
        brief = self._make_brief(kd=70)
        assert brief.target_bottom_word_count == 800

    def test_target_word_count_mirrors_bottom(self):
        brief = self._make_brief(kd=70)
        assert brief.target_word_count == brief.target_bottom_word_count

    def test_faq_count_default_is_4(self):
        brief = self._make_brief()
        assert brief.faq_count == 4

    def test_faq_count_override(self):
        brief = self._make_brief(faq_count=5)
        assert brief.faq_count == 5


class TestBuildBriefsBatch:
    def test_uses_brand_profile_faq_count(self):
        profile = {
            "brand_name": "X",
            "brand_usps": [],
            "store_url": "https://x.com",
            "faq_count": 5,
        }
        collections = [{
            "collection_url": "https://x.com/collections/y",
            "collection_name": "Y",
            "primary_keyword": "y",
        }]
        briefs = build_briefs_for_batch(collections, profile)
        assert briefs[0].faq_count == 5

    def test_defaults_faq_count_to_4(self):
        profile = {"brand_name": "X", "brand_usps": [], "store_url": ""}
        collections = [{
            "collection_url": "https://x.com/collections/y",
            "collection_name": "Y",
            "primary_keyword": "y",
        }]
        briefs = build_briefs_for_batch(collections, profile)
        assert briefs[0].faq_count == 4

    def test_wires_scraped_existing_content(self):
        profile = {"brand_name": "X", "brand_usps": [], "store_url": ""}
        collections = [{
            "collection_url": "https://x.com/collections/y",
            "collection_name": "Y",
            "primary_keyword": "y",
            "existing_top_copy": "Top copy here.",
            "existing_bottom_copy": "Bottom copy here.",
        }]
        briefs = build_briefs_for_batch(collections, profile)
        assert "Top copy here." in briefs[0].existing_content
        assert "Bottom copy here." in briefs[0].existing_content
