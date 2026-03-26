"""Real-time content validation rules for generated content."""

import json
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    """Result of a single validation check."""

    rule: str
    passed: bool
    message: str
    severity: str = "error"  # "error", "warning", "info"


class ContentValidation(BaseModel):
    """Full validation result for generated content."""

    element: str  # "description", "seo_title", "collection_title", "meta_description", "faqs"
    results: list[ValidationResult] = Field(default_factory=list)
    all_passed: bool = True
    error_count: int = 0
    warning_count: int = 0


def _load_rules() -> dict:
    config_path = Path(__file__).parent.parent / "config" / "methodology_rules.json"
    with open(config_path) as f:
        return json.load(f)


def _count_words(text: str) -> int:
    return len(text.split()) if text.strip() else 0


def _count_links(text: str) -> int:
    md_links = len(re.findall(r"\[.*?\]\(.*?\)", text))
    html_links = len(re.findall(r"<a\s+[^>]*href=", text, re.IGNORECASE))
    return md_links + html_links


def _check_keyword_present(text: str, keyword: str) -> bool:
    return keyword.lower() in text.lower()


def _count_usp_matches(text: str, usps: list[str]) -> int:
    text_lower = text.lower()
    count = 0
    for usp in usps:
        key_words = [w for w in usp.lower().split() if len(w) > 3]
        if key_words and any(w in text_lower for w in key_words):
            count += 1
    return count


def validate_description(
    text: str,
    primary_keyword: str,
    secondary_keywords: list[str],
    brand_usps: list[str],
) -> ContentValidation:
    """Validate a collection description against methodology rules."""
    rules = _load_rules()
    cl = rules["content_length"]["description"]
    ci = rules["content_inclusion"]
    results = []

    # Word count
    wc = _count_words(text)
    in_sweet_spot = cl["sweet_spot_min"] <= wc <= cl["sweet_spot_max"]
    over_limit = wc > cl["upper_limit_warn"]
    over_ceiling = wc > cl["hard_ceiling"]

    if over_ceiling:
        results.append(ValidationResult(
            rule="word_count", passed=False,
            message=f"Word count ({wc}) exceeds hard ceiling of {cl['hard_ceiling']}",
            severity="error",
        ))
    elif over_limit:
        results.append(ValidationResult(
            rule="word_count", passed=False,
            message=f"Word count ({wc}) exceeds recommended limit of {cl['upper_limit_warn']}",
            severity="warning",
        ))
    elif in_sweet_spot:
        results.append(ValidationResult(
            rule="word_count", passed=True,
            message=f"Word count ({wc}) is in the sweet spot ({cl['sweet_spot_min']}-{cl['sweet_spot_max']})",
        ))
    else:
        results.append(ValidationResult(
            rule="word_count", passed=False,
            message=f"Word count ({wc}) is outside the sweet spot ({cl['sweet_spot_min']}-{cl['sweet_spot_max']})",
            severity="warning",
        ))

    # Primary keyword
    has_primary = _check_keyword_present(text, primary_keyword)
    results.append(ValidationResult(
        rule="primary_keyword", passed=has_primary,
        message=f"Primary keyword '{primary_keyword}' {'found' if has_primary else 'not found'}",
        severity="error" if not has_primary else "info",
    ))

    # Secondary keywords
    sec_found = sum(1 for kw in secondary_keywords if _check_keyword_present(text, kw))
    min_sec = ci["description_min_secondary_keywords"]
    results.append(ValidationResult(
        rule="secondary_keywords", passed=sec_found >= min_sec,
        message=f"{sec_found}/{len(secondary_keywords)} secondary keywords included (min: {min_sec})",
        severity="warning" if sec_found < min_sec else "info",
    ))

    # USP matches
    usp_count = _count_usp_matches(text, brand_usps)
    min_usps = ci["description_min_usps"]
    results.append(ValidationResult(
        rule="brand_usps", passed=usp_count >= min_usps,
        message=f"{usp_count}/{len(brand_usps)} USPs referenced (min: {min_usps})",
        severity="error" if usp_count < min_usps else "info",
    ))

    # Internal links
    link_count = _count_links(text)
    min_links = ci["description_product_links_min"]
    max_links = ci["description_product_links_max"]
    results.append(ValidationResult(
        rule="internal_links", passed=link_count >= min_links,
        message=f"{link_count} internal links (target: {min_links}-{max_links})",
        severity="error" if link_count < min_links else "info",
    ))

    validation = ContentValidation(element="description", results=results)
    validation.error_count = sum(1 for r in results if not r.passed and r.severity == "error")
    validation.warning_count = sum(1 for r in results if not r.passed and r.severity == "warning")
    validation.all_passed = validation.error_count == 0
    return validation


