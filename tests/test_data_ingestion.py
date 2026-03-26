"""Tests for data ingestion module."""

import io
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.data_ingestion import (
    detect_format,
    normalize_dataframe,
    group_by_collection,
    _extract_collection_name,
)


@pytest.fixture
def gsc_df():
    return pd.read_csv(Path(__file__).parent / "fixtures" / "sample_gsc_export.csv")


@pytest.fixture
def ahrefs_df():
    return pd.read_csv(Path(__file__).parent / "fixtures" / "sample_ahrefs_export.csv")


class TestDetectFormat:
    def test_detects_gsc(self, gsc_df):
        assert detect_format(gsc_df) == "gsc"

    def test_detects_ahrefs(self, ahrefs_df):
        assert detect_format(ahrefs_df) == "ahrefs"

    def test_detects_custom_for_unknown(self):
        df = pd.DataFrame({"foo": [1], "bar": [2]})
        assert detect_format(df) == "custom"


class TestNormalize:
    def test_gsc_normalization(self, gsc_df):
        normalized = normalize_dataframe(gsc_df, "gsc")
        assert "keyword" in normalized.columns
        assert "collection_url" in normalized.columns
        assert "clicks" in normalized.columns
        assert len(normalized) > 0

    def test_ahrefs_normalization(self, ahrefs_df):
        normalized = normalize_dataframe(ahrefs_df, "ahrefs")
        assert "keyword" in normalized.columns
        assert "collection_url" in normalized.columns
        assert "search_volume" in normalized.columns

    def test_filters_to_collections(self, gsc_df):
        normalized = normalize_dataframe(gsc_df, "gsc")
        assert all("/collections/" in url for url in normalized["collection_url"])


class TestGroupByCollection:
    def test_groups_correctly(self, gsc_df):
        normalized = normalize_dataframe(gsc_df, "gsc")
        groups = group_by_collection(normalized)
        assert len(groups) == 4  # 4 collections in sample data

    def test_primary_keyword_is_highest_volume(self, ahrefs_df):
        normalized = normalize_dataframe(ahrefs_df, "ahrefs")
        groups = group_by_collection(normalized)
        for group in groups:
            if group.secondary_keywords:
                for sec in group.secondary_keywords:
                    if "search_volume" in sec and group.primary_keyword_volume:
                        assert sec["search_volume"] <= group.primary_keyword_volume

    def test_total_volume_calculated(self, gsc_df):
        normalized = normalize_dataframe(gsc_df, "gsc")
        groups = group_by_collection(normalized)
        for group in groups:
            assert group.total_volume >= 0


class TestExtractCollectionName:
    def test_basic_url(self):
        name = _extract_collection_name("https://example.com/collections/gold-earrings")
        assert name == "Gold Earrings"

    def test_url_with_trailing_slash(self):
        name = _extract_collection_name("https://example.com/collections/silver-rings/")
        assert name == "Silver Rings"

    def test_url_with_params(self):
        name = _extract_collection_name("https://example.com/collections/necklaces?page=2")
        assert name == "Necklaces"
