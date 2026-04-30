"""Tests for JSON-LD schema generators."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.schema import (
    build_faq_schema,
    build_itemlist_schema,
    schema_to_script_tag,
)


class TestFaqSchema:
    def test_builds_faqpage_with_questions(self):
        faqs = [
            {"question": "How long does it last?", "answer": "11 hours."},
            {"question": "Is it dishwasher safe?", "answer": "Hand-wash only."},
        ]
        schema = build_faq_schema(faqs)
        assert schema["@type"] == "FAQPage"
        assert schema["@context"] == "https://schema.org"
        assert len(schema["mainEntity"]) == 2
        assert schema["mainEntity"][0]["name"] == "How long does it last?"
        assert schema["mainEntity"][0]["acceptedAnswer"]["text"] == "11 hours."

    def test_empty_faqs_returns_none(self):
        assert build_faq_schema([]) is None

    def test_skips_blank_question(self):
        faqs = [
            {"question": "Real?", "answer": "Yes."},
            {"question": "", "answer": "Skip me."},
            {"question": "No answer?", "answer": ""},
        ]
        schema = build_faq_schema(faqs)
        assert schema is not None
        assert len(schema["mainEntity"]) == 1

    def test_all_blank_returns_none(self):
        faqs = [{"question": "", "answer": ""}, {"question": "  ", "answer": "  "}]
        assert build_faq_schema(faqs) is None


class TestItemListSchema:
    def test_builds_itemlist_with_products(self):
        products = [
            {"name": "Quencher 40oz", "url": "/products/quencher-40oz"},
            {"name": "Quencher 30oz", "url": "/products/quencher-30oz"},
        ]
        schema = build_itemlist_schema(
            products, "https://stanley.com.au/collections/quencher", "Quencher Tumblers"
        )
        assert schema["@type"] == "ItemList"
        assert schema["name"] == "Quencher Tumblers"
        assert len(schema["itemListElement"]) == 2
        first = schema["itemListElement"][0]
        assert first["position"] == 1
        assert first["item"]["url"] == "https://stanley.com.au/products/quencher-40oz"

    def test_resolves_relative_urls(self):
        products = [{"name": "P", "url": "/products/p"}]
        schema = build_itemlist_schema(products, "https://example.com/collections/c")
        assert schema["itemListElement"][0]["item"]["url"] == "https://example.com/products/p"

    def test_includes_offers_when_price_and_currency_set(self):
        products = [{
            "name": "Quencher 40oz",
            "url": "/products/quencher-40oz",
            "price": "49.95",
            "currency": "AUD",
        }]
        schema = build_itemlist_schema(products, "https://stanley.com.au/")
        offers = schema["itemListElement"][0]["item"]["offers"]
        assert offers["price"] == "49.95"
        assert offers["priceCurrency"] == "AUD"

    def test_empty_products_returns_none(self):
        assert build_itemlist_schema([], "https://x.com/") is None

    def test_skips_products_missing_name_or_url(self):
        products = [
            {"name": "P1", "url": "/products/p1"},
            {"name": "", "url": "/products/p2"},
            {"name": "P3", "url": ""},
        ]
        schema = build_itemlist_schema(products, "https://x.com/")
        assert len(schema["itemListElement"]) == 1

    def test_no_collection_name_omits_name_key(self):
        products = [{"name": "P", "url": "/products/p"}]
        schema = build_itemlist_schema(products, "https://x.com/")
        assert "name" not in schema


class TestScriptTag:
    def test_wraps_in_script_tag(self):
        schema = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": []}
        out = schema_to_script_tag(schema)
        assert out.startswith('<script type="application/ld+json">')
        assert out.endswith("</script>")

    def test_json_inside_is_parseable(self):
        schema = build_faq_schema([{"question": "Q?", "answer": "A."}])
        out = schema_to_script_tag(schema)
        inner = out.split(">", 1)[1].rsplit("<", 1)[0]
        parsed = json.loads(inner.replace("<\\/", "</"))
        assert parsed["@type"] == "FAQPage"

    def test_none_returns_empty_string(self):
        assert schema_to_script_tag(None) == ""

    def test_escapes_close_script_in_content(self):
        schema = build_faq_schema([
            {"question": "Hi?", "answer": "Hello </script><script>alert(1)</script>"}
        ])
        out = schema_to_script_tag(schema)
        answer_portion = out.split('"text":')[1]
        assert "</script><script>" not in answer_portion
        assert "<\\/script>" in out
