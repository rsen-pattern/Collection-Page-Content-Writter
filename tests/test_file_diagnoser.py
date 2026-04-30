"""Tests for file_diagnoser module."""

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.file_diagnoser import (
    build_sheet_preview,
    diagnose_file,
    apply_long_mapping,
    apply_wide_mapping,
    reread_with_header,
)


class TestBuildSheetPreview:
    def test_renders_named_columns_as_row_0(self):
        df = pd.DataFrame({"Keyword": ["dog"], "URL": ["https://x.com"]})
        preview = build_sheet_preview(df)
        # Row 0 contains the column names
        assert "Row 0: Keyword | URL" in preview
        # Row 1 contains the first data row
        assert "Row 1: dog | https://x.com" in preview

    def test_unnamed_columns_render_as_blanks_at_row_0(self):
        df = pd.DataFrame({
            "Unnamed: 0": ["", "", "Real Header", "data"],
            "Unnamed: 1": ["", "", "Volume", "100"],
        })
        preview = build_sheet_preview(df)
        # Row 0 should be blank (Unnamed columns)
        assert "Row 0: _ | _" in preview
        # Real header at Row 3 (since file row 0 was blank, row 1 was blank, row 2 was 'Real Header')
        assert "Row 3: Real Header | Volume" in preview

    def test_handles_empty_cells(self):
        df = pd.DataFrame({"a": [None, "x"], "b": ["", "y"]})
        preview = build_sheet_preview(df)
        assert "_" in preview

    def test_caps_at_max_rows(self):
        df = pd.DataFrame({"x": list(range(50))})
        preview = build_sheet_preview(df, max_rows=5)
        # 1 header row + 5 data rows = 6 lines
        assert len(preview.split("\n")) == 6


class TestDiagnoseFile:
    def test_empty_df_returns_low_confidence(self):
        result = diagnose_file("fake-key", pd.DataFrame())
        assert result["confidence"] == "low"
        assert result["mapping"] == {}

    def test_returns_parsed_json_when_ai_responds(self):
        with patch("core.file_diagnoser.OpenAI") as mock_openai:
            instance = mock_openai.return_value
            instance.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=(
                    '{"header_row": 6, "format": "wide", '
                    '"mapping": {"Primary Keyword": "keyword_1", "URL": "url"}, '
                    '"confidence": "high", "reasoning": "found it"}'
                )))]
            )
            df = pd.DataFrame({"Unnamed: 0": ["x"], "Unnamed: 1": ["y"]})
            result = diagnose_file("key", df)
            assert result["header_row"] == 6
            assert result["format"] == "wide"
            assert result["mapping"]["Primary Keyword"] == "keyword_1"
            assert result["confidence"] == "high"

    def test_strips_code_fences(self):
        with patch("core.file_diagnoser.OpenAI") as mock_openai:
            instance = mock_openai.return_value
            instance.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=(
                    '```json\n{"header_row": null, "format": "long", '
                    '"mapping": {}, "confidence": "low", "reasoning": "x"}\n```'
                )))]
            )
            df = pd.DataFrame({"a": [1]})
            result = diagnose_file("key", df)
            assert result["confidence"] == "low"

    def test_drops_unknown_internal_fields_from_mapping(self):
        with patch("core.file_diagnoser.OpenAI") as mock_openai:
            instance = mock_openai.return_value
            instance.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=(
                    '{"header_row": 0, "format": "long", '
                    '"mapping": {"Foo": "keyword", "Bar": "BOGUS_FIELD"}, '
                    '"confidence": "medium", "reasoning": "x"}'
                )))]
            )
            df = pd.DataFrame({"Foo": ["dog"], "Bar": [1]})
            result = diagnose_file("key", df)
            assert result["mapping"] == {"Foo": "keyword"}

    def test_name_field_accepted_in_mapping(self):
        with patch("core.file_diagnoser.OpenAI") as mock_openai:
            instance = mock_openai.return_value
            instance.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=(
                    '{"header_row": 0, "format": "wide", '
                    '"mapping": {"Sub Category": "name", "Primary KW": "keyword_1"}, '
                    '"confidence": "high", "reasoning": "x"}'
                )))]
            )
            df = pd.DataFrame({"Sub Category": ["Shirts"], "Primary KW": ["shirt"]})
            result = diagnose_file("key", df)
            assert result["mapping"]["Sub Category"] == "name"

    def test_invalid_json_returns_error(self):
        with patch("core.file_diagnoser.OpenAI") as mock_openai:
            instance = mock_openai.return_value
            instance.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="not json at all"))]
            )
            df = pd.DataFrame({"a": [1]})
            result = diagnose_file("key", df)
            assert "error" in result
            assert result["error"]
            assert result["mapping"] == {}

    def test_api_exception_returns_error(self):
        with patch("core.file_diagnoser.OpenAI") as mock_openai:
            instance = mock_openai.return_value
            instance.chat.completions.create.side_effect = Exception("rate limit")
            df = pd.DataFrame({"a": [1]})
            result = diagnose_file("key", df)
            assert "rate limit" in result["error"]

    def test_appends_v1_to_base_url(self):
        with patch("core.file_diagnoser.OpenAI") as mock_openai:
            instance = mock_openai.return_value
            instance.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content=(
                    '{"header_row": null, "format": "long", "mapping": {}, '
                    '"confidence": "low", "reasoning": "x"}'
                )))]
            )
            df = pd.DataFrame({"a": [1]})
            diagnose_file("key", df, base_url="https://bifrost.pattern.com")
            call_kwargs = mock_openai.call_args[1]
            assert call_kwargs["base_url"].endswith("/v1")


