"""AI-assisted diagnosis for unrecognised keyword data files.

Used as a fallback when the rule-based format detector returns "custom" with
no clear column mapping, OR when an XLSX has the header row buried below
empty/title rows. Calls Haiku via Bifrost to inspect the raw sheet preview
and propose either:
  - a header_row (0-indexed) to re-read the file from
  - a column-name → internal-field mapping
  - or both

The output is a structured suggestion dict. Callers decide whether to
auto-apply, surface for confirmation, or ignore. No data leaves the user's
sheet beyond the first ~20 rows of headers/values that get sent in the prompt.
"""

from __future__ import annotations

import json
from typing import Optional

import pandas as pd
from openai import OpenAI


# Internal fields the app understands. Any subset can appear in a mapping.
_INTERNAL_FIELDS = [
    "keyword",          # Primary keyword (or single keyword column)
    "url",              # Collection URL / page
    "volume",           # Search volume for the primary keyword
    "difficulty",       # Keyword difficulty
    "rank",             # Current rank / position
    "clicks",           # Clicks
    "impressions",      # Impressions
    # Wide-format keyword columns (one row per collection)
    "keyword_1", "volume_1",
    "keyword_2", "volume_2",
    "keyword_3", "volume_3",
    "keyword_4", "volume_4",
]


_DIAGNOSIS_PROMPT = """You are a data analyst inspecting a spreadsheet that a user uploaded to an SEO tool. The tool needs to find:
- a keyword column (or multiple keyword columns in a wide-format sheet)
- a URL/page column
- search volume, keyword difficulty, current rank, clicks, impressions (any that exist)

The sheet may have empty rows or a title banner before the actual header row. Your job is to identify the correct header row and map its columns to the internal fields below.

INTERNAL FIELDS (use these exact names in your mapping):
- "keyword" — single keyword column (long format)
- "url" — collection URL or page
- "volume", "difficulty", "rank", "clicks", "impressions" — metrics
- For WIDE format (one row per URL with multiple keyword columns):
  "keyword_1", "volume_1", "keyword_2", "volume_2", "keyword_3", "volume_3", "keyword_4", "volume_4"

Use wide-format (keyword_1..keyword_4) ONLY when the sheet clearly has multiple keyword columns side-by-side (e.g. "Primary Keyword", "Secondary Keyword", "Tertiary Keyword"). Otherwise use the long-format fields.

SHEET PREVIEW (first 15 rows, 0-indexed):
{preview}

Respond with ONLY a JSON object — no prose, no code fences. Schema:
{{
  "header_row": <0-indexed integer of the row that contains column headers, or null if row 0 is correct>,
  "format": "<long or wide>",
  "mapping": {{
    "<exact column name from header row>": "<internal field name>",
    ...
  }},
  "confidence": "high" | "medium" | "low",
  "reasoning": "<one short sentence explaining what you saw>"
}}

If you cannot identify a header row or any usable columns, return:
{{"header_row": null, "format": "long", "mapping": {{}}, "confidence": "low", "reasoning": "<why>"}}"""


def build_sheet_preview(raw_df: pd.DataFrame, max_rows: int = 15, max_cols: int = 20) -> str:
    """Render the first N rows of a raw DataFrame as a row-indexed text preview.

    Row indices match pandas's `header=` parameter (0-indexed file rows), so a
    header found on "Row 6" of this preview should be passed back as
    `header_row=6` to `reread_with_header`.

    The trick: pandas's default read consumes file-row-0 as column names. We
    re-expose that consumed row as "Row 0" in the preview (using the column
    names themselves), then number the data rows starting at 1. When the
    columns are all 'Unnamed:' we know the real row 0 was blank, so we render
    a blank row 0 and number data rows from 1.

    Empty cells render as `_`. Empty rows are still shown so the LLM can see
    structural gaps (title banners, blank rows) before the real header.
    """
    cols = list(raw_df.columns)[:max_cols]
    has_real_headers = not all(
        isinstance(c, str) and c.startswith("Unnamed:") for c in cols
    )

    rows = raw_df.head(max_rows).fillna("").astype(str)
    rows = rows[cols]

    lines = []
    # Row 0 is always the row pandas consumed as column names
    if has_real_headers:
        header_cells = [str(c) if not str(c).startswith("Unnamed:") else "_" for c in cols]
    else:
        header_cells = ["_"] * len(cols)
    lines.append("Row 0: " + " | ".join(header_cells))

    # Data rows are numbered starting at 1 to match file-row indexing
    for i, (_, row) in enumerate(rows.iterrows(), start=1):
        cells = []
        for v in row.tolist():
            v = v.strip() if isinstance(v, str) else str(v)
            cells.append(v if v else "_")
        lines.append(f"Row {i}: " + " | ".join(cells))
    return "\n".join(lines)


