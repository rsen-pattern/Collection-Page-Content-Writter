"""Content brief assembly for collection pages."""

import json
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from core.text_utils import clean_keyword


_PUNCT_RE = re.compile(r"[^\w\s]")


def _normalise_for_dedup(kw: str, overrides: Optional[dict] = None) -> str:
    """Normalise a keyword for duplicate detection.

    When ``overrides`` is provided and the lowercase keyword matches a key,
    the override value is returned verbatim — this is the escape hatch for
    brands whose singular vs plural variants target different intents.

    Otherwise: lowercases, cleans unicode, strips punctuation, then applies
    basic English plural-to-singular morphology:

    - ``-ies`` → ``-y``    (categories → category)
    - ``-sses`` → ``-ss``  (dresses → dress)
    - ``-ss`` left intact   (dress, glass — never stripped)
    - ``-es`` (>3 chars)   → strip ``-es``    (boxes → box)
    - ``-s`` (>3 chars)    → strip ``-s``     (shirts → shirt)

    Words ≤ 3 chars left untouched so we don't mangle stems like "gas".
    """
    cleaned_raw = clean_keyword(kw).lower()
    if overrides and cleaned_raw in overrides:
        return str(overrides[cleaned_raw])
    cleaned = _PUNCT_RE.sub(" ", cleaned_raw)
    parts = []
    for word in cleaned.split():
        if len(word) > 3 and word.endswith("ies"):
            parts.append(word[:-3] + "y")
        elif len(word) > 4 and word.endswith("sses"):
            parts.append(word[:-2])
        elif len(word) > 3 and word.endswith("ss"):
            parts.append(word)
        elif len(word) > 3 and word.endswith("es"):
            parts.append(word[:-2])
        elif len(word) > 3 and word.endswith("s"):
            parts.append(word[:-1])
        else:
            parts.append(word)
    return " ".join(parts).strip()


def _deduplicate_keywords(
    primary: str,
    secondary: list[str],
    overrides: Optional[dict] = None,
) -> list[str]:
    """Remove secondary keywords that are near-duplicates of primary or each other.

    Normalisation uses :func:`_normalise_for_dedup` so plural/singular pairs
    collapse across any vertical (not just cap/hat). Primary is always kept;
    survivors keep their original ordering. ``overrides`` is forwarded to the
    normaliser so brand-level escape hatches take effect.
    """
    seen: set[str] = {_normalise_for_dedup(primary, overrides)}
    deduped: list[str] = []
    for kw in secondary:
        norm = _normalise_for_dedup(kw, overrides)
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
    related_blog_posts: list[dict] = Field(default_factory=list)  # [{name, url}]
    target_word_count: int = 200  # kept for compat; mirrors target_bottom_word_count
    target_bottom_word_count: int = 200  # bottom-copy target, scales with KD
    paa_questions: list[str] = Field(default_factory=list)
    faq_count: int = 4
    voice_notes: str = ""
    brand_name: str = ""
    store_url: str = ""
    target_market: str = "UK"
    existing_content: str = Field(
        default="",
        description=(
            "Free-form reference text. Use for content that isn't clearly "
            "top-of-page or bottom-of-page (e.g. a pasted paragraph from "
            "the brief). Kept for backward compatibility."
        ),
    )
    existing_top_copy: str = Field(
        default="",
        description=(
            "Current copy above the product grid on the live page. Surfaced "
            "to prompts as a labelled section so the model can preserve top-"
            "vs-bottom voice and so re-generation can target one section."
        ),
    )
    existing_bottom_copy: str = Field(
        default="",
        description="Current copy below the product grid on the live page.",
    )
    past_feedback: str = ""
    prompt_overrides: dict = Field(default_factory=dict)


def load_methodology_rules() -> dict:
    """Load methodology rules."""
    config_path = Path(__file__).parent.parent / "config" / "methodology_rules.json"
    with open(config_path) as f:
        return json.load(f)


def calculate_target_word_counts(
    keyword_difficulty: Optional[float] = None,
) -> tuple[int, int]:
    """Calculate target word counts for top and bottom of page based on KD.

    Top stays compact regardless of difficulty. Bottom scales: low-difficulty
    collections get tight copy, high-difficulty competitive collections get
    much longer depth (per Shopify SEO guides recommending up to ~1000 words).

    Returns (top_target, bottom_target) — these are TARGETS for the model,
    not absolute caps. Validator caps come from methodology_rules.json.
    """
    rules = load_methodology_rules()
    top_cfg = rules["content_length"]["top_of_page_copy"]
    top_min = top_cfg["sweet_spot_min_words"]
    top_max = top_cfg["sweet_spot_max_words"]

    if keyword_difficulty is None:
        top_target = (top_min + top_max) // 2
        bottom_target = 200
        return top_target, bottom_target

    if keyword_difficulty >= 50:
        top_target = top_max
    elif keyword_difficulty >= 30:
        top_target = (top_min + top_max) // 2
    else:
        top_target = top_min + 5

    if keyword_difficulty >= 60:
        bottom_target = 800
    elif keyword_difficulty >= 40:
        bottom_target = 500
    elif keyword_difficulty >= 20:
        bottom_target = 250
    else:
        bottom_target = 125

    return top_target, bottom_target


