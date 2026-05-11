"""Tests for core.site_keywords — format detection, parsing, cannibalisation."""

import io
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.site_keywords import (
    SiteKeywordCorpus,
    SiteKeywordRow,
    conflicts_for_url,
    detect_site_format,
    find_all_cannibalisation,
    find_primary_keyword_conflicts,
    find_top_10_conflicts,
    parse_site_keywords,
    suggest_keywords_for_collection,
)


# ─────────────────────────────────────────────────────────────────────────
# Format detection
# ─────────────────────────────────────────────────────────────────────────


def _df(columns: list[str], rows: list[list]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=columns)


class TestDetectSiteFormat:
    def test_ahrefs_by_current_url_and_current_position(self):
        df = _df(["Keyword", "Current URL", "Current position", "Volume"], [])
        assert detect_site_format(df) == "ahrefs"

    def test_brightedge_by_landing_page(self):
        df = _df(["Keyword", "Landing Page", "Rank", "Search Volume"], [])
        assert detect_site_format(df) == "brightedge"

    def test_brightedge_by_average_rank(self):
        df = _df(["Search Term", "URL", "Average Rank", "Monthly Searches"], [])
        assert detect_site_format(df) == "brightedge"

    def test_semrush_by_url_position_volume(self):
        df = _df(["Keyword", "Search Volume", "Position", "URL"], [])
        assert detect_site_format(df) == "semrush"

    def test_unknown_falls_back_to_ahrefs_when_kw_volume_present(self):
        # Looser fallback — keyword + volume present, anything else missing.
        df = _df(["Keyword", "Volume"], [])
        assert detect_site_format(df) == "ahrefs"

    def test_unrecognisable_returns_custom(self):
        df = _df(["something", "else", "entirely"], [])
        assert detect_site_format(df) == "custom"


# ─────────────────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────────────────


class TestParseSiteKeywords:
    def test_ahrefs_round_trip(self):
        df = _df(
            ["Keyword", "Current URL", "Current position", "Volume", "Traffic"],
            [
                ["waterproof necklaces", "https://x.com/collections/necklaces", 4, 2900, 120],
                ["gold necklaces", "https://x.com/collections/necklaces", 7, 1800, 60],
            ],
        )
        corpus = parse_site_keywords(df)
        assert corpus.source_format == "ahrefs"
        assert corpus.error == ""
        assert corpus.total_rows == 2
        assert corpus.rows[0].keyword == "waterproof necklaces"
        assert corpus.rows[0].position == 4
        assert corpus.rows[0].search_volume == 2900
        assert corpus.rows[0].traffic == 120

    def test_semrush_round_trip(self):
        df = _df(
            ["Keyword", "Search Volume", "Position", "URL", "Traffic"],
            [["gold earrings", 5400, 9, "https://x.com/collections/gold-earrings", 250]],
        )
        corpus = parse_site_keywords(df)
        assert corpus.source_format == "semrush"
        assert corpus.total_rows == 1
        assert corpus.rows[0].url == "https://x.com/collections/gold-earrings"

    def test_brightedge_round_trip(self):
        df = _df(
            ["Keyword", "Landing Page", "Rank", "Search Volume"],
            [["silver rings", "https://x.com/collections/silver", 12, 1200]],
        )
        corpus = parse_site_keywords(df)
        assert corpus.source_format == "brightedge"
        assert corpus.total_rows == 1
        assert corpus.rows[0].position == 12

    def test_missing_keyword_column_returns_error(self):
        df = _df(["Position", "URL", "Volume"], [[1, "https://x.com", 100]])
        corpus = parse_site_keywords(df)
        assert corpus.error != ""
        assert corpus.total_rows == 0

    def test_empty_rows_silently_dropped(self):
        df = _df(
            ["Keyword", "Current URL", "Current position", "Volume"],
            [
                ["valid", "https://x.com/y", 5, 100],
                [None, "https://x.com/z", 6, 50],
                ["", "https://x.com/w", 7, 50],
                ["lonely", None, 8, 50],
            ],
        )
        corpus = parse_site_keywords(df)
        assert corpus.total_rows == 1

    def test_dict_round_trip(self):
        corpus = SiteKeywordCorpus(
            source_format="ahrefs",
            rows=[SiteKeywordRow(keyword="x", url="u", search_volume=100, position=3.0)],
            uploaded_at="2026-05-11T00:00:00Z",
        )
        restored = SiteKeywordCorpus.from_dict(corpus.to_dict())
        assert restored.total_rows == 1
        assert restored.rows[0].keyword == "x"
        assert restored.rows[0].position == 3.0


