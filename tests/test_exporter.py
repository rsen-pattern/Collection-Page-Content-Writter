"""Tests for core.exporter."""

import io
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.exporter import export_keyword_map_roundtrip


def _read_back(buf: io.BytesIO) -> pd.DataFrame:
    buf.seek(0)
    return pd.read_excel(buf, sheet_name="Keyword Map")


def _make_collection(secondary_keywords):
    return {
        "collection_url": "https://x.com/collections/y",
        "collection_name": "Y",
        "primary_keyword": "alpha",
        "primary_keyword_volume": 1000,
        "secondary_keywords_raw": [
            {"keyword": kw, "search_volume": vol}
            for kw, vol in secondary_keywords
        ],
        "content": {
            "seo_title": "T",
            "collection_title": "H1",
            "description": "D",
            "meta_description": "M",
            "approved": True,
        },
    }


class TestRoundTripWidth:
    def test_default_width_four_emits_three_secondary_pairs(self):
        col = _make_collection([("beta", 200), ("gamma", 100)])
        df = _read_back(export_keyword_map_roundtrip([col]))
        # Primary + 3 secondary slots = 4 keyword columns.
        for n in (2, 3, 4):
            assert f"Target Keyword {n}" in df.columns
        assert "Target Keyword 5" not in df.columns
        assert df.loc[0, "Target Keyword 2"] == "beta"
        assert df.loc[0, "Target Keyword 3"] == "gamma"
        assert df.loc[0, "Target Keyword 4"] == "" or pd.isna(df.loc[0, "Target Keyword 4"])

    def test_explicit_width_six_emits_six_keyword_columns(self):
        col = _make_collection([("k2", 1), ("k3", 1), ("k4", 1), ("k5", 1), ("k6", 1)])
        df = _read_back(export_keyword_map_roundtrip([col], keyword_width=6))
        for n in range(2, 7):
            assert f"Target Keyword {n}" in df.columns
        assert "Target Keyword 7" not in df.columns
        assert df.loc[0, "Target Keyword 6"] == "k6"

    def test_padding_when_fewer_secondary_than_width(self):
        col = _make_collection([("beta", 200)])
        df = _read_back(export_keyword_map_roundtrip([col], keyword_width=4))
        assert df.loc[0, "Target Keyword 2"] == "beta"
        # Empty pads — pandas may read as NaN or "".
        for n in (3, 4):
            val = df.loc[0, f"Target Keyword {n}"]
            assert val == "" or pd.isna(val)
