"""Screaming Frog crawl CSV parser."""

from dataclasses import dataclass
from typing import Optional

import pandas as pd


SF_COLUMN_MAP = {
    "url":                     ["Address"],
    "seo_title":               ["Title 1", "Title"],
    "title_length":            ["Title 1 Length"],
    "title_2":                 ["Title 2"],
    "meta_description":        ["Meta Description 1", "Meta Description"],
    "meta_description_length": ["Meta Description 1 Length"],
    "h1":                      ["H1-1", "H1 1", "H1"],
    "h1_length":               ["H1-1 Length", "H1 1 Length"],
    "h1_2":                    ["H1-2", "H1 2"],
    "word_count":              ["Word Count"],
    "status_code":             ["Status Code"],
    "indexability":            ["Indexability"],
    "inlinks":                 ["Unique Inlinks"],
    "crawl_depth":             ["Crawl Depth"],
    "response_time":           ["Response Time"],
}


@dataclass
class SFPageData:
    """Data extracted from a single Screaming Frog crawl row."""

    url: str
    seo_title: str = ""
    title_length: Optional[int] = None
    title_2: str = ""
    meta_description: str = ""
    meta_description_length: Optional[int] = None
    h1: str = ""
    h1_length: Optional[int] = None
    h1_2: str = ""
    word_count: Optional[int] = None
    status_code: Optional[int] = None
    indexability: str = ""
    inlinks: Optional[int] = None
    crawl_depth: Optional[int] = None
    response_time: Optional[float] = None


@dataclass
class AuditFlag:
    """A pre-flight audit issue derived from SF crawl data."""

    flag_id: str
    severity: str  # 'error' | 'warning'
    message: str


def _safe_str(val) -> str:
    try:
        if pd.isna(val):
            return ""
        return str(val).strip()
    except (ValueError, TypeError):
        return ""


def _safe_int(val) -> Optional[int]:
    try:
        if pd.isna(val):
            return None
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> Optional[float]:
    try:
        if pd.isna(val):
            return None
        return float(val)
    except (ValueError, TypeError):
        return None


def _normalise_url(url: str) -> str:
    return url.rstrip("/").replace("http://", "https://")


def parse_screaming_frog_csv(df: pd.DataFrame) -> dict[str, SFPageData]:
    """Parse a Screaming Frog internal_html.csv export into a URL-keyed dict.

    Returns a dict mapping normalised URL → SFPageData.
    Missing columns are silently skipped; their fields default to empty/None.
    Raises ValueError if the Address column cannot be found.
    """
    columns_lower = {c.strip().lower(): c for c in df.columns}

    col_refs: dict[str, str] = {}
    for field_key, candidates in SF_COLUMN_MAP.items():
        for candidate in candidates:
            if candidate.lower() in columns_lower:
                col_refs[field_key] = columns_lower[candidate.lower()]
                break

    if "url" not in col_refs:
        raise ValueError(
            "No 'Address' column found. "
            "Make sure this is a Screaming Frog internal_html.csv export."
        )

    result: dict[str, SFPageData] = {}

    for _, row in df.iterrows():
        raw_url = _safe_str(row[col_refs["url"]])
        if not raw_url:
            continue

        page = SFPageData(
            url=raw_url,
            seo_title=_safe_str(row[col_refs["seo_title"]]) if col_refs.get("seo_title") else "",
            title_length=_safe_int(row[col_refs["title_length"]]) if col_refs.get("title_length") else None,
            title_2=_safe_str(row[col_refs["title_2"]]) if col_refs.get("title_2") else "",
            meta_description=_safe_str(row[col_refs["meta_description"]]) if col_refs.get("meta_description") else "",
            meta_description_length=_safe_int(row[col_refs["meta_description_length"]]) if col_refs.get("meta_description_length") else None,
            h1=_safe_str(row[col_refs["h1"]]) if col_refs.get("h1") else "",
            h1_length=_safe_int(row[col_refs["h1_length"]]) if col_refs.get("h1_length") else None,
            h1_2=_safe_str(row[col_refs["h1_2"]]) if col_refs.get("h1_2") else "",
            word_count=_safe_int(row[col_refs["word_count"]]) if col_refs.get("word_count") else None,
            status_code=_safe_int(row[col_refs["status_code"]]) if col_refs.get("status_code") else None,
            indexability=_safe_str(row[col_refs["indexability"]]) if col_refs.get("indexability") else "",
            inlinks=_safe_int(row[col_refs["inlinks"]]) if col_refs.get("inlinks") else None,
            crawl_depth=_safe_int(row[col_refs["crawl_depth"]]) if col_refs.get("crawl_depth") else None,
            response_time=_safe_float(row[col_refs["response_time"]]) if col_refs.get("response_time") else None,
        )

        result[_normalise_url(raw_url)] = page

    return result