def validate_seo_title(
    text: str,
    primary_keyword: str,
    h1: str = "",
    brand_name: str = "",
) -> ContentValidation:
    """Validate an SEO title."""
    rules = _load_rules()
    cl = rules["content_length"]["seo_title"]
    results = []

    # Length
    char_count = len(text)
    in_range = cl["min_chars"] <= char_count <= cl["max_chars"]
    results.append(ValidationResult(
        rule="length", passed=in_range,
        message=f"{char_count} characters (target: {cl['min_chars']}-{cl['max_chars']})",
        severity="warning" if not in_range else "info",
    ))

    # Primary keyword first
    starts_with = text.lower().startswith(primary_keyword.lower())
    results.append(ValidationResult(
        rule="keyword_first", passed=starts_with,
        message=f"Primary keyword {'leads' if starts_with else 'does not lead'} the title",
        severity="error" if not starts_with else "info",
    ))

    # Separator
    has_sep = "|" in text or " - " in text
    results.append(ValidationResult(
        rule="separator", passed=has_sep,
        message=f"Separator format {'used' if has_sep else 'not used'}",
        severity="warning" if not has_sep else "info",
    ))

    # Differs from H1
    if h1:
        differs = text.strip().lower() != h1.strip().lower()
        results.append(ValidationResult(
            rule="differs_from_h1", passed=differs,
            message=f"{'Differs from' if differs else 'Same as'} H1",
            severity="error" if not differs else "info",
        ))

    validation = ContentValidation(element="seo_title", results=results)
    validation.error_count = sum(1 for r in results if not r.passed and r.severity == "error")
    validation.warning_count = sum(1 for r in results if not r.passed and r.severity == "warning")
    validation.all_passed = validation.error_count == 0
    return validation


def validate_collection_title(
    text: str,
    primary_keyword: str,
    seo_title: str = "",
) -> ContentValidation:
    """Validate a collection title (H1)."""
    results = []

    # Has keyword
    has_kw = _check_keyword_present(text, primary_keyword)
    results.append(ValidationResult(
        rule="has_keyword", passed=has_kw,
        message=f"Primary keyword {'included' if has_kw else 'not included'}",
        severity="error" if not has_kw else "info",
    ))

    # Concise
    wc = _count_words(text)
    concise = wc <= 8
    results.append(ValidationResult(
        rule="concise", passed=concise,
        message=f"{wc} words ({'concise' if concise else 'too long — keep under 8 words'})",
        severity="warning" if not concise else "info",
    ))

    # Differs from SEO title
    if seo_title:
        differs = text.strip().lower() != seo_title.strip().lower()
        results.append(ValidationResult(
            rule="differs_from_seo_title", passed=differs,
            message=f"{'Differs from' if differs else 'Same as'} SEO title",
            severity="error" if not differs else "info",
        ))

    validation = ContentValidation(element="collection_title", results=results)
    validation.error_count = sum(1 for r in results if not r.passed and r.severity == "error")
    validation.warning_count = sum(1 for r in results if not r.passed and r.severity == "warning")
    validation.all_passed = validation.error_count == 0
    return validation


def validate_meta_description(
    text: str,
    primary_keyword: str,
) -> ContentValidation:
    """Validate a meta description."""
    rules = _load_rules()
    max_chars = rules["content_length"]["meta_description"]["max_chars"]
    results = []

    # Length
    char_count = len(text)
    within = char_count <= max_chars
    results.append(ValidationResult(
        rule="length", passed=within,
        message=f"{char_count} characters (max: {max_chars})",
        severity="error" if not within else "info",
    ))

    # Has keyword
    has_kw = _check_keyword_present(text, primary_keyword)
    results.append(ValidationResult(
        rule="has_keyword", passed=has_kw,
        message=f"Primary keyword {'included' if has_kw else 'not included'}",
        severity="warning" if not has_kw else "info",
    ))

    # CTA check (basic)
    cta_patterns = ["shop", "browse", "discover", "explore", "find", "view", "buy", "order"]
    has_cta = any(p in text.lower() for p in cta_patterns)
    results.append(ValidationResult(
        rule="has_cta", passed=has_cta,
        message=f"CTA {'detected' if has_cta else 'not detected — consider ending with a call to action'}",
        severity="warning" if not has_cta else "info",
    ))

    validation = ContentValidation(element="meta_description", results=results)
    validation.error_count = sum(1 for r in results if not r.passed and r.severity == "error")
    validation.warning_count = sum(1 for r in results if not r.passed and r.severity == "warning")
    validation.all_passed = validation.error_count == 0
    return validation


def validate_faqs(
    faqs: list[dict],
    brand_name: str = "",
    batch_faq_topics: list[str] = None,
) -> ContentValidation:
    """Validate FAQ content."""
    rules = _load_rules()
    faq_rules = rules["content_length"]["faq"]
    results = []

    # Count
    count = len(faqs)
    in_range = faq_rules["count_min"] <= count <= faq_rules["count_max"]
    results.append(ValidationResult(
        rule="count", passed=in_range,
        message=f"{count} FAQs (target: {faq_rules['count_min']}-{faq_rules['count_max']})",
        severity="warning" if not in_range else "info",
    ))

    # Check for "What is" questions
    for i, faq in enumerate(faqs):
        q = faq.get("question", "")
        if q.lower().startswith("what is ") or q.lower().startswith("what are "):
            results.append(ValidationResult(
                rule=f"no_what_is_q{i+1}", passed=False,
                message=f'FAQ {i+1} starts with "What is/are" — rephrase',
                severity="error",
            ))

    # Check for duplicate topics in batch
    if batch_faq_topics:
        for i, faq in enumerate(faqs):
            q = faq.get("question", "").lower()
            for topic in batch_faq_topics:
                if topic.lower() in q:
                    results.append(ValidationResult(
                        rule=f"duplicate_topic_q{i+1}", passed=False,
                        message=f'FAQ {i+1} overlaps with existing batch topic: "{topic}"',
                        severity="warning",
                    ))

    validation = ContentValidation(element="faqs", results=results)
    validation.error_count = sum(1 for r in results if not r.passed and r.severity == "error")
    validation.warning_count = sum(1 for r in results if not r.passed and r.severity == "warning")
    validation.all_passed = validation.error_count == 0
    return validation
