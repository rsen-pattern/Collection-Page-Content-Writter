"""Tests for priority scoring module."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.priority_scorer import (
    score_organic_traffic,
    score_striking_distance,
    score_revenue_potential,
    score_competitive_gap,
    score_current_optimization,
    auto_score_collection,
    ScoringFactors,
)


class TestOrganicTrafficScore:
    def test_high_traffic(self):
        assert score_organic_traffic(150, 0) == 3

    def test_medium_traffic(self):
        assert score_organic_traffic(50, 0) == 2

    def test_low_traffic(self):
        assert score_organic_traffic(5, 0) == 1

    def test_estimated_from_volume(self):
        # 5000 * 0.03 = 150 → score 3
        assert score_organic_traffic(None, 5000) == 3


class TestStrikingDistanceScore:
    def test_position_8_to_17(self):
        assert score_striking_distance(12, []) == 3

    def test_position_18_to_25(self):
        assert score_striking_distance(20, []) == 2

    def test_no_striking_distance(self):
        assert score_striking_distance(3, []) == 1

    def test_secondary_ranks_matter(self):
        assert score_striking_distance(3, [None, 15, 30]) == 3

    def test_no_ranks(self):
        assert score_striking_distance(None, []) == 1


class TestRevenueScore:
    def test_high_product_count(self):
        assert score_revenue_potential(product_count=25) == 3

    def test_medium_product_count(self):
        assert score_revenue_potential(product_count=10) == 2

    def test_low_product_count(self):
        assert score_revenue_potential(product_count=2) == 1

    def test_inferred_from_volume(self):
        assert score_revenue_potential(volume=2000) == 3


class TestCompetitiveGapScore:
    def test_low_difficulty_poor_rank(self):
        assert score_competitive_gap(difficulty=20, best_rank=15) == 3

    def test_low_difficulty_good_rank(self):
        assert score_competitive_gap(difficulty=20, best_rank=5) == 2

    def test_high_difficulty(self):
        assert score_competitive_gap(difficulty=70, best_rank=20) == 1

    def test_no_data(self):
        assert score_competitive_gap(None, None) == 1


class TestCurrentOptimization:
    def test_nothing_optimized(self):
        assert score_current_optimization(False, False, False) == 3

    def test_partially_optimized(self):
        assert score_current_optimization(True, False, False) == 2

    def test_well_optimized(self):
        assert score_current_optimization(True, True, True) == 1


class TestScoringFactors:
    def test_total_calculation(self):
        factors = ScoringFactors(
            organic_traffic=3,
            striking_distance=3,
            revenue_potential=2,
            homepage_nav_link=1,
            current_optimization=3,
            competitive_gap=2,
        )
        assert factors.total == 14

    def test_max_score(self):
        factors = ScoringFactors(
            organic_traffic=3,
            striking_distance=3,
            revenue_potential=3,
            homepage_nav_link=3,
            current_optimization=3,
            competitive_gap=3,
        )
        assert factors.total == 18


class TestAutoScoreCollection:
    def test_returns_scored_collection(self):
        result = auto_score_collection(
            collection_url="https://example.com/collections/test",
            collection_name="Test",
            primary_keyword="test keyword",
            total_volume=3000,
            best_rank=10,
            total_clicks=100,
        )
        assert result.total_score > 0
        assert result.collection_name == "Test"
        assert result.total_score == result.scores.total
