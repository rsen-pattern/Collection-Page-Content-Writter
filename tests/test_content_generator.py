"""Tests for content generator module (prompt building and response parsing)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.brief_builder import ContentBrief
from core.content_generator import (
    GeneratedContent,
    build_system_prompt,
    build_full_brief_prompt,
    build_description_prompt,
    build_bottom_copy_prompt,
    build_alt_text_prompt,
    build_title_prompt,
    build_faq_prompt,
    parse_full_brief_response,
    parse_title_response,
    parse_faqs,
)


@pytest.fixture
def sample_brief():
    return ContentBrief(
        collection_url="https://example.com/collections/waterproof-necklaces",
        collection_name="Waterproof Necklaces",
        primary_keyword="waterproof necklaces",
        primary_keyword_volume=2900,
        secondary_keywords=["gold waterproof necklaces", "silver waterproof necklaces"],
        brand_usps=[
            "Handcrafted in London",
            "100% waterproof",
            "Lifetime warranty",
        ],
        products_to_link=[
            {"name": "Gold Chain", "url": "/products/gold-chain"},
            {"name": "Silver Pendant", "url": "/products/silver-pendant"},
        ],
        related_collections=[
            {"name": "Earrings", "url": "/collections/earrings"},
        ],
        target_word_count=100,
        paa_questions=["Can you shower with waterproof necklaces?"],
        faq_count=3,
        brand_name="Lunar Jewelry",
        store_url="https://lunarjewelry.co.uk",
        target_market="UK",
    )


class TestBuildPrompts:
    def test_system_prompt_includes_brand(self, sample_brief):
        prompt = build_system_prompt(sample_brief)
        assert "Lunar Jewelry" in prompt
        assert "waterproof" in prompt.lower()

    def test_full_brief_prompt_includes_context(self, sample_brief):
        prompt = build_full_brief_prompt(sample_brief)
        assert "Waterproof Necklaces" in prompt
        assert "waterproof necklaces" in prompt
        assert "Gold Chain" in prompt

    def test_description_prompt(self, sample_brief):
        prompt = build_description_prompt(sample_brief)
        assert "waterproof necklaces" in prompt
        assert "100" in prompt  # target word count

    def test_title_prompt(self, sample_brief):
        prompt = build_title_prompt(sample_brief)
        assert "waterproof necklaces" in prompt
        assert "Lunar Jewelry" in prompt

    def test_faq_prompt(self, sample_brief):
        prompt = build_faq_prompt(sample_brief)
        assert "shower" in prompt.lower()
        assert "3" in prompt

    def test_batch_exclusion_in_faq(self, sample_brief):
        prompt = build_faq_prompt(sample_brief, batch_faq_topics=["How to care for necklaces?"])
        assert "How to care for necklaces?" in prompt


class TestParseResponses:
    def test_parse_full_brief(self):
        response = """---SEO TITLE---
Waterproof Necklaces | Gold & Silver | For Sale at Lunar Jewelry

---COLLECTION TITLE---
Waterproof Necklaces

---DESCRIPTION---
Discover our stunning waterproof necklaces, handcrafted in London.

---META DESCRIPTION---
Shop waterproof necklaces at Lunar Jewelry. Free UK delivery.

---FAQ---
Q: Can you shower with waterproof necklaces?
A: Yes, all our necklaces are 100% waterproof.

Q: Do waterproof necklaces tarnish?
A: No, our pieces are made with recycled metals that resist tarnishing.
"""
        result = parse_full_brief_response(response)
        assert "Waterproof Necklaces" in result["seo_title"]
        assert result["collection_title"] == "Waterproof Necklaces"
        assert "handcrafted" in result["description"]
        assert len(result["meta_description"]) > 0
        assert len(result["faqs"]) == 2

    def test_parse_title_response(self):
        response = """SEO Title: Waterproof Necklaces | Gold & Silver | For Sale at Lunar
Collection Title: Waterproof Necklaces"""
        result = parse_title_response(response)
        assert "Waterproof" in result["seo_title"]
        assert result["collection_title"] == "Waterproof Necklaces"

    def test_parse_faqs(self):
        text = """Q: Can you shower with them?
A: Yes, they are fully waterproof.

Q: Are they hypoallergenic?
A: Yes, all our pieces are nickel-free and hypoallergenic."""
        faqs = parse_faqs(text)
        assert len(faqs) == 2
        assert "shower" in faqs[0]["question"]
        assert "waterproof" in faqs[0]["answer"]

    def test_parse_empty_faqs(self):
        assert parse_faqs("") == []


class TestNewGenerators:
    def test_generated_content_has_alt_text_field(self):
        content = GeneratedContent(
            collection_url="https://x.com/collections/y", collection_name="Y"
        )
        assert hasattr(content, "alt_text")
        assert content.alt_text == ""

    def test_build_bottom_copy_prompt_includes_target(self, sample_brief):
        sample_brief.target_bottom_word_count = 800
        prompt = build_bottom_copy_prompt(sample_brief)
        assert "800" in prompt
        assert "words" in prompt.lower()

    def test_build_bottom_copy_prompt_heading_rule_present(self, sample_brief):
        prompt = build_bottom_copy_prompt(sample_brief)
        assert "H2" in prompt or "H3" in prompt

    def test_build_alt_text_prompt_includes_product(self, sample_brief):
        prompt = build_alt_text_prompt(sample_brief, {
            "name": "Quencher 40oz",
            "product_type": "Tumbler",
            "image_alt": "",
        })
        assert "Quencher 40oz" in prompt
        assert "5-12 words" in prompt
        assert "Image of" in prompt  # negative example in the template

    def test_full_brief_prompt_includes_target_bottom_words(self, sample_brief):
        sample_brief.target_bottom_word_count = 500
        prompt = build_full_brief_prompt(sample_brief)
        assert "500" in prompt
