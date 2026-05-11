"""Tests for the sitemap ingestion module."""

import gzip
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.sitemap import (
    ParsedSitemap,
    SitemapUrl,
    _classify_url,
    _title_from_handle,
    fetch_sitemap,
    find_related_urls,
    parse_sitemap_file,
)


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def basic_sitemap_bytes() -> bytes:
    return (FIXTURES / "sample_sitemap.xml").read_bytes()


@pytest.fixture
def sitemap_index_bytes() -> bytes:
    return (FIXTURES / "sample_sitemap_index.xml").read_bytes()


@pytest.fixture
def sitemap_products_bytes() -> bytes:
    return (FIXTURES / "sample_sitemap_products.xml").read_bytes()


@pytest.fixture
def sitemap_collections_bytes() -> bytes:
    return (FIXTURES / "sample_sitemap_collections.xml").read_bytes()


class TestClassifyUrl:
    def test_product(self):
        assert _classify_url("https://x.com/products/abc-123")[0] == "product"
        assert _classify_url("https://x.com/products/abc-123")[1] == "abc-123"

    def test_collection(self):
        url_type, handle = _classify_url("https://x.com/collections/tumblers")
        assert url_type == "collection"
        assert handle == "tumblers"

    def test_collection_scoped_product_is_product(self):
        url_type, handle = _classify_url(
            "https://x.com/collections/tumblers/products/quencher"
        )
        assert url_type == "product"
        assert handle == "quencher"

    def test_blog_post(self):
        url_type, handle = _classify_url("https://x.com/blogs/news/why-tumblers-win")
        assert url_type == "blog"
        assert handle == "why-tumblers-win"

    def test_page(self):
        assert _classify_url("https://x.com/pages/about")[0] == "page"

    def test_other(self):
        assert _classify_url("https://x.com/policies/refund")[0] == "other"


class TestTitleFromHandle:
    def test_basic(self):
        assert _title_from_handle("gold-earrings") == "Gold Earrings"

    def test_preserves_digits(self):
        assert _title_from_handle("quencher-40oz-charcoal") == "Quencher 40oz Charcoal"

    def test_underscores(self):
        assert _title_from_handle("travel_mug_12oz") == "Travel Mug 12oz"

    def test_empty(self):
        assert _title_from_handle("") == ""


class TestParseSitemapFile:
    def test_basic_urlset(self, basic_sitemap_bytes):
        result = parse_sitemap_file(basic_sitemap_bytes, source_url="https://x.com/sitemap.xml")
        assert result.error == ""
        assert len(result.products) == 3
        assert len(result.collections) == 2
        assert len(result.blog_posts) == 2
        assert len(result.pages) == 2
        assert len(result.other) == 1
        assert result.total_urls == 10
        # last_modified survives
        assert all(u.last_modified for u in result.products)

    def test_title_guess_populated(self, basic_sitemap_bytes):
        result = parse_sitemap_file(basic_sitemap_bytes)
        titles = [p.title_guess for p in result.products]
        assert "Quencher 40oz Charcoal" in titles

    def test_sitemapindex_without_recursion(self, sitemap_index_bytes):
        # parse_sitemap_file does not recurse — children land in 'other'.
        result = parse_sitemap_file(sitemap_index_bytes)
        assert result.error == ""
        assert result.total_urls == 2

    def test_gzip_decompression(self, basic_sitemap_bytes):
        gz = gzip.compress(basic_sitemap_bytes)
        result = parse_sitemap_file(gz, source_url="https://x.com/sitemap.xml.gz")
        assert result.error == ""
        assert result.total_urls == 10

    def test_malformed_xml_returns_error(self):
        result = parse_sitemap_file(b"<not really xml")
        assert result.error.startswith("Malformed XML")
        assert result.total_urls == 0

    def test_max_urls_cap(self, basic_sitemap_bytes):
        result = parse_sitemap_file(basic_sitemap_bytes, max_urls=3)
        assert result.total_urls == 3
        assert "Truncated" in result.error

    def test_round_trip_dict(self, basic_sitemap_bytes):
        result = parse_sitemap_file(basic_sitemap_bytes)
        restored = ParsedSitemap.from_dict(result.to_dict())
        assert restored.total_urls == result.total_urls
        assert restored.products[0].url == result.products[0].url


