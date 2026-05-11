"""Tests for core.text_utils — the pan-app text helpers."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.text_utils import (
    clean_keyword,
    ensure_v1_path,
    extract_collection_handle,
    extract_collection_name,
)


class TestCleanKeyword:
    def test_strips_zero_width_space(self):
        assert clean_keyword("hello​world") == "helloworld"

    def test_strips_bom(self):
        assert clean_keyword("﻿hello") == "hello"

    def test_strips_soft_hyphen(self):
        assert clean_keyword("hello­world") == "helloworld"

    def test_collapses_multiple_whitespace(self):
        assert clean_keyword("hello    world") == "hello world"
        assert clean_keyword("hello\t\nworld") == "hello world"

    def test_empty_string_returns_empty(self):
        assert clean_keyword("") == ""

    def test_none_returns_empty(self):
        assert clean_keyword(None) == ""

    def test_already_clean_unchanged(self):
        assert clean_keyword("waterproof necklaces") == "waterproof necklaces"

    def test_leading_trailing_whitespace_stripped(self):
        assert clean_keyword("  hello  ") == "hello"


class TestExtractCollectionHandle:
    def test_standard_url(self):
        assert extract_collection_handle("https://x.com/collections/gold-earrings") == "gold-earrings"

    def test_trailing_slash(self):
        assert extract_collection_handle("https://x.com/collections/silver-rings/") == "silver-rings"

    def test_query_params(self):
        assert extract_collection_handle("https://x.com/collections/necklaces?page=2") == "necklaces"

    def test_fragment(self):
        assert extract_collection_handle("https://x.com/collections/bracelets#main") == "bracelets"

    def test_no_scheme(self):
        assert extract_collection_handle("x.com/collections/anklets") == "anklets"

    def test_non_collection_url(self):
        assert extract_collection_handle("https://x.com/products/necklace") == ""

    def test_empty(self):
        assert extract_collection_handle("") == ""

    def test_none_safe(self):
        assert extract_collection_handle(None) == ""


class TestExtractCollectionName:
    def test_basic_url(self):
        assert extract_collection_name("https://x.com/collections/gold-earrings") == "Gold Earrings"

    def test_trailing_slash(self):
        assert extract_collection_name("https://x.com/collections/silver-rings/") == "Silver Rings"

    def test_query_params(self):
        assert extract_collection_name("https://x.com/collections/necklaces?page=2") == "Necklaces"

    def test_underscore_handle(self):
        assert extract_collection_name("https://x.com/collections/gold_chains") == "Gold Chains"

    def test_no_collections_segment_uses_last_path_part(self):
        assert extract_collection_name("https://x.com/category/widgets") == "Widgets"

    def test_empty(self):
        assert extract_collection_name("") == ""


class TestEnsureV1Path:
    def test_bare_domain(self):
        assert ensure_v1_path("https://bifrost.example.com") == "https://bifrost.example.com/v1"

    def test_already_v1(self):
        assert ensure_v1_path("https://bifrost.example.com/v1") == "https://bifrost.example.com/v1"

    def test_v1_with_trailing_slash(self):
        # rstrip("/") removes the trailing slash before checks.
        assert ensure_v1_path("https://bifrost.example.com/v1/") == "https://bifrost.example.com/v1"

    def test_v1_deeper_in_path_does_not_double_append(self):
        assert ensure_v1_path("https://bifrost.example.com/v1/foo") == "https://bifrost.example.com/v1/foo"
        assert ensure_v1_path("https://bifrost.example.com/v1/foo/") == "https://bifrost.example.com/v1/foo"

    def test_domain_with_port(self):
        assert ensure_v1_path("http://localhost:8080") == "http://localhost:8080/v1"

    def test_empty(self):
        assert ensure_v1_path("") == ""
