"""CSV parsers, format detection, and normalization for keyword data ingestion."""

import io
import json
import re
import unicodedata
from pathlib import Path
from typing import Optional

import pandas as pd
from pydantic import BaseModel, Field


def clean_keyword(text: str) -> str:
    """Strip unicode format characters and normalise whitespace.

    Removes zero-width spaces (U+200B), BOM (U+FEFF), soft hyphens,
    and all other characters in unicode category 'Cf'.
    """
    if not text:
        return text
    cleaned = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return " ".join(cleaned.split())


class KeywordRecord(BaseModel):
    """Internal schema for a keyword-collection pair."""

    collection_url: str
    collection_name: str
    primary_keyword: str
    secondary_keywords: list[str] = Field(default_factory=list)
    current_rank: Optional[int] = None
    search_volume: Optional[int] = None
    keyword_difficulty: Optional[float] = None
    clicks: Optional[int] = None
    impressions: Optional[int] = None


class CollectionGroup(BaseModel):
    """A collection with its grouped keywords."""

    collection_url: str
    collection_name: str
    primary_keyword: str
    primary_keyword_volume: Optional[int] = None
    secondary_keywords: list[dict] = Field(default_factory=list)
    total_volume: int = 0
    best_rank: Optional[int] = None
    total_clicks: Optional[int] = None
    total_impressions: Optional[int] = None


class SkippedCollection(BaseModel):
    """A collection row excluded or flagged during ingestion."""

    collection_url: str
    reason: str  # "no_keywords" | "zero_volume"


def load_format_mappings() -> dict:
    """Load column mapping configuration."""
    config_path = Path(__file__).parent.parent / "config" / "format_mappings.json"
    with open(config_path) as f:
        return json.load(f)


def detect_format(df: pd.DataFrame) -> str:
    """Auto-detect the source format by checking column headers."""
    mappings = load_format_mappings()
    columns = [c.strip() for c in df.columns.tolist()]
    columns_lower = [c.lower() for c in columns]

    # Explicit early check for keyword_map (wide-format XLSX with per-column keywords)
    if any(c == "target keyword 1" for c in columns_lower):
        return "keyword_map"

    for format_key, format_config in mappings["formats"].items():
        if format_key in ("custom", "keyword_map"):
            continue
        detection_cols = format_config["detection_columns"]
        if detection_cols and all(
            any(d.lower() == c for c in columns_lower) for d in detection_cols
        ):
            return format_key
        alt_cols = format_config.get("alternative_detection", [])
        if alt_cols and all(
            any(a.lower() == c for c in columns_lower) for a in alt_cols
        ):
            return format_key

    return "custom"