class TestFetchSitemap:
    def _mock_session(self, mapping: dict):
        session = MagicMock()

        def _get(url, timeout=15, headers=None):
            if url not in mapping:
                raise requests.RequestException(f"unmapped {url}")
            resp = MagicMock()
            resp.content = mapping[url]
            resp.raise_for_status = MagicMock()
            return resp

        session.get.side_effect = _get
        return session

    def test_fetch_urlset(self, basic_sitemap_bytes):
        session = self._mock_session({"https://x.com/sitemap.xml": basic_sitemap_bytes})
        result = fetch_sitemap("https://x.com/sitemap.xml", _session=session)
        assert result.error == ""
        assert result.total_urls == 10

    def test_fetch_sitemapindex_recurses(
        self, sitemap_index_bytes, sitemap_products_bytes, sitemap_collections_bytes
    ):
        session = self._mock_session(
            {
                "https://example-store.myshopify.com/sitemap.xml": sitemap_index_bytes,
                "https://example-store.myshopify.com/sitemap_products_1.xml": sitemap_products_bytes,
                "https://example-store.myshopify.com/sitemap_collections_1.xml": sitemap_collections_bytes,
            }
        )
        result = fetch_sitemap(
            "https://example-store.myshopify.com/sitemap.xml", _session=session
        )
        assert result.error == ""
        assert len(result.products) == 2
        assert len(result.collections) == 1
        assert len(result.blog_posts) == 1

    def test_network_error_surfaces_via_error_field(self):
        session = MagicMock()
        session.get.side_effect = requests.RequestException("boom")
        result = fetch_sitemap("https://x.com/sitemap.xml", _session=session)
        assert "Fetch failed" in result.error
        assert result.total_urls == 0

    def test_malformed_response(self):
        session = MagicMock()
        resp = MagicMock()
        resp.content = b"<broken"
        resp.raise_for_status = MagicMock()
        session.get.return_value = resp
        result = fetch_sitemap("https://x.com/sitemap.xml", _session=session)
        assert "Malformed XML" in result.error


class TestFindRelatedUrls:
    @pytest.fixture
    def sitemap(self, basic_sitemap_bytes) -> ParsedSitemap:
        return parse_sitemap_file(basic_sitemap_bytes)

    def test_excludes_target_url(self, sitemap):
        target = "https://example-store.myshopify.com/collections/insulated-tumblers"
        result = find_related_urls(
            "insulated tumblers",
            ["tumblers"],
            sitemap,
            target_url=target,
        )
        assert all(c["url"] != target for c in result["collections"])

    def test_respects_caps(self, sitemap):
        result = find_related_urls(
            "quencher",
            ["tumbler", "mug"],
            sitemap,
            max_products=1,
            max_collections=1,
            max_blog_posts=1,
        )
        assert len(result["products"]) <= 1
        assert len(result["collections"]) <= 1
        assert len(result["blog_posts"]) <= 1

    def test_matches_blog_posts_by_keyword(self, sitemap):
        result = find_related_urls(
            "insulated tumblers",
            [],
            sitemap,
            max_blog_posts=2,
        )
        urls = [b["url"] for b in result["blog_posts"]]
        assert any("why-insulated-tumblers-win" in u for u in urls)

    def test_returns_scores(self, sitemap):
        result = find_related_urls("quencher", [], sitemap)
        if result["products"]:
            assert "score" in result["products"][0]
            assert 0 <= result["products"][0]["score"] <= 1

    def test_empty_sitemap_returns_empty(self):
        empty = ParsedSitemap()
        result = find_related_urls("x", ["y"], empty)
        assert result == {"products": [], "collections": [], "blog_posts": []}
