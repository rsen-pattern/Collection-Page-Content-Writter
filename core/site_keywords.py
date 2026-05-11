"""Site-wide keyword corpus — for cannibalisation detection and new-keyword suggestions.

A second data source alongside per-collection keyword data. Holds every URL
and keyword pair on the site (from SEMrush / Ahrefs / Brightedge organic
keyword exports). Two outputs:

1. **Cannibalisation**: keywords where multiple URLs target the same intent.
   Two flavours:
   - *Primary overlap* — two or more :class:`CollectionGroup` instances share
     a ``primary_keyword``. Detected from the per-collection data alone, no
     site-keyword upload needed.
   - *Top-10 overlap* — from the site keyword corpus, keywords where ≥2 URLs
     rank in the top 10 positions. Surfaced as a "cannibalisation risk" badge
     on Priority Scoring.

2. **New keyword suggestions**: keywords from the site corpus that aren't
   yet assigned to any optimised collection. Surfaced as additional
   secondary-keyword candidates in the Content Studio Brief tab.

Format detection covers SEMrush, Ahrefs, and Brightedge Domain Keyword
exports. The parser is lenient — unknown columns are ignored, missing
columns fall back to defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd

from core.text_utils import clean_keyword, extract_collection_handle


# ─────────────────────────────────────────────────────────────────────────
# Data shapes
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class SiteKeywordRow:
    """One row in the site-wide keyword corpus."""

    keyword: str
    url: str
    search_volume: int = 0
    position: Optional[float] = None
    traffic: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "keyword": self.keyword,
            "url": self.url,
            "search_volume": self.search_volume,
            "position": self.position,
            "traffic": self.traffic,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SiteKeywordRow":
        return cls(
            keyword=data.get("keyword", ""),
            url=data.get("url", ""),
            search_volume=int(data.get("search_volume") or 0),
            position=_safe_float(data.get("position")),
            traffic=_safe_int(data.get("traffic")),
        )


@dataclass
class SiteKeywordCorpus:
    """Parsed site-wide keyword corpus, plus the format it came from."""

    source_format: str = "custom"
    rows: list[SiteKeywordRow] = field(default_factory=list)
    uploaded_at: str = ""
    error: str = ""

    @property
    def total_rows(self) -> int:
        return len(self.rows)

    @property
    def unique_keywords(self) -> int:
        return len({r.keyword.lower() for r in self.rows if r.keyword})

    @property
    def unique_urls(self) -> int:
        return len({r.url for r in self.rows if r.url})

    def to_dict(self) -> dict:
        return {
            "source_format": self.source_format,
            "rows": [r.to_dict() for r in self.rows],
            "uploaded_at": self.uploaded_at,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SiteKeywordCorpus":
        return cls(
            source_format=data.get("source_format", "custom"),
            rows=[SiteKeywordRow.from_dict(r) for r in data.get("rows", [])],
            uploaded_at=data.get("uploaded_at", ""),
            error=data.get("error", ""),
        )


@dataclass
class CannibalisationConflict:
    """One detected cannibalisation conflict — a keyword with multiple URLs."""

    keyword: str
    search_volume: int = 0
    # Each entry: {"url": str, "position": Optional[float]}
    urls: list[dict] = field(default_factory=list)
    # "primary_overlap" | "top_10_overlap" | "primary_and_top10"
    kind: str = "top_10_overlap"

    def to_dict(self) -> dict:
        return {
            "keyword": self.keyword,
            "search_volume": self.search_volume,
            "urls": list(self.urls),
            "kind": self.kind,
        }


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _safe_int(v) -> Optional[int]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _safe_float(v) -> Optional[float]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


# Column header patterns per vendor. Match is case-insensitive.
_VENDOR_PATTERNS = {
    "semrush": {
        "keyword": ["keyword"],
        "url": ["url"],
        "volume": ["search volume", "volume"],
        "position": ["position"],
        "traffic": ["traffic", "traffic (%)"],
    },
    "ahrefs": {
        "keyword": ["keyword"],
        "url": ["current url", "url"],
        "volume": ["volume", "search volume"],
        "position": ["current position", "position"],
        "traffic": ["traffic", "estimated traffic"],
    },
    "brightedge": {
        "keyword": ["keyword", "search term"],
        "url": ["landing page", "page url", "url"],
        "volume": ["search volume", "monthly searches"],
        "position": ["rank", "position", "average rank"],
        "traffic": ["estimated traffic", "traffic"],
    },
}


def _find_column(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """Return the actual column header matching any candidate (case-insensitive)."""
    lower_to_actual = {c.lower(): c for c in df.columns if isinstance(c, str)}
    for cand in candidates:
        if cand.lower() in lower_to_actual:
            return lower_to_actual[cand.lower()]
    return None


def detect_site_format(df: pd.DataFrame) -> str:
    """Detect SEMrush / Ahrefs / Brightedge from column headers. Returns
    'custom' when nothing matches."""
    cols_lower = {c.lower() for c in df.columns if isinstance(c, str)}

    # Strong, distinctive signal per vendor — these column names are vendor-specific.
    if "current url" in cols_lower and "current position" in cols_lower:
        return "ahrefs"
    if "landing page" in cols_lower or "average rank" in cols_lower:
        return "brightedge"
    if "search volume" in cols_lower and "url" in cols_lower and "position" in cols_lower:
        return "semrush"
    # Looser fallbacks.
    if "keyword" in cols_lower and "volume" in cols_lower:
        return "ahrefs"
    return "custom"


# ─────────────────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────────────────


def parse_site_keywords(
    df: pd.DataFrame,
    source_format: Optional[str] = None,
) -> SiteKeywordCorpus:
    """Parse a site-keyword DataFrame into a corpus.

    Auto-detects the format when ``source_format`` is None. Rows with no
    keyword or no URL are dropped silently. Position / traffic are
    optional and missing values are tolerated.
    """
    fmt = source_format or detect_site_format(df)
    patterns = _VENDOR_PATTERNS.get(fmt, _VENDOR_PATTERNS["semrush"])

    kw_col = _find_column(df, patterns["keyword"])
    url_col = _find_column(df, patterns["url"])
    vol_col = _find_column(df, patterns["volume"])
    pos_col = _find_column(df, patterns["position"])
    traffic_col = _find_column(df, patterns["traffic"])

    if not kw_col or not url_col:
        return SiteKeywordCorpus(
            source_format=fmt,
            error=(
                "Could not locate keyword + URL columns. Expected vendor "
                "headers like 'Keyword' and 'URL' / 'Current URL' / "
                "'Landing Page'."
            ),
            uploaded_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        )

    rows: list[SiteKeywordRow] = []
    for _, row in df.iterrows():
        raw_kw = row.get(kw_col)
        raw_url = row.get(url_col)
        if raw_kw is None or raw_url is None:
            continue
        if isinstance(raw_kw, float) and pd.isna(raw_kw):
            continue
        if isinstance(raw_url, float) and pd.isna(raw_url):
            continue
        keyword = clean_keyword(str(raw_kw)).strip()
        url = str(raw_url).strip()
        if not keyword or not url:
            continue
        rows.append(SiteKeywordRow(
            keyword=keyword,
            url=url,
            search_volume=_safe_int(row.get(vol_col)) or 0 if vol_col else 0,
            position=_safe_float(row.get(pos_col)) if pos_col else None,
            traffic=_safe_int(row.get(traffic_col)) if traffic_col else None,
        ))

    return SiteKeywordCorpus(
        source_format=fmt,
        rows=rows,
        uploaded_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
    )


# ─────────────────────────────────────────────────────────────────────────
# Cannibalisation detection
# ─────────────────────────────────────────────────────────────────────────


def find_primary_keyword_conflicts(
    collection_groups: list,
) -> list[CannibalisationConflict]:
    """Detect collections whose ``primary_keyword`` is shared.

    Operates on the per-collection data only — no site keyword corpus
    required. The conflicting URLs are the collection URLs themselves.
    """
    by_kw: dict[str, list[dict]] = {}
    for g in collection_groups:
        kw = _attr(g, "primary_keyword", "")
        url = _attr(g, "collection_url", "")
        if not kw or not url:
            continue
        norm_kw = kw.lower().strip()
        by_kw.setdefault(norm_kw, []).append({
            "url": url,
            "position": None,
            "collection_name": _attr(g, "collection_name", ""),
        })

    conflicts: list[CannibalisationConflict] = []
    for norm_kw, urls in by_kw.items():
        if len(urls) > 1:
            conflicts.append(CannibalisationConflict(
                keyword=norm_kw,
                search_volume=0,
                urls=urls,
                kind="primary_overlap",
            ))
    return conflicts


def find_top_10_conflicts(
    corpus: SiteKeywordCorpus,
    min_position: int = 1,
    max_position: int = 10,
) -> list[CannibalisationConflict]:
    """Detect keywords where ≥2 site URLs rank inside the [min, max] range.

    Default range is 1–10 (top-10 SERP). The user's spec also flagged 5–10
    as a stricter band — callers can narrow the range to suit.
    """
    by_kw: dict[str, list[dict]] = {}
    volumes: dict[str, int] = {}
    for row in corpus.rows:
        if row.position is None:
            continue
        if not (min_position <= row.position <= max_position):
            continue
        norm_kw = row.keyword.lower().strip()
        if not norm_kw:
            continue
        by_kw.setdefault(norm_kw, []).append({
            "url": row.url,
            "position": row.position,
        })
        if row.search_volume:
            volumes[norm_kw] = max(volumes.get(norm_kw, 0), row.search_volume)

    conflicts: list[CannibalisationConflict] = []
    for norm_kw, urls in by_kw.items():
        # Distinct URLs only — same URL ranking multiple times is not a conflict.
        unique_urls = {u["url"] for u in urls}
        if len(unique_urls) > 1:
            # Keep one entry per distinct URL, picking its best (lowest) position.
            best_by_url: dict[str, dict] = {}
            for u in urls:
                cur = best_by_url.get(u["url"])
                if cur is None or u["position"] < cur["position"]:
                    best_by_url[u["url"]] = u
            conflicts.append(CannibalisationConflict(
                keyword=norm_kw,
                search_volume=volumes.get(norm_kw, 0),
                urls=sorted(best_by_url.values(), key=lambda d: d["position"]),
                kind="top_10_overlap",
            ))
    return conflicts


def find_all_cannibalisation(
    collection_groups: list,
    corpus: Optional[SiteKeywordCorpus] = None,
) -> list[CannibalisationConflict]:
    """Combine primary-keyword and top-10 overlap detection.

    When a keyword surfaces from both detection passes, the conflict's
    ``kind`` is set to ``primary_and_top10``.
    """
    primary = find_primary_keyword_conflicts(collection_groups)
    top10 = find_top_10_conflicts(corpus) if corpus is not None else []

    by_kw: dict[str, CannibalisationConflict] = {c.keyword: c for c in primary}
    for c in top10:
        if c.keyword in by_kw:
            existing = by_kw[c.keyword]
            existing.kind = "primary_and_top10"
            # Merge URL lists, dedup by URL.
            seen = {u["url"] for u in existing.urls}
            for u in c.urls:
                if u["url"] not in seen:
                    existing.urls.append(u)
                    seen.add(u["url"])
            existing.search_volume = max(existing.search_volume, c.search_volume)
        else:
            by_kw[c.keyword] = c

    # Sort by search volume desc (most consequential conflicts first).
    return sorted(by_kw.values(), key=lambda c: c.search_volume, reverse=True)


def conflicts_for_url(
    conflicts: list[CannibalisationConflict],
    url: str,
) -> list[CannibalisationConflict]:
    """Return conflicts that mention the given URL."""
    return [c for c in conflicts if any(u["url"] == url for u in c.urls)]


# ─────────────────────────────────────────────────────────────────────────
# New-keyword suggestions
# ─────────────────────────────────────────────────────────────────────────


def suggest_keywords_for_collection(
    collection_url: str,
    corpus: SiteKeywordCorpus,
    existing_keywords: Optional[list[str]] = None,
    *,
    max_suggestions: int = 8,
    min_volume: int = 20,
) -> list[SiteKeywordRow]:
    """Return site-corpus keywords that this collection could target.

    Heuristic: rows whose URL exactly matches the collection URL or shares
    the same collection handle. Excludes keywords already in
    ``existing_keywords``. Sorted by search volume desc.
    """
    if not collection_url or not corpus.rows:
        return []

    existing_lower = {k.lower().strip() for k in (existing_keywords or []) if k}
    target_handle = extract_collection_handle(collection_url)

    matches: dict[str, SiteKeywordRow] = {}
    for row in corpus.rows:
        if row.search_volume < min_volume:
            continue
        norm_kw = row.keyword.lower().strip()
        if not norm_kw or norm_kw in existing_lower:
            continue
        row_handle = extract_collection_handle(row.url)
        is_same_url = row.url == collection_url
        is_same_handle = bool(target_handle) and row_handle == target_handle
        if not (is_same_url or is_same_handle):
            continue
        # Keep the highest-volume entry per keyword.
        cur = matches.get(norm_kw)
        if cur is None or row.search_volume > cur.search_volume:
            matches[norm_kw] = row

    ranked = sorted(matches.values(), key=lambda r: r.search_volume, reverse=True)
    return ranked[:max_suggestions]


# ─────────────────────────────────────────────────────────────────────────
# Internal duck-typing helper
# ─────────────────────────────────────────────────────────────────────────


def _attr(obj, name: str, default=""):
    """Read ``name`` from ``obj``, tolerating both dict and Pydantic-model shapes."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


__all__ = [
    "CannibalisationConflict",
    "SiteKeywordCorpus",
    "SiteKeywordRow",
    "conflicts_for_url",
    "detect_site_format",
    "find_all_cannibalisation",
    "find_primary_keyword_conflicts",
    "find_top_10_conflicts",
    "parse_site_keywords",
    "suggest_keywords_for_collection",
]
