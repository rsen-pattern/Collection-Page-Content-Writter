"""Content brief assembly for collection pages."""

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from core.data_ingestion import clean_keyword


_PLURAL_SUFFIXES = ("caps", "cap", "hats", "hat", "s")


def _deduplicate_keywords(primary: str, secondary: list[str]) -> list[str]:
    """Remove secondary keywords that are near-duplicates of primary or each other.

    Normalises by cleaning unicode, lowercasing, and stripping common cap/hat
    plural suffixes.  Primary is always kept.  Ordering of survivors is preserved.
    """
    def _norm(kw: str) -> str:
        kw = clean_keyword(kw).lower()
        for suffix in _PLURAL_SUFFIXES:
            if kw.endswith(" " + suffix):
                kw = kw[: -(len(suffix) + 1)]
                break
        return kw.strip()

    seen: set[str] = {_norm(primary)}
    deduped: list[str] = []
    for kw in secondary:
        norm = _norm(kw)
        if norm and norm not in seen:
            seen.add(norm)
            deduped.append(kw)
    return deduped


class ContentBrief(BaseModel):
    """Content brief for a single collection."""

    collection_url: str
    collection_name: str
    primary_keyword: str
    primary_keyword_volume: Optional[int] = None
    secondary_keywords: list[str] = Field(default_factory=list)
    brand_usps: list[str] = Field(default_factory=list)
    products_to_link: list[dict] = Field(default_factory=list)  # [{name, url}]
    related_collections: list[dict] = Field(default_factory=list)  # [{name, url}]
    target_word_count: int = 100
    paa_questions: list[str] = Field(default_factory=list)
    faq_count: int = 3
    voice_notes: str = ""
    brand_name: str = ""
    store_url: str = ""
    target_market: str = "UK"
    existing_content: str = ""


def load_methodology_rules() -> dict:
    """Load methodology rules."""
    config_path = Path(__file__).parent.parent / "config" / "methodology_rules.json"
    with open(config_path) as f:
        return json.load(f)


def calculate_target_word_count(
    keyword_difficulty: Optional[float] = None,
) -> int:
    """Calculate target word count based on keyword difficulty."""
    rules = load_methodology_rules()
    min_words = rules["content_length"]["description"]["sweet_spot_min"]
    max_words = rules["content_length"]["description"]["sweet_spot_max"]

    if keyword_difficulty is None:
        return (min_words + max_words) // 2

    # Higher difficulty → more content needed
    if keyword_difficulty >= 50:
        return max_words
    elif keyword_difficulty >= 30:
        return (min_words + max_words) // 2
    else:
        return min_words + 25  # ~75 words for low difficulty


def find_related_collections(
    target_collection: str,
    all_collections: list,
    max_related: int = 2,
) -> list[dict]:
    """Find related collections based on keyword overlap."""
    if not all_collections:
        return []

    target_words = set(target_collection.lower().split())
    scored = []

    for collection in all_collections:
        name = collection.get("collection_name", "")
        url = collection.get("collection_url", "")
        if url == target_collection:
            continue
        col_words = set(name.lower().split())
        overlap = len(target_words & col_words)
        if overlap > 0:
            scored.append({"name": name, "url": url, "overlap": overlap})

    scored.sort(key=lambda x: x["overlap"], reverse=True)
    return [{"name": s["name"], "url": s["url"]} for s in scored[:max_related]]


def build_brief(
    collection_url: str,
    collection_name: str,
    primary_keyword: str,
    primary_keyword_volume: Optional[int],
    secondary_keywords: list[dict],
    brand_usps: list[str],
    brand_name: str,
    store_url: str,
    target_market: str = "UK",
    voice_notes: str = "",
    products_to_link: list[dict] = None,
    related_collections: list[dict] = None,
    paa_questions: list[str] = None,
    keyword_difficulty: Optional[float] = None,
    existing_content: str = "",
) -> ContentBrief:
    """Build a content brief for a collection."""
    if products_to_link is None:
        products_to_link = []
    if related_collections is None:
        related_collections = []
    if paa_questions is None:
        paa_questions = []

    raw_secondary = [
        kw.get("keyword", kw) if isinstance(kw, dict) else kw
        for kw in secondary_keywords
    ]
    deduped_secondary = _deduplicate_keywords(primary_keyword, raw_secondary)
    secondary_kw_list = deduped_secondary[:10]

    target_word_count = calculate_target_word_count(keyword_difficulty)

    return ContentBrief(
        collection_url=collection_url,
        collection_name=collection_name,
        primary_keyword=primary_keyword,
        primary_keyword_volume=primary_keyword_volume,
        secondary_keywords=secondary_kw_list[:10],  # Cap at 10
        brand_usps=brand_usps,
        products_to_link=products_to_link,
        related_collections=related_collections,
        target_word_count=target_word_count,
        paa_questions=paa_questions[:5],
        faq_count=3,
        voice_notes=voice_notes,
        brand_name=brand_name,
        store_url=store_url,
        target_market=target_market,
        existing_content=existing_content,
    )


def build_briefs_for_batch(
    batch_collections: list,
    client_profile: dict,
    all_collections: list = None,
) -> list[ContentBrief]:
    """Build content briefs for a batch of collections."""
    if all_collections is None:
        all_collections = []

    briefs = []
    for collection in batch_collections:
        # Find related collections
        related = find_related_collections(
            collection.get("collection_url", ""),
            [c for c in all_collections if c.get("collection_url") != collection.get("collection_url")],
        )

        kw_difficulty = None
        for kw in collection.get("secondary_keywords", []):
            if isinstance(kw, dict) and "keyword_difficulty" in kw:
                kw_difficulty = kw["keyword_difficulty"]
                break

        brief = build_brief(
            collection_url=collection.get("collection_url", ""),
            collection_name=collection.get("collection_name", ""),
            primary_keyword=collection.get("primary_keyword", ""),
            primary_keyword_volume=collection.get("primary_keyword_volume"),
            secondary_keywords=collection.get("secondary_keywords", []),
            brand_usps=client_profile.get("brand_usps", []),
            brand_name=client_profile.get("brand_name", ""),
            store_url=client_profile.get("store_url", ""),
            target_market=client_profile.get("target_market", "UK"),
            voice_notes=client_profile.get("voice_notes", ""),
            products_to_link=collection.get("products_to_link", []),
            related_collections=related,
            paa_questions=collection.get("paa_questions", []),
            keyword_difficulty=kw_difficulty,
        )
        briefs.append(brief)

    return briefs
