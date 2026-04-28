"""6-factor priority scoring model for collection optimization."""

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class ScoringFactors(BaseModel):
    """Individual scores for the 6 priority factors."""

    organic_traffic: int = Field(1, ge=1, le=3)
    striking_distance: int = Field(1, ge=1, le=3)
    revenue_potential: int = Field(1, ge=1, le=3)
    homepage_nav_link: int = Field(1, ge=1, le=3)
    current_optimization: int = Field(1, ge=1, le=3)
    competitive_gap: int = Field(1, ge=1, le=3)

    @property
    def total(self) -> int:
        return (
            self.organic_traffic
            + self.striking_distance
            + self.revenue_potential
            + self.homepage_nav_link
            + self.current_optimization
            + self.competitive_gap
        )


class ScoredCollection(BaseModel):
    """A collection with its priority score."""

    collection_url: str
    collection_name: str
    primary_keyword: str
    scores: ScoringFactors
    total_score: int = 0
    in_batch: bool = False

    # Source data for reference
    total_volume: int = 0
    best_rank: Optional[int] = None
    total_clicks: Optional[int] = None
    keyword_count: int = 0
    secondary_keywords: list[dict] = Field(default_factory=list)

    # Data availability flags — False when the factor defaulted due to missing data
    has_rank_data: bool = True
    has_difficulty_data: bool = True
    has_click_data: bool = True
    has_optimization_data: bool = False  # True when current_optimization came from SF data

    def model_post_init(self, __context):
        self.total_score = self.scores.total


def load_methodology_rules() -> dict:
    """Load methodology rules configuration."""
    config_path = Path(__file__).parent.parent / "config" / "methodology_rules.json"
    with open(config_path) as f:
        return json.load(f)


def score_organic_traffic(
    clicks: Optional[int],
    volume: int,
    volume_only: bool = False,
) -> int:
    """Score based on current organic traffic (clicks or estimated from volume)."""
    if volume_only:
        # Direct volume bands — used when click data is not available (keyword_map)
        if volume >= 500:
            return 3
        if volume >= 100:
            return 2
        return 1
    traffic = clicks if clicks is not None else volume * 0.03  # ~3% CTR estimate
    if traffic >= 100:
        return 3
    elif traffic >= 20:
        return 2
    return 1


def score_striking_distance(best_rank: Optional[int], ranks: list[Optional[int]]) -> int:
    """Score based on striking distance keywords (positions 8-17 highest priority)."""
    all_ranks = [r for r in ([best_rank] + ranks) if r is not None]
    if not all_ranks:
        return 1

    has_8_to_17 = any(8 <= r <= 17 for r in all_ranks)
    has_18_to_25 = any(18 <= r <= 25 for r in all_ranks)

    if has_8_to_17:
        return 3
    elif has_18_to_25:
        return 2
    return 1


def score_revenue_potential(
    product_count: Optional[int] = None, volume: int = 0
) -> int:
    """Score revenue potential (manual input or inferred from volume)."""
    if product_count is not None:
        if product_count >= 20:
            return 3
        elif product_count >= 5:
            return 2
        return 1

    if volume >= 1000:
        return 3
    elif volume >= 200:
        return 2
    return 1


def score_homepage_nav_link(linked: Optional[bool] = None) -> int:
    """Score based on whether collection is linked from homepage/nav. Manual input."""
    if linked is None:
        return 1
    return 3 if linked else 1


def score_current_optimization(
    has_description: bool = False,
    has_meta: bool = False,
    title_optimized: bool = False,
) -> int:
    """Score current optimization level (lower = more opportunity)."""
    optimized_count = sum([has_description, has_meta, title_optimized])
    if optimized_count == 0:
        return 3  # High priority: nothing optimized
    elif optimized_count <= 1:
        return 2
    return 1  # Already somewhat optimized


def score_competitive_gap(
    difficulty: Optional[float] = None, best_rank: Optional[int] = None
) -> int:
    """Score competitive gap (keyword difficulty vs current rank)."""
    if difficulty is None or best_rank is None:
        return 1

    if difficulty < 30 and best_rank > 10:
        return 3  # Low difficulty, not ranking well = big opportunity
    elif difficulty < 50 and best_rank > 15:
        return 3
    elif difficulty < 30 and best_rank <= 10:
        return 2  # Low difficulty, decent rank
    elif difficulty < 50:
        return 2
    return 1