class TestApplyLongMapping:
    def test_maps_keyword_url_volume(self):
        df = pd.DataFrame({
            "kw": ["dog food", "cat food"],
            "u": ["https://x.com/collections/dog", "https://x.com/collections/cat"],
            "vol": ["100", "200"],
        })
        result = apply_long_mapping(df, {"kw": "keyword", "u": "url", "vol": "volume"})
        assert result["keyword"].tolist() == ["dog food", "cat food"]
        assert result["collection_url"].iloc[0].startswith("https://")
        assert result["search_volume"].iloc[0] == 100

    def test_skips_missing_columns(self):
        df = pd.DataFrame({"a": [1]})
        result = apply_long_mapping(df, {"missing_col": "keyword"})
        assert result.empty

    def test_difficulty_strips_percent_sign(self):
        df = pd.DataFrame({"d": ["25%", "50%"]})
        result = apply_long_mapping(df, {"d": "difficulty"})
        assert result["keyword_difficulty"].tolist() == [25.0, 50.0]


class TestApplyWideMapping:
    def test_builds_collection_groups_from_wide_format(self):
        df = pd.DataFrame({
            "URL": ["https://x.com/collections/oversized", "https://x.com/collections/flannel"],
            "Primary Keyword": ["oversized shirt", "flannel shirt"],
            "Primary KW SV": [2400, 5400],
            "Secondary Keyword": ["oversized shirts", "flannel shirts"],
            "Secondary KW SV": [1000, 1600],
        })
        mapping = {
            "URL": "url",
            "Primary Keyword": "keyword_1",
            "Primary KW SV": "volume_1",
            "Secondary Keyword": "keyword_2",
            "Secondary KW SV": "volume_2",
        }
        groups, skipped, info = apply_wide_mapping(df, mapping)
        assert len(groups) == 2
        assert groups[0].primary_keyword == "flannel shirt"  # sorted by total vol desc
        assert groups[0].total_volume == 7000  # 5400 + 1600
        assert len(skipped) == 0
        assert info["real_urls"] == 2
        assert info["placeholder_urls"] == 0

    def test_skips_rows_with_no_keywords(self):
        df = pd.DataFrame({
            "URL": ["https://x.com/collections/a", "https://x.com/collections/b"],
            "kw1": ["dog", None],
            "vol1": [100, 0],
        })
        mapping = {"URL": "url", "kw1": "keyword_1", "vol1": "volume_1"}
        groups, skipped, info = apply_wide_mapping(df, mapping)
        assert len(groups) == 1
        assert len(skipped) == 1
        assert skipped[0].reason == "no_keywords"

    def test_flags_zero_volume_rows(self):
        df = pd.DataFrame({"URL": ["https://x.com/collections/a"], "kw1": ["dog"], "vol1": [0]})
        mapping = {"URL": "url", "kw1": "keyword_1", "vol1": "volume_1"}
        groups, skipped, info = apply_wide_mapping(df, mapping)
        assert len(groups) == 1
        assert len(skipped) == 1
        assert skipped[0].reason == "zero_volume"

    def test_empty_url_falls_back_to_name_column(self):
        df = pd.DataFrame({
            "URL": [None, None],
            "Sub Category": ["Oversized Shirts", "Flannel Shirts"],
            "Primary Keyword": ["oversized shirt", "flannel shirt"],
            "Primary KW SV": [100, 200],
        })
        mapping = {
            "URL": "url",
            "Sub Category": "name",
            "Primary Keyword": "keyword_1",
            "Primary KW SV": "volume_1",
        }
        groups, skipped, info = apply_wide_mapping(df, mapping)
        assert len(groups) == 2
        assert info["placeholder_urls"] == 2
        assert info["real_urls"] == 0
        urls = [g.collection_url for g in groups]
        assert "/collections/flannel-shirts" in urls
        assert "/collections/oversized-shirts" in urls
        # Friendly collection names should come from the name column
        names = [g.collection_name for g in groups]
        assert "Flannel Shirts" in names

    def test_no_url_no_name_falls_back_to_keyword(self):
        df = pd.DataFrame({
            "Primary Keyword": ["oversized shirt"],
            "Primary KW SV": [100],
        })
        mapping = {"Primary Keyword": "keyword_1", "Primary KW SV": "volume_1"}
        groups, skipped, info = apply_wide_mapping(df, mapping)
        assert len(groups) == 1
        assert info["placeholder_urls"] == 1
        assert groups[0].collection_url == "/collections/oversized-shirt"

    def test_mixed_real_and_placeholder_urls(self):
        df = pd.DataFrame({
            "URL": ["https://x.com/collections/real", None],
            "Sub Category": ["Real Cat", "Placeholder Cat"],
            "Primary Keyword": ["real kw", "placeholder kw"],
            "Primary KW SV": [100, 200],
        })
        mapping = {
            "URL": "url",
            "Sub Category": "name",
            "Primary Keyword": "keyword_1",
            "Primary KW SV": "volume_1",
        }
        groups, skipped, info = apply_wide_mapping(df, mapping)
        assert len(groups) == 2
        assert info["real_urls"] == 1
        assert info["placeholder_urls"] == 1

    def test_returns_empty_when_no_keywords_mapped(self):
        df = pd.DataFrame({"URL": ["x"]})
        mapping = {"URL": "url"}  # no keyword mapping
        groups, skipped, info = apply_wide_mapping(df, mapping)
        assert groups == []


class TestRereadWithHeader:
    def test_none_header_uses_default(self):
        buf = io.BytesIO(b"col1,col2\nval1,val2\n")
        buf.name = "x.csv"
        df = reread_with_header(buf, None)
        assert df.columns.tolist() == ["col1", "col2"]
        assert df.iloc[0].tolist() == ["val1", "val2"]

    def test_header_row_skips_lines(self):
        # First row is junk, headers on row 1
        buf = io.BytesIO(b"junk1,junk2\ncol1,col2\nval1,val2\n")
        buf.name = "x.csv"
        df = reread_with_header(buf, 1)
        assert df.columns.tolist() == ["col1", "col2"]
        assert df.iloc[0].tolist() == ["val1", "val2"]
