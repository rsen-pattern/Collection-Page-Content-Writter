"""Audit checklist evaluation engine for collection pages."""

import json
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from core.data_ingestion import clean_keyword


class AuditCheck(BaseModel):
    """Result of a single audit check."""

    id: str
    label: str
    category: str
    result: str  # "pass", "fail", "needs_review"
    details: str = ""
    impact: str = "medium"
    effort: str = "medium"


class AuditResult(BaseModel):
    """Full audit result for a collection."""

    collection_url: str
    collection_name: str
    checks: list[AuditCheck] = Field(default_factory=list)
    total_checks: int = 0
    passing: int = 0
    failing: int = 0
    needs_review: int = 0

    @property
    def score_display(self) -> str:
        return f"{self.passing}/{self.total_checks}"


class CollectionAuditData(BaseModel):
    """Data needed to run an audit on a collection."""

    collection_url: str
    collection_name: str
    primary_keyword: str
    seo_title: str = ""
    h1: str = ""
    description: str = ""
    meta_description: str = ""
    word_count: int = 0
    internal_link_count: int = 0
    inbound_internal_links: int = 0
    linked_from_homepage: Optional[bool] = None
    linked_from_blog: Optional[bool] = None
    faq_content: str = ""
    structured_data: str = ""
    url_handle: str = ""
    brand_usps: list[str] = Field(default_factory=list)


def load_audit_checklist() -> dict:
    """Load audit checklist configuration."""
    config_path = Path(__file__).parent.parent / "config" / "audit_checklist.json"
    with open(config_path) as f:
        return json.load(f)


def _get_field_value(data: CollectionAuditData, field: str) -> str:
    """Get a field value from audit data."""
    return str(getattr(data, field, ""))


def _check_keyword_match(text: str, keyword: str) -> bool:
    """Check if keyword appears in text (case-insensitive, fuzzy)."""
    if not text or not keyword:
        return False
    text_lower = clean_keyword(text).lower()
    keyword_lower = clean_keyword(keyword).lower()
    if keyword_lower in text_lower:
        return True
    # Check individual words
    keyword_words = keyword_lower.split()
    if len(keyword_words) > 1:
        matches = sum(1 for w in keyword_words if w in text_lower)
        return matches >= len(keyword_words) * 0.7
    return False


def _check_usp_match(text: str, usps: list[str], min_matches: int) -> tuple[bool, int]:
    """Check how many USPs are referenced in the text."""
    if not text or not usps:
        return False, 0
    text_lower = clean_keyword(text).lower()
    matches = 0
    for usp in usps:
        usp_words = clean_keyword(usp).lower().split()
        key_words = [w for w in usp_words if len(w) > 3]
        if key_words and any(w in text_lower for w in key_words):
            matches += 1
    return matches >= min_matches, matches


def _count_links(text: str) -> int:
    """Count markdown and HTML links in text."""
    md_links = len(re.findall(r"\[.*?\]\(.*?\)", text))
    html_links = len(re.findall(r"<a\s+[^>]*href=", text, re.IGNORECASE))
    return md_links + html_links