def _find_column(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """Find a matching column from a list of candidates (case-insensitive)."""
    columns_lower = {c.lower(): c for c in df.columns}
    for candidate in candidates:
        if candidate.lower() in columns_lower:
            return columns_lower[candidate.lower()]
    return None


def _extract_collection_name(url: str) -> str:
    """Extract a human-readable collection name from a URL."""
    match = re.search(r"/collections/([^/?#]+)", url)
    if match:
        handle = match.group(1)
        return handle.replace("-", " ").replace("_", " ").title()
    parts = url.rstrip("/").split("/")
    return parts[-1].replace("-", " ").replace("_", " ").title() if parts else url


def normalize_dataframe(df: pd.DataFrame, source_format: str) -> pd.DataFrame:
    """Normalize a DataFrame from any supported format to the internal schema."""
    mappings = load_format_mappings()
    format_config = mappings["formats"].get(source_format, mappings["formats"]["custom"])
    col_map = format_config["column_mapping"]

    normalized = pd.DataFrame()

    keyword_col = _find_column(df, col_map.get("keyword", []))
    url_col = _find_column(df, col_map.get("url", []) + col_map.get("page", []))
    volume_col = _find_column(df, col_map.get("volume", []))
    difficulty_col = _find_column(df, col_map.get("difficulty", []))
    rank_col = _find_column(df, col_map.get("rank", []))
    clicks_col = _find_column(df, col_map.get("clicks", []))
    impressions_col = _find_column(df, col_map.get("impressions", []))

    if keyword_col:
        normalized["keyword"] = (
            df[keyword_col].astype(str).str.strip().apply(clean_keyword)
        )
    if url_col:
        normalized["collection_url"] = df[url_col].astype(str).str.strip()
    if volume_col:
        normalized["search_volume"] = pd.to_numeric(df[volume_col], errors="coerce")
    if difficulty_col:
        normalized["keyword_difficulty"] = pd.to_numeric(
            df[difficulty_col].astype(str).str.replace("%", ""), errors="coerce"
        )
    if rank_col:
        normalized["current_rank"] = pd.to_numeric(df[rank_col], errors="coerce")
    if clicks_col:
        normalized["clicks"] = pd.to_numeric(df[clicks_col], errors="coerce")
    if impressions_col:
        normalized["impressions"] = pd.to_numeric(df[impressions_col], errors="coerce")

    # Filter to collection URLs if possible
    if "collection_url" in normalized.columns:
        collection_mask = normalized["collection_url"].str.contains(
            "/collections/", case=False, na=False
        )
        if collection_mask.any():
            normalized = normalized[collection_mask].copy()

    return normalized


def normalize_keyword_map(
    df: pd.DataFrame,
) -> tuple[list[CollectionGroup], list[SkippedCollection]]:
    """Normalize a wide-format keyword mapping XLSX into CollectionGroup objects.

    Each row is one collection; keywords are spread horizontally across up to
    four keyword+volume column pairs.  Keyword 1 is primary; 2-N are secondary.

    Rows with all keyword columns null/empty produce a SkippedCollection with
    reason='no_keywords'.  Rows where total_volume == 0 produce a
    SkippedCollection with reason='zero_volume' AND still appear in groups.
    """
    mappings = load_format_mappings()
    col_map = mappings["formats"]["keyword_map"]["column_mapping"]

    url_col = _find_column(df, col_map["url"])

    # The canonical keyword/volume column pairs in order
    present_pairs: list[tuple[str, Optional[str]]] = []
    for i in range(1, 5):
        kw_col = _find_column(df, col_map[f"keyword_{i}"])
        vol_col = _find_column(df, col_map[f"volume_{i}"])
        if kw_col is not None:
            present_pairs.append((kw_col, vol_col))

    if not url_col or not present_pairs:
        return [], []

    groups: list[CollectionGroup] = []
    skipped: list[SkippedCollection] = []

    for _, row in df.iterrows():
        url_val = row.get(url_col)
        if pd.isna(url_val):
            continue
        url = str(url_val).strip()
        if "/collections/" not in url.lower():
            continue

        # Detect whether all keyword columns are null/empty
        all_null = all(
            pd.isna(row.get(kw_col)) or str(row.get(kw_col, "")).strip() == ""
            for kw_col, _ in present_pairs
        )
        if all_null:
            skipped.append(SkippedCollection(collection_url=url, reason="no_keywords"))
            continue

        # Collect non-empty keywords with cleaned text and integer volumes
        keywords: list[dict] = []
        for kw_col, vol_col in present_pairs:
            raw_kw = row.get(kw_col)
            if pd.isna(raw_kw) or str(raw_kw).strip() == "":
                continue
            kw_text = clean_keyword(str(raw_kw).strip())
            if not kw_text:
                continue
            vol = 0
            if vol_col is not None:
                raw_vol = row.get(vol_col)
                if pd.notna(raw_vol):
                    try:
                        vol = int(float(str(raw_vol)))
                    except (ValueError, TypeError):
                        vol = 0
            keywords.append({"keyword": kw_text, "search_volume": vol})

        if not keywords:
            skipped.append(SkippedCollection(collection_url=url, reason="no_keywords"))
            continue

        total_volume = sum(kw["search_volume"] for kw in keywords)

        if total_volume == 0:
            skipped.append(SkippedCollection(collection_url=url, reason="zero_volume"))

        primary = keywords[0]
        secondary: list[dict] = []
        for kw in keywords[1:]:
            kw_data: dict = {"keyword": kw["keyword"]}
            if kw["search_volume"] != 0:
                kw_data["search_volume"] = kw["search_volume"]
            secondary.append(kw_data)

        groups.append(
            CollectionGroup(
                collection_url=url,
                collection_name=_extract_collection_name(url),
                primary_keyword=primary["keyword"],
                primary_keyword_volume=primary["search_volume"] or None,
                secondary_keywords=secondary,
                total_volume=total_volume,
                best_rank=None,
                total_clicks=None,
                total_impressions=None,
            )
        )

    groups.sort(key=lambda g: g.total_volume, reverse=True)
    return groups, skipped


def group_by_collection(df: pd.DataFrame) -> list[CollectionGroup]:
    """Group keywords by collection URL and create CollectionGroup objects."""
    if "collection_url" not in df.columns or "keyword" not in df.columns:
        return []

    groups = []
    for url, group_df in df.groupby("collection_url"):
        sort_col = "search_volume" if "search_volume" in group_df.columns else "clicks" if "clicks" in group_df.columns else None
        if sort_col:
            group_df = group_df.sort_values(
                sort_col, ascending=False, na_position="last"
            )

        primary_row = group_df.iloc[0]
        primary_keyword = primary_row["keyword"]
        primary_volume = (
            int(primary_row["search_volume"])
            if pd.notna(primary_row.get("search_volume"))
            else None
        )

        secondary = []
        for _, row in group_df.iloc[1:].iterrows():
            kw_data = {"keyword": row["keyword"]}
            if pd.notna(row.get("search_volume")):
                kw_data["search_volume"] = int(row["search_volume"])
            if pd.notna(row.get("current_rank")):
                kw_data["current_rank"] = int(row["current_rank"])
            if pd.notna(row.get("keyword_difficulty")):
                kw_data["keyword_difficulty"] = float(row["keyword_difficulty"])
            secondary.append(kw_data)

        total_volume = int(group_df["search_volume"].sum()) if "search_volume" in group_df.columns and group_df["search_volume"].notna().any() else 0
        best_rank = (
            int(group_df["current_rank"].min())
            if "current_rank" in group_df and group_df["current_rank"].notna().any()
            else None
        )
        total_clicks = (
            int(group_df["clicks"].sum())
            if "clicks" in group_df and group_df["clicks"].notna().any()
            else None
        )
        total_impressions = (
            int(group_df["impressions"].sum())
            if "impressions" in group_df and group_df["impressions"].notna().any()
            else None
        )

        collection = CollectionGroup(
            collection_url=str(url),
            collection_name=_extract_collection_name(str(url)),
            primary_keyword=primary_keyword,
            primary_keyword_volume=primary_volume,
            secondary_keywords=secondary,
            total_volume=total_volume,
            best_rank=best_rank,
            total_clicks=total_clicks,
            total_impressions=total_impressions,
        )
        groups.append(collection)

    groups.sort(key=lambda g: g.total_volume, reverse=True)
    return groups


def read_upload(uploaded_file) -> pd.DataFrame:
    """Read an uploaded file (CSV or XLSX) into a DataFrame."""
    filename = uploaded_file.name.lower()
    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        return pd.read_excel(uploaded_file)
    elif filename.endswith(".csv"):
        content = uploaded_file.read()
        uploaded_file.seek(0)
        try:
            return pd.read_csv(io.BytesIO(content))
        except Exception:
            return pd.read_csv(io.BytesIO(content), encoding="latin-1")
    else:
        raise ValueError(f"Unsupported file format: {filename}. Use CSV or XLSX.")


def ingest_file(
    uploaded_file,
) -> tuple[pd.DataFrame, str, list[CollectionGroup], list[SkippedCollection]]:
    """Full ingestion pipeline: read, detect format, normalize, group."""
    raw_df = read_upload(uploaded_file)
    source_format = detect_format(raw_df)
    if source_format == "keyword_map":
        groups, skipped = normalize_keyword_map(raw_df)
        return pd.DataFrame(), source_format, groups, skipped
    normalized_df = normalize_dataframe(raw_df, source_format)
    groups = group_by_collection(normalized_df)
    return normalized_df, source_format, groups, []