# ─────────────────────────────────────────────────────────────────────────
# Cannibalisation — primary overlap
# ─────────────────────────────────────────────────────────────────────────


class TestFindPrimaryKeywordConflicts:
    def _group(self, url: str, primary: str, name: str = ""):
        return {
            "collection_url": url,
            "collection_name": name or url.rsplit("/", 1)[-1].title(),
            "primary_keyword": primary,
        }

    def test_no_conflicts_when_primaries_unique(self):
        groups = [
            self._group("https://x.com/a", "alpha"),
            self._group("https://x.com/b", "beta"),
        ]
        assert find_primary_keyword_conflicts(groups) == []

    def test_two_collections_share_primary_flagged(self):
        groups = [
            self._group("https://x.com/a", "shared kw"),
            self._group("https://x.com/b", "shared kw"),
        ]
        conflicts = find_primary_keyword_conflicts(groups)
        assert len(conflicts) == 1
        assert conflicts[0].kind == "primary_overlap"
        assert {u["url"] for u in conflicts[0].urls} == {"https://x.com/a", "https://x.com/b"}

    def test_case_insensitive_match(self):
        groups = [
            self._group("https://x.com/a", "SHIRTS"),
            self._group("https://x.com/b", "shirts"),
        ]
        conflicts = find_primary_keyword_conflicts(groups)
        assert len(conflicts) == 1


# ─────────────────────────────────────────────────────────────────────────
# Cannibalisation — top-10 overlap
# ─────────────────────────────────────────────────────────────────────────


class TestFindTop10Conflicts:
    def test_two_urls_top10_for_same_keyword(self):
        corpus = SiteKeywordCorpus(rows=[
            SiteKeywordRow(keyword="shirts", url="https://x.com/a", search_volume=1000, position=3),
            SiteKeywordRow(keyword="shirts", url="https://x.com/b", search_volume=1000, position=9),
        ])
        conflicts = find_top_10_conflicts(corpus)
        assert len(conflicts) == 1
        assert conflicts[0].keyword == "shirts"
        assert len(conflicts[0].urls) == 2
        # URLs sorted by best position first.
        assert conflicts[0].urls[0]["position"] == 3

    def test_only_one_url_no_conflict(self):
        corpus = SiteKeywordCorpus(rows=[
            SiteKeywordRow(keyword="shirts", url="https://x.com/a", position=3),
        ])
        assert find_top_10_conflicts(corpus) == []

    def test_outside_range_ignored(self):
        corpus = SiteKeywordCorpus(rows=[
            SiteKeywordRow(keyword="shirts", url="https://x.com/a", position=15),
            SiteKeywordRow(keyword="shirts", url="https://x.com/b", position=22),
        ])
        assert find_top_10_conflicts(corpus) == []

    def test_custom_range_5_to_10(self):
        """User spec mentioned 5–10 band as a stricter check."""
        corpus = SiteKeywordCorpus(rows=[
            SiteKeywordRow(keyword="shirts", url="https://x.com/a", position=3),
            SiteKeywordRow(keyword="shirts", url="https://x.com/b", position=8),
        ])
        # In 5–10 only b qualifies; only one URL → no conflict.
        assert find_top_10_conflicts(corpus, min_position=5, max_position=10) == []

    def test_same_url_multiple_rows_not_a_conflict(self):
        corpus = SiteKeywordCorpus(rows=[
            SiteKeywordRow(keyword="shirts", url="https://x.com/a", position=3),
            SiteKeywordRow(keyword="shirts", url="https://x.com/a", position=4),
        ])
        assert find_top_10_conflicts(corpus) == []


# ─────────────────────────────────────────────────────────────────────────
# Combined detection + helpers
# ─────────────────────────────────────────────────────────────────────────