def calculate_target_word_count(
    keyword_difficulty: Optional[float] = None,
) -> int:
    """Calculate bottom-copy target word count. Kept for backward compatibility."""
    _, bottom = calculate_target_word_counts(keyword_difficulty)
    return bottom


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


def _apply_sitemap_fallback(
    sitemap,
    primary_keyword: str,
    secondary_keywords: list[str],
    target_url: str,
    products_to_link: list[dict],
    related_collections: list[dict],
    related_blog_posts: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Fill empty link slots from sitemap matches. Existing values are preserved.

    The sitemap module is optional — callers pass ``None`` when no sitemap is
    loaded, in which case the inputs are returned untouched.
    """
    if sitemap is None:
        return products_to_link, related_collections, related_blog_posts
    from core.sitemap import find_related_urls

    suggestions = find_related_urls(
        primary_keyword=primary_keyword,
        secondary_keywords=secondary_keywords,
        sitemap=sitemap,
        target_url=target_url,
    )
    if not products_to_link:
        products_to_link = [{"name": s["name"], "url": s["url"]} for s in suggestions["products"]]
    if not related_collections:
        related_collections = [{"name": s["name"], "url": s["url"]} for s in suggestions["collections"]]
    if not related_blog_posts:
        related_blog_posts = [{"name": s["name"], "url": s["url"]} for s in suggestions["blog_posts"]]
    return products_to_link, related_collections, related_blog_posts


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
    related_blog_posts: list[dict] = None,
    paa_questions: list[str] = None,
    keyword_difficulty: Optional[float] = None,
    existing_content: str = "",
    existing_top_copy: str = "",
    existing_bottom_copy: str = "",
    faq_count: int = 4,
    past_feedback: str = "",
    prompt_overrides: dict = None,
    sitemap=None,
) -> ContentBrief:
    """Build a content brief for a collection.

    When ``sitemap`` is provided, any empty link slots
    (``products_to_link``/``related_collections``/``related_blog_posts``) are
    filled with sitemap-matched URLs. Existing values are never overwritten.
    """
    if products_to_link is None:
        products_to_link = []
    if related_collections is None:
        related_collections = []
    if related_blog_posts is None:
        related_blog_posts = []
    if paa_questions is None:
        paa_questions = []
    if prompt_overrides is None:
        prompt_overrides = {}

    raw_secondary = [
        kw.get("keyword", kw) if isinstance(kw, dict) else kw
        for kw in secondary_keywords
    ]
    dedup_overrides = (prompt_overrides or {}).get("dedup_overrides") or {}
    deduped_secondary = _deduplicate_keywords(
        primary_keyword, raw_secondary, overrides=dedup_overrides
    )
    secondary_kw_list = deduped_secondary[:10]

    products_to_link, related_collections, related_blog_posts = _apply_sitemap_fallback(
        sitemap=sitemap,
        primary_keyword=primary_keyword,
        secondary_keywords=secondary_kw_list,
        target_url=collection_url,
        products_to_link=products_to_link,
        related_collections=related_collections,
        related_blog_posts=related_blog_posts,
    )

    _, bottom_target = calculate_target_word_counts(keyword_difficulty)

    return ContentBrief(
        collection_url=collection_url,
        collection_name=collection_name,
        primary_keyword=primary_keyword,
        primary_keyword_volume=primary_keyword_volume,
        secondary_keywords=secondary_kw_list[:10],
        brand_usps=brand_usps,
        products_to_link=products_to_link,
        related_collections=related_collections,
        related_blog_posts=related_blog_posts,
        target_word_count=bottom_target,
        target_bottom_word_count=bottom_target,
        paa_questions=paa_questions[:5],
        faq_count=faq_count,
        voice_notes=voice_notes,
        brand_name=brand_name,
        store_url=store_url,
        target_market=target_market,
        existing_content=existing_content,
        existing_top_copy=existing_top_copy,
        existing_bottom_copy=existing_bottom_copy,
        past_feedback=past_feedback,
        prompt_overrides=prompt_overrides,
    )


def build_briefs_for_batch(
    batch_collections: list,
    client_profile: dict,
    all_collections: list = None,
    sitemap=None,
) -> list[ContentBrief]:
    """Build content briefs for a batch of collections.

    ``sitemap`` is an optional ``ParsedSitemap`` used to fill empty link slots
    on each brief. When None, behaviour is unchanged from prior versions.
    """
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

        # Pass top/bottom/other through as structured fields. Free-form
        # "existing_content" only carries text that doesn't fit either slot
        # (e.g. a manually pasted reference paragraph).
        existing_top = collection.get("existing_top_copy", "")
        existing_bottom = collection.get("existing_bottom_copy", "")
        existing_other = collection.get("existing_content", "")

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
            related_blog_posts=collection.get("related_blog_posts", []),
            paa_questions=collection.get("paa_questions", []),
            keyword_difficulty=kw_difficulty,
            existing_content=existing_other,
            existing_top_copy=existing_top,
            existing_bottom_copy=existing_bottom,
            faq_count=client_profile.get("faq_count", 4),
            past_feedback=client_profile.get("past_feedback", ""),
            prompt_overrides=client_profile.get("prompt_overrides", {}),
            sitemap=sitemap,
        )
        briefs.append(brief)

    return briefs