def derive_optimization_score(page: SFPageData) -> int:
    """Derive the current_optimization priority score (1-3) from SF data.

    Mirrors score_current_optimization() in priority_scorer.py:
        3 = nothing optimized (high opportunity)
        2 = partially optimized
        1 = well optimized

    title_optimized = has title AND length is 50-60 chars
    has_meta        = meta description is non-empty
    has_description = word count > 30 (proxy; could be product grid, not a
                      collection description — the full audit catches the
                      distinction via the description_exists check)
    """
    title_optimized = bool(page.seo_title) and (
        page.title_length is not None and 50 <= page.title_length <= 60
    )
    has_meta = bool(page.meta_description)
    has_description = (page.word_count or 0) > 30

    optimized_count = sum([title_optimized, has_meta, has_description])
    if optimized_count == 0:
        return 3
    elif optimized_count <= 1:
        return 2
    return 1


def derive_nav_link_signal(page: SFPageData) -> Optional[int]:
    """Suggest a homepage_nav_link score from inlinks and crawl depth.

    Returns None if data is insufficient or inconclusive — score not overridden.
    Returns 3 for high inlinks (>=5) AND shallow depth (<=2).
    Returns 1 for low inlinks (<3) OR deep depth (>=4).
    """
    inlinks = page.inlinks
    depth = page.crawl_depth

    if inlinks is None or depth is None:
        return None
    if inlinks >= 5 and depth <= 2:
        return 3
    if inlinks < 3 or depth >= 4:
        return 1
    return None


def derive_audit_flags(page: SFPageData) -> list[AuditFlag]:
    """Derive pre-flight audit flags from SF crawl data."""
    flags: list[AuditFlag] = []

    if page.status_code is not None and page.status_code != 200:
        flags.append(AuditFlag(
            flag_id="bad_status",
            severity="error",
            message=f"Page returns HTTP {page.status_code} — may not be indexable",
        ))

    if page.indexability.lower() == "non-indexable":
        flags.append(AuditFlag(
            flag_id="non_indexable",
            severity="error",
            message="Page is marked Non-Indexable — check robots/noindex directives",
        ))

    if page.status_code == 200 and not page.meta_description:
        flags.append(AuditFlag(
            flag_id="missing_meta",
            severity="error",
            message="No meta description — high impact, low effort fix",
        ))

    if page.meta_description_length and page.meta_description_length > 155:
        flags.append(AuditFlag(
            flag_id="meta_too_long",
            severity="warning",
            message=f"Meta description is {page.meta_description_length} chars (max 155)",
        ))

    if page.seo_title and page.title_length is not None:
        if not (50 <= page.title_length <= 60):
            flags.append(AuditFlag(
                flag_id="title_length",
                severity="warning",
                message=f"Title is {page.title_length} chars (target 50-60)",
            ))

    if page.h1_2:
        flags.append(AuditFlag(
            flag_id="duplicate_h1",
            severity="warning",
            message=f'Duplicate H1 found: "{page.h1_2}"',
        ))

    if page.title_2:
        flags.append(AuditFlag(
            flag_id="duplicate_title",
            severity="warning",
            message=f'Duplicate title tag found: "{page.title_2}"',
        ))

    return flags