def auto_score_collection(
    collection_url: str,
    collection_name: str,
    primary_keyword: str,
    total_volume: int = 0,
    best_rank: Optional[int] = None,
    total_clicks: Optional[int] = None,
    keyword_count: int = 0,
    keyword_difficulty: Optional[float] = None,
    secondary_keywords: list[dict] = None,
    all_ranks: list[Optional[int]] = None,
    volume_only: bool = False,
) -> ScoredCollection:
    """Auto-score a collection using available data."""
    if secondary_keywords is None:
        secondary_keywords = []
    if all_ranks is None:
        all_ranks = [kw.get("current_rank") for kw in secondary_keywords]

    has_rank_data = best_rank is not None or any(r is not None for r in all_ranks)
    has_difficulty_data = keyword_difficulty is not None
    has_click_data = total_clicks is not None

    scores = ScoringFactors(
        organic_traffic=score_organic_traffic(total_clicks, total_volume, volume_only=volume_only),
        striking_distance=score_striking_distance(best_rank, all_ranks),
        revenue_potential=score_revenue_potential(volume=total_volume),
        homepage_nav_link=1,  # Requires manual input
        current_optimization=3,  # Default: assume not optimized (Phase 1)
        competitive_gap=score_competitive_gap(keyword_difficulty, best_rank),
    )

    return ScoredCollection(
        collection_url=collection_url,
        collection_name=collection_name,
        primary_keyword=primary_keyword,
        scores=scores,
        total_volume=total_volume,
        best_rank=best_rank,
        total_clicks=total_clicks,
        keyword_count=keyword_count,
        secondary_keywords=secondary_keywords,
        has_rank_data=has_rank_data,
        has_difficulty_data=has_difficulty_data,
        has_click_data=has_click_data,
    )


def score_all_collections(collection_groups: list, volume_only: bool = False) -> list[ScoredCollection]:
    """Score all collection groups and return sorted by priority."""
    scored = []
    for group in collection_groups:
        kw_difficulty = None
        all_ranks = []
        for kw in group.secondary_keywords:
            if "keyword_difficulty" in kw:
                kw_difficulty = kw_difficulty or kw["keyword_difficulty"]
            if "current_rank" in kw:
                all_ranks.append(kw["current_rank"])

        scored_collection = auto_score_collection(
            collection_url=group.collection_url,
            collection_name=group.collection_name,
            primary_keyword=group.primary_keyword,
            total_volume=group.total_volume,
            best_rank=group.best_rank,
            total_clicks=group.total_clicks,
            keyword_count=len(group.secondary_keywords) + 1,
            keyword_difficulty=kw_difficulty,
            secondary_keywords=group.secondary_keywords,
            all_ranks=all_ranks,
            volume_only=volume_only,
        )
        scored.append(scored_collection)

    scored.sort(key=lambda s: s.total_score, reverse=True)
    return scored


def identify_sub_collection_opportunities(
    collection_groups: list,
    min_volume: int = 500,
) -> list[dict]:
    """Identify modifier keywords that could be sub-collection candidates."""
    opportunities = []

    modifier_patterns = [
        "black", "white", "red", "blue", "green", "pink", "gold", "silver",
        "velvet", "leather", "cotton", "silk", "wooden", "metal",
        "small", "large", "mini", "big", "round", "square",
        "mens", "womens", "kids", "boys", "girls",
        "cheap", "luxury", "premium", "best",
    ]

    for group in collection_groups:
        collection_modifiers = []
        for kw_data in group.secondary_keywords:
            keyword = kw_data.get("keyword", "").lower()
            volume = kw_data.get("search_volume", 0)

            if volume and volume >= min_volume:
                has_modifier = any(mod in keyword for mod in modifier_patterns)
                is_longer = len(keyword.split()) > len(group.primary_keyword.split())
                if has_modifier or is_longer:
                    collection_modifiers.append(
                        {
                            "keyword": kw_data["keyword"],
                            "volume": volume,
                            "parent_collection": group.collection_name,
                            "parent_url": group.collection_url,
                        }
                    )

        if collection_modifiers:
            collection_modifiers.sort(key=lambda x: x["volume"], reverse=True)
            opportunities.extend(collection_modifiers)

    return opportunities