class TestFindAllCannibalisation:
    def test_keyword_in_both_buckets_marked_primary_and_top10(self):
        groups = [
            {"collection_url": "https://x.com/a", "primary_keyword": "shirts", "collection_name": "A"},
            {"collection_url": "https://x.com/b", "primary_keyword": "shirts", "collection_name": "B"},
        ]
        corpus = SiteKeywordCorpus(rows=[
            SiteKeywordRow(keyword="shirts", url="https://x.com/a", position=3, search_volume=5000),
            SiteKeywordRow(keyword="shirts", url="https://x.com/c", position=8, search_volume=5000),
        ])
        conflicts = find_all_cannibalisation(groups, corpus)
        assert len(conflicts) == 1
        c = conflicts[0]
        assert c.kind == "primary_and_top10"
        # Both URL sources merged; deduplicated.
        urls = {u["url"] for u in c.urls}
        assert urls == {"https://x.com/a", "https://x.com/b", "https://x.com/c"}

    def test_sorted_by_volume_desc(self):
        corpus = SiteKeywordCorpus(rows=[
            SiteKeywordRow(keyword="low", url="https://x.com/a", position=3, search_volume=100),
            SiteKeywordRow(keyword="low", url="https://x.com/b", position=4, search_volume=100),
            SiteKeywordRow(keyword="high", url="https://x.com/a", position=3, search_volume=5000),
            SiteKeywordRow(keyword="high", url="https://x.com/b", position=4, search_volume=5000),
        ])
        conflicts = find_all_cannibalisation([], corpus)
        assert conflicts[0].keyword == "high"
        assert conflicts[1].keyword == "low"


class TestConflictsForUrl:
    def test_filters_to_url(self):
        corpus = SiteKeywordCorpus(rows=[
            SiteKeywordRow(keyword="x", url="https://x.com/a", position=3),
            SiteKeywordRow(keyword="x", url="https://x.com/b", position=4),
            SiteKeywordRow(keyword="y", url="https://x.com/c", position=3),
            SiteKeywordRow(keyword="y", url="https://x.com/d", position=4),
        ])
        all_conflicts = find_top_10_conflicts(corpus)
        a_conflicts = conflicts_for_url(all_conflicts, "https://x.com/a")
        assert len(a_conflicts) == 1
        assert a_conflicts[0].keyword == "x"


# ─────────────────────────────────────────────────────────────────────────
# Suggestions
# ─────────────────────────────────────────────────────────────────────────


class TestSuggestKeywordsForCollection:
    def test_returns_matches_for_same_url(self):
        corpus = SiteKeywordCorpus(rows=[
            SiteKeywordRow(keyword="big shirts", url="https://x.com/collections/shirts", search_volume=500),
            SiteKeywordRow(keyword="red shirts", url="https://x.com/collections/shirts", search_volume=300),
            SiteKeywordRow(keyword="dresses", url="https://x.com/collections/dresses", search_volume=400),
        ])
        suggestions = suggest_keywords_for_collection(
            "https://x.com/collections/shirts", corpus
        )
        kw = [s.keyword for s in suggestions]
        assert "big shirts" in kw
        assert "red shirts" in kw
        assert "dresses" not in kw

    def test_excludes_existing_keywords(self):
        corpus = SiteKeywordCorpus(rows=[
            SiteKeywordRow(keyword="big shirts", url="https://x.com/collections/shirts", search_volume=500),
            SiteKeywordRow(keyword="red shirts", url="https://x.com/collections/shirts", search_volume=300),
        ])
        suggestions = suggest_keywords_for_collection(
            "https://x.com/collections/shirts",
            corpus,
            existing_keywords=["Big Shirts"],
        )
        kw = [s.keyword for s in suggestions]
        assert "big shirts" not in kw

    def test_sorted_by_volume_desc_and_capped(self):
        corpus = SiteKeywordCorpus(rows=[
            SiteKeywordRow(keyword=f"kw{i}", url="https://x.com/collections/shirts", search_volume=100 + i)
            for i in range(20)
        ])
        suggestions = suggest_keywords_for_collection(
            "https://x.com/collections/shirts", corpus, max_suggestions=5
        )
        assert len(suggestions) == 5
        # Highest volume first.
        assert suggestions[0].search_volume > suggestions[-1].search_volume

    def test_below_min_volume_filtered(self):
        corpus = SiteKeywordCorpus(rows=[
            SiteKeywordRow(keyword="tiny", url="https://x.com/collections/shirts", search_volume=5),
            SiteKeywordRow(keyword="big", url="https://x.com/collections/shirts", search_volume=500),
        ])
        suggestions = suggest_keywords_for_collection(
            "https://x.com/collections/shirts", corpus, min_volume=20
        )
        kw = [s.keyword for s in suggestions]
        assert "tiny" not in kw
        assert "big" in kw

    def test_matches_by_handle_when_url_differs(self):
        """A row with the same /collections/<handle> but a different host or
        scheme still counts as a match."""
        corpus = SiteKeywordCorpus(rows=[
            SiteKeywordRow(keyword="x", url="http://OTHER.com/collections/shirts/", search_volume=100),
        ])
        suggestions = suggest_keywords_for_collection(
            "https://x.com/collections/shirts", corpus
        )
        assert len(suggestions) == 1