def run_check(
    check_config: dict, data: CollectionAuditData, category: str
) -> AuditCheck:
    """Run a single audit check and return the result."""
    check_id = check_config["id"]
    label = check_config["label"]
    check_type = check_config["type"]
    field = check_config.get("field", "")
    impact = check_config.get("impact", "medium")
    effort = check_config.get("effort", "medium")

    value = _get_field_value(data, field)

    if check_type == "field_exists":
        passed = bool(value.strip())
        return AuditCheck(
            id=check_id,
            label=label,
            category=category,
            result="pass" if passed else "fail",
            details=f"{'Present' if passed else 'Missing'}",
            impact=impact,
            effort=effort,
        )

    elif check_type == "keyword_match":
        match_field = check_config.get("match_against", "primary_keyword")
        keyword = _get_field_value(data, match_field)
        passed = _check_keyword_match(value, keyword)
        return AuditCheck(
            id=check_id,
            label=label,
            category=category,
            result="pass" if passed else "fail",
            details=f"Keyword '{keyword}' {'found' if passed else 'not found'} in {field}",
            impact=impact,
            effort=effort,
        )

    elif check_type == "regex":
        pattern = check_config.get("pattern", "")
        passed = bool(re.match(pattern, value))
        return AuditCheck(
            id=check_id,
            label=label,
            category=category,
            result="pass" if passed else "fail",
            details=f"Pattern {'matched' if passed else 'not matched'}",
            impact=impact,
            effort=effort,
        )

    elif check_type == "word_count_range":
        words = len(value.split()) if value.strip() else 0
        min_w = check_config.get("min_words", 0)
        max_w = check_config.get("max_words", 999)
        passed = min_w <= words <= max_w
        return AuditCheck(
            id=check_id,
            label=label,
            category=category,
            result="pass" if passed else "fail",
            details=f"{words} words (target: {min_w}-{max_w})",
            impact=impact,
            effort=effort,
        )

    elif check_type == "char_count_range":
        chars = len(value)
        min_c = check_config.get("min_chars", 0)
        max_c = check_config.get("max_chars", 999)
        passed = min_c <= chars <= max_c
        return AuditCheck(
            id=check_id,
            label=label,
            category=category,
            result="pass" if passed else "fail",
            details=f"{chars} characters (target: {min_c}-{max_c})",
            impact=impact,
            effort=effort,
        )

    elif check_type == "string_differs":
        compare_field = check_config.get("compare_field", "")
        compare_value = _get_field_value(data, compare_field)
        if not value.strip() or not compare_value.strip():
            return AuditCheck(
                id=check_id,
                label=label,
                category=category,
                result="needs_review",
                details="One or both fields are empty",
                impact=impact,
                effort=effort,
            )
        passed = value.strip().lower() != compare_value.strip().lower()
        return AuditCheck(
            id=check_id,
            label=label,
            category=category,
            result="pass" if passed else "fail",
            details=f"{'Different' if passed else 'Same as'} {compare_field}",
            impact=impact,
            effort=effort,
        )

    elif check_type == "link_count":
        count = _count_links(value)
        min_links = check_config.get("min_links", 1)
        passed = count >= min_links
        return AuditCheck(
            id=check_id,
            label=label,
            category=category,
            result="pass" if passed else "fail",
            details=f"{count} links found (minimum: {min_links})",
            impact=impact,
            effort=effort,
        )

    elif check_type == "usp_match":
        min_matches = check_config.get("min_matches", 2)
        passed, count = _check_usp_match(value, data.brand_usps, min_matches)
        return AuditCheck(
            id=check_id,
            label=label,
            category=category,
            result="pass" if passed else "fail",
            details=f"{count}/{min_matches} USPs referenced",
            impact=impact,
            effort=effort,
        )

    elif check_type == "boolean_check":
        field_val = getattr(data, field, None)
        if field_val is None:
            return AuditCheck(
                id=check_id,
                label=label,
                category=category,
                result="needs_review",
                details="Data not available",
                impact=impact,
                effort=effort,
            )
        return AuditCheck(
            id=check_id,
            label=label,
            category=category,
            result="pass" if field_val else "fail",
            details=f"{'Yes' if field_val else 'No'}",
            impact=impact,
            effort=effort,
        )

    elif check_type == "numeric_min":
        num_val = getattr(data, field, 0) or 0
        min_val = check_config.get("min_value", 1)
        passed = num_val >= min_val
        return AuditCheck(
            id=check_id,
            label=label,
            category=category,
            result="pass" if passed else "fail",
            details=f"{num_val} (minimum: {min_val})",
            impact=impact,
            effort=effort,
        )

    elif check_type == "manual_review":
        return AuditCheck(
            id=check_id,
            label=label,
            category=category,
            result="needs_review",
            details="Requires manual review",
            impact=impact,
            effort=effort,
        )

    return AuditCheck(
        id=check_id,
        label=label,
        category=category,
        result="needs_review",
        details=f"Unknown check type: {check_type}",
        impact=impact,
        effort=effort,
    )


def audit_collection(data: CollectionAuditData) -> AuditResult:
    """Run the full audit checklist against a collection."""
    checklist = load_audit_checklist()
    checks = []

    for category_key, category_config in checklist["categories"].items():
        for check_config in category_config["checks"]:
            result = run_check(check_config, data, category_config["label"])
            checks.append(result)

    passing = sum(1 for c in checks if c.result == "pass")
    failing = sum(1 for c in checks if c.result == "fail")
    needs_review = sum(1 for c in checks if c.result == "needs_review")

    return AuditResult(
        collection_url=data.collection_url,
        collection_name=data.collection_name,
        checks=checks,
        total_checks=len(checks),
        passing=passing,
        failing=failing,
        needs_review=needs_review,
    )


def get_priority_actions(audit_result: AuditResult) -> list[AuditCheck]:
    """Get failing checks sorted by impact (high first) then effort (low first)."""
    impact_order = {"high": 0, "medium": 1, "low": 2}
    effort_order = {"low": 0, "medium": 1, "high": 2}

    failing = [c for c in audit_result.checks if c.result == "fail"]
    failing.sort(
        key=lambda c: (impact_order.get(c.impact, 1), effort_order.get(c.effort, 1))
    )
    return failing


def get_category_scores(audit_result: AuditResult) -> dict[str, dict]:
    """Get pass/total scores broken down by category."""
    categories = {}
    for check in audit_result.checks:
        if check.category not in categories:
            categories[check.category] = {"passing": 0, "total": 0}
        categories[check.category]["total"] += 1
        if check.result == "pass":
            categories[check.category]["passing"] += 1
    return categories