def diagnose_file(
    api_key: str,
    raw_df: pd.DataFrame,
    model: str = "anthropic/claude-haiku-4-5",
    base_url: str = "https://bifrost.pattern.com",
) -> dict:
    """Ask Haiku to diagnose a file's structure and propose a column mapping.

    Returns a dict with keys: header_row, format, mapping, confidence,
    reasoning, error (str, set when something failed). Always returns a dict
    — never raises — so callers can fall through cleanly.
    """
    if raw_df is None or raw_df.empty:
        return {
            "header_row": None,
            "format": "long",
            "mapping": {},
            "confidence": "low",
            "reasoning": "File is empty.",
            "error": "",
        }

    if not base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"

    preview = build_sheet_preview(raw_df)
    prompt = _DIAGNOSIS_PROMPT.format(preview=preview)

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            max_tokens=800,
            messages=[
                {"role": "system", "content": "You return strict JSON. No prose, no code fences."},
                {"role": "user", "content": prompt},
            ],
        )
        raw = (response.choices[0].message.content or "").strip()
    except Exception as e:
        return {
            "header_row": None,
            "format": "long",
            "mapping": {},
            "confidence": "low",
            "reasoning": "",
            "error": f"AI diagnosis call failed: {e}",
        }

    # Strip code fences if the model added them despite instructions
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "header_row": None,
            "format": "long",
            "mapping": {},
            "confidence": "low",
            "reasoning": "",
            "error": f"AI returned non-JSON: {raw[:200]}",
        }

    # Sanity-check shape and fields. Drop any mapping entries pointing to
    # unknown internal fields rather than letting them propagate.
    mapping = parsed.get("mapping") or {}
    clean_mapping = {
        k: v for k, v in mapping.items()
        if isinstance(k, str) and isinstance(v, str) and v in _INTERNAL_FIELDS
    }

    header_row = parsed.get("header_row")
    if isinstance(header_row, str):
        try:
            header_row = int(header_row)
        except ValueError:
            header_row = None

    return {
        "header_row": header_row,
        "format": parsed.get("format", "long"),
        "mapping": clean_mapping,
        "confidence": parsed.get("confidence", "low"),
        "reasoning": parsed.get("reasoning", ""),
        "error": "",
    }


def reread_with_header(uploaded_file, header_row: Optional[int]) -> pd.DataFrame:
    """Re-read an uploaded file using a specific header row (0-indexed).

    Pandas accepts header= as a 0-indexed row number. None means the existing
    parse was already correct. Always seeks the file back to start.
    """
    uploaded_file.seek(0)
    name = uploaded_file.name.lower()
    if header_row is None or header_row == 0:
        if name.endswith((".xlsx", ".xls")):
            return pd.read_excel(uploaded_file)
        return pd.read_csv(uploaded_file)

    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file, header=header_row)
    return pd.read_csv(uploaded_file, header=header_row)


def apply_long_mapping(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """Apply a long-format column mapping and return a normalized DataFrame.

    `mapping` is {source_column: internal_field}. Output columns use internal
    field names. Numeric fields are coerced; URLs/keywords are stripped strings.
    """
    out = pd.DataFrame()
    for src_col, internal in mapping.items():
        if src_col not in df.columns:
            continue
        if internal in ("volume", "difficulty", "rank", "clicks", "impressions"):
            out[_alias_for(internal)] = pd.to_numeric(
                df[src_col].astype(str).str.replace("%", ""), errors="coerce"
            )
        elif internal == "keyword":
            out["keyword"] = df[src_col].astype(str).str.strip()
        elif internal == "url":
            out["collection_url"] = df[src_col].astype(str).str.strip()
    return out


def apply_wide_mapping(df: pd.DataFrame, mapping: dict) -> tuple[list, list]:
    """Apply a wide-format mapping and return (CollectionGroup list, skipped list).

    Reuses the same shape that `normalize_keyword_map` produces so callers can
    drop the result straight into `st.session_state.collection_groups`.
    """
    from core.data_ingestion import CollectionGroup, SkippedCollection, _extract_collection_name, clean_keyword

    inv = {v: k for k, v in mapping.items()}  # internal -> source col
    url_col = inv.get("url")
    pairs = []
    for i in range(1, 5):
        kw = inv.get(f"keyword_{i}")
        vol = inv.get(f"volume_{i}")
        if kw and kw in df.columns:
            pairs.append((kw, vol if vol in df.columns else None))

    if not url_col or not pairs:
        return [], []

    groups: list = []
    skipped: list = []
    for _, row in df.iterrows():
        url_val = row.get(url_col)
        if pd.isna(url_val):
            continue
        url = str(url_val).strip()
        if not url or url.lower() == "nan":
            continue

        keywords = []
        for kw_col, vol_col in pairs:
            raw = row.get(kw_col)
            if pd.isna(raw) or str(raw).strip() == "":
                continue
            text = clean_keyword(str(raw).strip())
            if not text:
                continue
            volume = 0
            if vol_col is not None:
                rv = row.get(vol_col)
                if pd.notna(rv):
                    try:
                        volume = int(float(str(rv)))
                    except (ValueError, TypeError):
                        volume = 0
            keywords.append({"keyword": text, "search_volume": volume})

        if not keywords:
            skipped.append(SkippedCollection(collection_url=url, reason="no_keywords"))
            continue

        total = sum(k["search_volume"] for k in keywords)
        if total == 0:
            skipped.append(SkippedCollection(collection_url=url, reason="zero_volume"))

        primary = keywords[0]
        secondary = []
        for kw in keywords[1:]:
            entry: dict = {"keyword": kw["keyword"]}
            if kw["search_volume"]:
                entry["search_volume"] = kw["search_volume"]
            secondary.append(entry)

        groups.append(CollectionGroup(
            collection_url=url,
            collection_name=_extract_collection_name(url) if "/collections/" in url.lower() else url,
            primary_keyword=primary["keyword"],
            primary_keyword_volume=primary["search_volume"] or None,
            secondary_keywords=secondary,
            total_volume=total,
            best_rank=None,
            total_clicks=None,
            total_impressions=None,
        ))

    groups.sort(key=lambda g: g.total_volume, reverse=True)
    return groups, skipped


def _alias_for(internal: str) -> str:
    """Map internal field name to the column name the rest of the app expects."""
    return {
        "volume": "search_volume",
        "difficulty": "keyword_difficulty",
        "rank": "current_rank",
    }.get(internal, internal)
