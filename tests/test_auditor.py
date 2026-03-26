"""Tests for audit engine."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.auditor import (
    CollectionAuditData,
    audit_collection,
    get_priority_actions,
    get_category_scores,
    _check_keyword_match,
    _count_links,
)


@pytest.fixture
def good_collection():
    return CollectionAuditData(
        collection_url="https://example.com/collections/waterproof-necklaces",
        collection_name="Waterproof Necklaces",
        primary_keyword="waterproof necklaces",
        seo_title="Waterproof Necklaces | Gold & Silver | For Sale at Lunar",
        h1="Waterproof Necklaces",
        description=(
            "Discover our stunning collection of waterproof necklaces, handcrafted in London "
            "using recycled precious metals. Each piece comes with a lifetime warranty and is "
            "100% waterproof — perfect for wearing in the shower, swimming, or sleeping. "
            "Browse our [gold chains](/collections/gold-chains) and [silver pendants](/products/silver-pendant) "
            "or explore our [earrings collection](/collections/earrings). "
            "All our waterproof jewelry is hypoallergenic and nickel-free."
        ),
        meta_description="Shop waterproof necklaces handcrafted in London. 100% waterproof, lifetime warranty. Browse now.",
        brand_usps=[
            "Handcrafted in London using recycled precious metals",
            "100% waterproof",
            "Lifetime warranty",
            "Hypoallergenic",
        ],
        url_handle="waterproof-necklaces",
    )


@pytest.fixture
def poor_collection():
    return CollectionAuditData(
        collection_url="https://example.com/collections/rings",
        collection_name="Rings",
        primary_keyword="silver rings",
        seo_title="Rings",
        h1="Rings",
        description="",
        meta_description="",
        brand_usps=["Handcrafted", "Waterproof"],
    )


class TestKeywordMatch:
    def test_exact_match(self):
        assert _check_keyword_match("Buy waterproof necklaces today", "waterproof necklaces")

    def test_case_insensitive(self):
        assert _check_keyword_match("WATERPROOF NECKLACES for sale", "waterproof necklaces")

    def test_no_match(self):
        assert not _check_keyword_match("Buy earrings today", "waterproof necklaces")

    def test_empty(self):
        assert not _check_keyword_match("", "keyword")
        assert not _check_keyword_match("text", "")


class TestCountLinks:
    def test_markdown_links(self):
        text = "Check [product](/url) and [other](/url2)"
        assert _count_links(text) == 2

    def test_html_links(self):
        text = '<a href="/url">link</a>'
        assert _count_links(text) == 1

    def test_no_links(self):
        assert _count_links("plain text") == 0


class TestAuditCollection:
    def test_good_collection_scores_well(self, good_collection):
        result = audit_collection(good_collection)
        assert result.passing > result.failing

    def test_poor_collection_scores_badly(self, poor_collection):
        result = audit_collection(poor_collection)
        assert result.failing > result.passing

    def test_all_checks_run(self, good_collection):
        result = audit_collection(good_collection)
        assert result.total_checks > 0
        assert result.total_checks == result.passing + result.failing + result.needs_review


class TestPriorityActions:
    def test_returns_failing_checks(self, poor_collection):
        result = audit_collection(poor_collection)
        actions = get_priority_actions(result)
        assert len(actions) > 0
        assert all(a.result == "fail" for a in actions)

    def test_sorted_by_impact(self, poor_collection):
        result = audit_collection(poor_collection)
        actions = get_priority_actions(result)
        if len(actions) >= 2:
            impact_order = {"high": 0, "medium": 1, "low": 2}
            for j in range(len(actions) - 1):
                assert impact_order[actions[j].impact] <= impact_order[actions[j + 1].impact]


class TestCategoryScores:
    def test_returns_categories(self, good_collection):
        result = audit_collection(good_collection)
        categories = get_category_scores(result)
        assert len(categories) > 0
        assert all("passing" in v and "total" in v for v in categories.values())
