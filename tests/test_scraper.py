"""Tests for Shopify collection product scraper."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.scraper import (
    CollectionPageData,
    ScrapedProduct,
    fetch_collection_data,
    _shopify_extract_handle,
    _shopify_origin,
)


class TestHelpers:
    def test_extract_handle(self):
        assert _shopify_extract_handle("https://x.com/collections/quencher") == "quencher"
        assert _shopify_extract_handle("https://x.com/collections/quencher?foo=bar") == "quencher"
        assert _shopify_extract_handle("https://x.com/about") == ""

    def test_origin(self):
        assert _shopify_origin("https://stanley.com.au/collections/quencher") == "https://stanley.com.au"

    def test_origin_empty_for_relative(self):
        assert _shopify_origin("/collections/foo") == ""


class TestFetchCollectionData:
    def test_rejects_non_collection_url(self):
        result = fetch_collection_data("https://x.com/products/foo")
        assert result.source == "failed"

    def test_rejects_empty_url(self):
        result = fetch_collection_data("")
        assert result.source == "failed"

    def test_json_path_extracts_products(self):
        page_html = (
            "<html><head>"
            "<title>Quencher Tumblers | Stanley</title>"
            "<meta name='description' content='Shop quencher tumblers'>"
            "</head><body><h1>Quencher Tumblers</h1></body></html>"
        )
        products_json = {
            "products": [
                {
                    "title": "Quencher 40oz",
                    "handle": "quencher-40oz",
                    "variants": [{"price": "49.95"}],
                    "images": [{"src": "https://cdn.shopify.com/img.jpg", "alt": "Charcoal Quencher 40oz"}],
                    "product_type": "Tumbler",
                    "vendor": "Stanley",
                },
            ]
        }

        def side_effect(url, accept_json=False):
            mock = MagicMock()
            mock.status_code = 200
            if "products.json" in url:
                mock.json.return_value = products_json
                return mock
            if url.endswith(".json"):
                mock.json.return_value = {"collection": {}}
                return mock
            mock.text = page_html
            return mock

        with patch("core.scraper._shopify_get", side_effect=side_effect):
            result = fetch_collection_data("https://stanley.com.au/collections/quencher")

        assert result.source in ("json", "mixed")
        assert len(result.products) == 1
        assert result.products[0].name == "Quencher 40oz"
        assert result.products[0].url == "https://stanley.com.au/products/quencher-40oz"
        assert result.products[0].image_alt == "Charcoal Quencher 40oz"
        assert result.h1 == "Quencher Tumblers"
        assert result.meta_title == "Quencher Tumblers | Stanley"
        assert result.meta_description == "Shop quencher tumblers"

    def test_html_fallback_when_json_returns_none(self):
        page_html = """
        <html><body>
          <h1>Quencher Tumblers</h1>
          <div class="product-card">
            <a href="/products/quencher-40oz">
              <h2 class="product-card__title">Quencher 40oz</h2>
              <img src="/img/q.jpg" alt="Quencher" />
            </a>
          </div>
        </body></html>
        """

        def side_effect(url, accept_json=False):
            if "products.json" in url or url.endswith(".json"):
                return None
            m = MagicMock()
            m.status_code = 200
            m.text = page_html
            return m

        with patch("core.scraper._shopify_get", side_effect=side_effect):
            result = fetch_collection_data("https://x.com/collections/quencher")

        assert result.source == "html"
        assert len(result.products) == 1
        assert result.products[0].name == "Quencher 40oz"

    def test_failed_when_nothing_loads(self):
        with patch("core.scraper._shopify_get", return_value=None):
            result = fetch_collection_data("https://x.com/collections/y")
        assert result.source == "failed"

    def test_partial_result_when_page_loads_but_no_products(self):
        page_html = "<html><body><h1>Quencher</h1></body></html>"

        def side_effect(url, accept_json=False):
            if "products.json" in url:
                return None
            if url.endswith(".json"):
                return None
            m = MagicMock()
            m.status_code = 200
            m.text = page_html
            return m

        with patch("core.scraper._shopify_get", side_effect=side_effect):
            result = fetch_collection_data("https://x.com/collections/quencher")

        assert result.source == "html"
        assert result.h1 == "Quencher"
        assert len(result.products) == 0
