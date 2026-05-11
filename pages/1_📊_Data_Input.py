"""Step 1: Project Setup & Data Input.

When auto-detection or column auto-mapping is incomplete, an "AI diagnosis"
fallback inspects the file with Haiku and proposes the correct header row +
column mapping. The user can review and apply with one click.
"""

import streamlit as st
import pandas as pd

from core.app_state import get_state, save_state


st.title("Step 1: Data Input")

state = get_state()

# --- 1.1 Brand Profile status banner ---
cp = state.client_profile
if not cp.brand_name:
    st.warning("⚠️ No brand profile loaded.")
    st.page_link("pages/0_🏷️_Brand_Profile.py", label="→ Set up brand profile", icon="🏷️")
    st.stop()
else:
    st.success(f"Active brand: **{cp.brand_name}** · {len(cp.brand_usps or [])} USPs")
    st.page_link("pages/0_🏷️_Brand_Profile.py", label="Edit brand profile", icon="🏷️")

# Sitemap status — surfaces whether smart link suggestions are active.
_sitemap_dict = state.sitemap_parsed or None
if _sitemap_dict:
    from core.sitemap import ParsedSitemap as _PS

    try:
        _sm = _PS.from_dict(_sitemap_dict)
        st.info(
            f"📍 Site structure: {_sm.total_urls:,} URLs from sitemap — "
            f"smart link suggestions active."
        )
    except Exception:
        st.caption("📍 Site structure: sitemap data unreadable.")
else:
    st.caption(
        "📍 Site structure: No sitemap loaded — link suggestions limited to user-provided URLs."
    )

# Profile is loaded by this point — gate already passed via st.stop() above.
profile_valid = True

st.markdown("---")

# --- 1.2 Data Input ---
st.markdown("## Keyword Data Upload")
st.markdown(
    "Upload a CSV or XLSX export from Google Search Console, Ahrefs, SEMrush, or a custom keyword map."
)

uploaded_file = st.file_uploader(
    "Upload keyword data",
    type=["csv", "xlsx", "xls"],
    help="Accepted formats: GSC queries+pages, Ahrefs organic keywords, SEMrush organic research, custom format",
)

from core.data_ingestion import load_sample_template as _load_template

st.caption("Don't have keyword data yet? Grab a sample to test the pipeline:")
template_col1, template_col2, template_col3, _ = st.columns([1, 1, 1, 2])
with template_col1:
    st.download_button(
        "📄 GSC Sample",
        data=_load_template("gsc"),
        file_name="sample_gsc.csv",
        mime="text/csv",
        help="Google Search Console export format",
    )
with template_col2:
    st.download_button(
        "📄 Ahrefs Sample",
        data=_load_template("ahrefs"),
        file_name="sample_ahrefs.csv",
        mime="text/csv",
        help="Ahrefs organic keywords export format",
    )
with template_col3:
    st.download_button(
        "📄 Keyword Map",
        data=_load_template("keyword_map"),
        file_name="sample_keyword_map.csv",
        mime="text/csv",
        help="Wide-format mapping template with up to 4 keywords per URL",
    )

if uploaded_file is None:
    with st.container(border=True):
        st.markdown("### 📥 Don't have keyword data yet?")
        st.markdown(
            "- **Google Search Console**: Search Results → Export → Filter to your store domain\n"
            "- **Ahrefs**: Site Explorer → Organic keywords → Export\n"
            "- **SEMrush**: Organic Research → Positions → Export\n"
            "- **Custom**: Any CSV with `keyword` + `url` columns (volume, rank, difficulty optional)"
        )
        st.caption("Or use the sample templates above to test the pipeline.")

_FORMAT_LABELS = {
    "gsc": "Google Search Console",
    "ahrefs": "Ahrefs",
    "semrush": "SEMrush",
    "keyword_map": "Keyword Mapping Document",
    "custom": "Custom Format",
}


def _detection_quality(source_format: str, raw_df: pd.DataFrame) -> str:
    """Return 'good' if rule-based detection found a real format,
    'weak' if it fell through to custom and the columns look unusable
    (mostly Unnamed:, suggesting a header buried below blank rows or a
    non-standard layout)."""
    if source_format != "custom":
        return "good"
    cols = list(raw_df.columns)
    unnamed_ratio = sum(
        1 for c in cols if isinstance(c, str) and c.startswith("Unnamed:")
    ) / max(len(cols), 1)
    if unnamed_ratio > 0.5:
        return "weak"
    # Check whether any standard column candidate exists
    from core.data_ingestion import load_format_mappings
    mappings = load_format_mappings()
    custom_map = mappings["formats"]["custom"]["column_mapping"]
    cols_lower = {c.lower() for c in cols if isinstance(c, str)}
    if any(any(cand.lower() in cols_lower for cand in cands) for cands in custom_map.values()):
        return "good"
    return "weak"


if uploaded_file is not None:
    from core.data_ingestion import (
        detect_format,
        read_upload,
        normalize_dataframe,
        group_by_collection,
        normalize_keyword_map,
        load_format_mappings,
        _find_column,
    )

    try:
        raw_df = read_upload(uploaded_file)
        source_format = detect_format(raw_df)
        format_label = _FORMAT_LABELS.get(source_format, source_format.upper())
        quality = _detection_quality(source_format, raw_df)

        st.success(f"Detected format: **{format_label}** ({len(raw_df)} rows)")

        # Show raw preview
        with st.expander("Raw Data Preview"):
            st.dataframe(raw_df.head(20))

        # ───────────────────────────────────────────────────────────────────
        # AI-assisted diagnosis (offered when detection is weak)
        # ───────────────────────────────────────────────────────────────────
        if quality == "weak":
            st.warning(
                "Couldn't recognise this file's structure automatically. "
                "Most columns have generic names like `Unnamed: 0`, which usually means "
                "the header row is buried below blank rows or a title banner."
            )
            api_key = state.bifrost_api_key

            adc1, adc2 = st.columns([1, 4])
            with adc1:
                ai_clicked = st.button(
                    "🤖 Ask AI to diagnose",
                    type="primary",
                    disabled=not api_key,
                    help="Sends the first 15 rows to Haiku and asks it to identify the header row and column mapping.",
                )
            with adc2:
                if not api_key:
                    st.caption("Set the Bifrost API key in the sidebar to enable AI diagnosis.")
                else:
                    st.caption("Uses Haiku (fast, low-cost). Only the first 15 rows are sent.")

            if ai_clicked:
                from core.file_diagnoser import diagnose_file
                with st.spinner("Inspecting file structure..."):
                    diagnosis = diagnose_file(
                        api_key=api_key,
                        raw_df=raw_df,
                        base_url=state.bifrost_base_url or "https://bifrost.pattern.com",
                    )
                st.session_state["_ai_diagnosis"] = diagnosis
                st.rerun()

            diagnosis = st.session_state.get("_ai_diagnosis")
            if diagnosis:
                if diagnosis.get("error"):
                    st.error(f"AI diagnosis failed: {diagnosis['error']}")
                elif not diagnosis.get("mapping"):
                    st.error(
                        f"AI couldn't identify a usable structure. "
                        f"Reason: {diagnosis.get('reasoning', 'no details')}"
                    )
                else:
                    confidence = diagnosis.get("confidence", "low")
                    badge = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(confidence, "")
                    st.info(
                        f"**AI diagnosis** {badge} confidence: {confidence}\n\n"
                        f"_{diagnosis.get('reasoning', '')}_"
                    )
                    st.markdown("**Proposed column mapping:**")
                    mapping_rows = [
                        {"Source column": k, "Maps to": v}
                        for k, v in diagnosis["mapping"].items()
                    ]
                    st.dataframe(pd.DataFrame(mapping_rows), width="stretch", hide_index=True)
                    if diagnosis.get("header_row") is not None:
                        st.caption(f"Header row identified: Row {diagnosis['header_row']}")

                    apply_col1, apply_col2 = st.columns([1, 4])
                    with apply_col1:
                        apply_clicked = st.button(
                            "✅ Apply AI mapping",
                            type="primary",
                            help="Re-read the file using the AI's suggested header row and column mapping.",
                        )
                    if apply_clicked:
                        from core.file_diagnoser import (
                            reread_with_header,
                            apply_wide_mapping,
                            apply_long_mapping,
                        )
                        try:
                            df = reread_with_header(uploaded_file, diagnosis.get("header_row"))
                        except Exception as e:
                            st.error(f"Couldn't re-read file: {e}")
                            df = None

                        if df is not None:
                            if diagnosis.get("format") == "wide":
                                groups, skipped, info = apply_wide_mapping(df, diagnosis["mapping"])
                                if groups:
                                    state.normalized_data = pd.DataFrame()
                                    state.source_format = "keyword_map"  # treat as wide
                                    state.collection_groups = groups
                                    state.skipped_collections = skipped
                                    state.raw_data = raw_df
                                    st.success(
                                        f"Applied AI mapping. Loaded **{len(groups)} collections** "
                                        f"({len(skipped)} skipped)."
                                    )
                                    if info["placeholder_urls"]:
                                        st.warning(
                                            f"⚠️ {info['placeholder_urls']} of {len(groups)} collections "
                                            f"are using **placeholder URLs** generated from category/keyword names "
                                            f"(your file's URL column is empty). The pipeline will work for "
                                            f"keyword scoring and content drafting, but the Shopify scraper "
                                            f"won't find products until you fill in real URLs."
                                        )
                                    st.session_state.pop("_ai_diagnosis", None)
                                    save_state(state)
                                    st.rerun()
                                else:
                                    st.error(
                                        "AI mapping produced no usable rows. "
                                        "The URL/name columns may be wrong — try editing the mapping or "
                                        "manually entering URLs in the next step."
                                    )
                            else:
                                normalized = apply_long_mapping(df, diagnosis["mapping"])
                                if "collection_url" in normalized.columns:
                                    mask = normalized["collection_url"].str.contains(
                                        "/collections/", case=False, na=False
                                    )
                                    if mask.any():
                                        normalized = normalized[mask].copy()
                                groups = group_by_collection(normalized)
                                state.normalized_data = normalized
                                state.source_format = "custom"
                                state.collection_groups = groups
                                state.skipped_collections = []
                                state.raw_data = raw_df
                                st.success(
                                    f"Applied AI mapping. Loaded **{len(groups)} collections** "
                                    f"from {len(normalized)} keyword rows."
                                )
                                st.session_state.pop("_ai_diagnosis", None)
                                save_state(state)
                                st.rerun()

            st.markdown("---")
            st.caption(
                "If you'd rather configure the columns manually, use the dropdowns below."
            )

        if source_format == "keyword_map":
            # --- Keyword Mapping format: fully auto-handled, no dropdowns ---
            st.markdown("### Keyword Mapping Document — Auto Configuration")
            st.info(
                "Column mapping is automatic for this format. "
                "Keywords 1–4 and their volumes have been detected. "
                "Click **Process Data** to load all collections."
            )

            if st.button("Process Data", type="primary", disabled=not profile_valid):
                with st.spinner(f"Processing {len(raw_df)} rows…"):
                    groups, skipped = normalize_keyword_map(raw_df)
                    # Record the input's keyword column width so the
                    # round-trip exporter mirrors the source schema.
                    state.source_keyword_width = (
                        max(len(g.secondary_keywords) + 1 for g in groups) if groups else 4
                    )

                no_kw_count = sum(1 for s in skipped if s.reason == "no_keywords")
                zero_vol_count = sum(1 for s in skipped if s.reason == "zero_volume")

                state.normalized_data = pd.DataFrame()
                state.source_format = source_format
                state.collection_groups = groups
                state.skipped_collections = skipped
                state.raw_data = raw_df
                save_state(state)

                st.success(
                    f"Loaded **{len(groups)} collections**. "
                    + (f"**{no_kw_count}** skipped (no keywords). " if no_kw_count else "")
                    + (f"**{zero_vol_count}** flagged (zero volume)." if zero_vol_count else "")
                )

                if skipped:
                    with st.expander(f"Skipped / Flagged Collections ({len(skipped)})"):
                        for s in skipped:
                            label = {
                                "no_keywords": "⛔ No keywords",
                                "zero_volume": "⚠️ Zero volume",
                            }
                            st.caption(
                                f"{label.get(s.reason, s.reason)} — {s.collection_url}"
                            )

        else:
            # --- Standard formats: show column mapping dropdowns ---
            st.markdown("### Column Mapping")
            st.markdown(
                "Confirm or override the auto-detected column assignments:"
            )

            mappings = load_format_mappings()
            format_config = mappings["formats"].get(source_format, mappings["formats"]["custom"])
            col_map = format_config["column_mapping"]

            available_cols = ["(none)"] + list(raw_df.columns)

            mc1, mc2, mc3 = st.columns(3)

            with mc1:
                kw_default = _find_column(raw_df, col_map.get("keyword", []))
                keyword_col = st.selectbox(
                    "Keyword column",
                    available_cols,
                    index=available_cols.index(kw_default) if kw_default in available_cols else 0,
                )

                url_candidates = col_map.get("url", []) + col_map.get("page", [])
                url_default = _find_column(raw_df, url_candidates)
                url_col = st.selectbox(
                    "URL / Page column",
                    available_cols,
                    index=available_cols.index(url_default) if url_default in available_cols else 0,
                )

            with mc2:
                vol_default = _find_column(raw_df, col_map.get("volume", []))
                volume_col = st.selectbox(
                    "Search Volume column",
                    available_cols,
                    index=available_cols.index(vol_default) if vol_default in available_cols else 0,
                )

                diff_default = _find_column(raw_df, col_map.get("difficulty", []))
                difficulty_col = st.selectbox(
                    "Keyword Difficulty column",
                    available_cols,
                    index=available_cols.index(diff_default) if diff_default in available_cols else 0,
                )

            with mc3:
                rank_default = _find_column(raw_df, col_map.get("rank", []))
                rank_col = st.selectbox(
                    "Current Rank column",
                    available_cols,
                    index=available_cols.index(rank_default) if rank_default in available_cols else 0,
                )

                clicks_default = _find_column(raw_df, col_map.get("clicks", []))
                clicks_col = st.selectbox(
                    "Clicks column",
                    available_cols,
                    index=available_cols.index(clicks_default) if clicks_default in available_cols else 0,
                )

            if st.button("Process Data", type="primary", disabled=not profile_valid):
                with st.spinner(f"Processing {len(raw_df)} rows…"):
                    normalized = pd.DataFrame()

                    if keyword_col != "(none)":
                        normalized["keyword"] = raw_df[keyword_col].astype(str).str.strip()
                    if url_col != "(none)":
                        normalized["collection_url"] = raw_df[url_col].astype(str).str.strip()
                    if volume_col != "(none)":
                        normalized["search_volume"] = pd.to_numeric(raw_df[volume_col], errors="coerce")
                    if difficulty_col != "(none)":
                        normalized["keyword_difficulty"] = pd.to_numeric(
                            raw_df[difficulty_col].astype(str).str.replace("%", ""), errors="coerce"
                        )
                    if rank_col != "(none)":
                        normalized["current_rank"] = pd.to_numeric(raw_df[rank_col], errors="coerce")
                    if clicks_col != "(none)":
                        normalized["clicks"] = pd.to_numeric(raw_df[clicks_col], errors="coerce")

                    # Filter to collection URLs
                    if "collection_url" in normalized.columns:
                        mask = normalized["collection_url"].str.contains("/collections/", case=False, na=False)
                        if mask.any():
                            filtered_count = len(normalized) - mask.sum()
                            normalized = normalized[mask].copy()
                            if filtered_count > 0:
                                st.info(f"Filtered {filtered_count} non-collection URLs")

                    groups = group_by_collection(normalized)

                state.normalized_data = normalized
                state.source_format = source_format
                state.collection_groups = groups
                state.skipped_collections = []
                state.raw_data = raw_df
                save_state(state)

                st.success(f"Processed {len(normalized)} keywords into {len(groups)} collections")

    except Exception as e:
        st.error(f"Error processing file: {e}")

# --- 1.3 Keyword-to-Collection Grouping ---
if state.collection_groups:
    st.markdown("---")
    st.markdown("## Keyword-to-Collection Grouping")
    st.markdown(f"**{len(state.collection_groups)} collections** identified")

    # Keyword Mapping format: show summary preview table before expanders
    if state.source_format == "keyword_map":
        preview_rows = [
            {
                "Collection Name": g.collection_name,
                "Primary Keyword": g.primary_keyword,
                "Primary Volume": g.primary_keyword_volume or 0,
                "Secondary Keywords": len(g.secondary_keywords),
            }
            for g in state.collection_groups
        ]
        st.dataframe(pd.DataFrame(preview_rows), width="stretch")

    # Build set of zero-volume URLs for inline warnings
    zero_vol_urls = {
        s.collection_url
        for s in state.skipped_collections or []
        if s.reason == "zero_volume"
    }

    for i, group in enumerate(state.collection_groups):
        zero_vol_flag = " ⚠️ zero volume" if group.collection_url in zero_vol_urls else ""
        with st.expander(
            f"{group.collection_name} — {group.primary_keyword} "
            f"(Vol: {group.total_volume:,} | Keywords: {len(group.secondary_keywords) + 1})"
            f"{zero_vol_flag}"
        ):
            if group.collection_url in zero_vol_urls:
                st.warning(
                    "All keywords for this collection have zero search volume. "
                    "Included in scoring but may not be a priority."
                )

            gc1, gc2 = st.columns([2, 1])

            with gc1:
                st.text_input(
                    "Collection URL",
                    value=group.collection_url,
                    key=f"url_{i}",
                    disabled=True,
                )

                # Allow changing primary keyword
                all_keywords = [group.primary_keyword] + [
                    kw.get("keyword", "") for kw in group.secondary_keywords
                ]
                primary_idx = st.selectbox(
                    "Primary Keyword",
                    range(len(all_keywords)),
                    format_func=lambda x: (
                        f"{all_keywords[x]} "
                        f"(Vol: {group.secondary_keywords[x-1].get('search_volume', 'N/A') if x > 0 else group.primary_keyword_volume or 'N/A'})"
                    ),
                    key=f"primary_{i}",
                )

                if primary_idx != 0:
                    from core.text_utils import clean_keyword as _clean
                    new_primary = _clean(all_keywords[primary_idx])
                    state.collection_groups[i].primary_keyword = new_primary
                    save_state(state)

            with gc2:
                st.markdown("**Secondary Keywords:**")
                for kw in group.secondary_keywords[:10]:
                    vol = kw.get("search_volume", "")
                    rank = kw.get("current_rank", "")
                    st.caption(
                        f"• {kw['keyword']} "
                        f"{'(Vol: ' + str(vol) + ')' if vol else ''} "
                        f"{'[Rank: ' + str(rank) + ']' if rank else ''}"
                    )
                if len(group.secondary_keywords) > 10:
                    st.caption(f"... and {len(group.secondary_keywords) - 10} more")

    st.markdown("---")

    # --- Site Keyword Data ---
    st.markdown("### Site Keyword Data (optional)")
    st.markdown(
        "Upload a domain-wide keyword export from **SEMrush**, **Ahrefs**, or "
        "**Brightedge** to detect cannibalisation risks (multiple URLs ranking "
        "for the same keyword) and surface new keyword opportunities in the "
        "Content Studio."
    )

    _site_kw_file = st.file_uploader(
        "Domain keyword export (CSV / XLSX)",
        type=["csv", "xlsx", "xls"],
        key="site_kw_uploader",
        help=(
            "Expected columns: Keyword, URL (or Current URL / Landing Page), "
            "Search Volume, Position (or Current position / Rank). "
            "Traffic is optional."
        ),
    )

    _current_corpus_dict = state.site_keywords or None
    if _current_corpus_dict:
        from core.site_keywords import SiteKeywordCorpus as _SKC
        _existing = _SKC.from_dict(_current_corpus_dict)
        st.caption(
            f"✅ Loaded — {_existing.total_rows:,} rows · "
            f"{_existing.unique_keywords:,} unique keywords · "
            f"{_existing.unique_urls:,} unique URLs "
            f"({_existing.source_format})"
        )
        if st.button("Clear site keyword data", key="clear_site_kw"):
            state.site_keywords = {}
            state.site_cannibalisation = {}
            save_state(state)
            st.rerun()

    if _site_kw_file is not None:
        from core.data_ingestion import read_upload as _read_upload
        from core.site_keywords import (
            detect_site_format as _detect_site_format,
            parse_site_keywords as _parse_site_keywords,
            find_all_cannibalisation as _find_cannib,
            SiteKeywordCorpus as _SKC,
        )

        try:
            _raw_site_df = _read_upload(_site_kw_file)
        except Exception as e:
            st.error(f"Couldn't read site keyword file: {e}")
            _raw_site_df = None

        if _raw_site_df is not None:
            _detected_fmt = _detect_site_format(_raw_site_df)
            _vendor_label = {
                "semrush": "SEMrush",
                "ahrefs": "Ahrefs",
                "brightedge": "Brightedge",
                "custom": "Custom / unknown",
            }.get(_detected_fmt, _detected_fmt)
            st.info(f"Detected vendor: **{_vendor_label}** ({len(_raw_site_df)} rows)")

            with st.expander("Raw site keyword preview", expanded=False):
                st.dataframe(_raw_site_df.head(20), width="stretch")

            if st.button("Process site keyword data", type="secondary", key="process_site_kw"):
                with st.spinner(f"Parsing {len(_raw_site_df)} rows…"):
                    _corpus = _parse_site_keywords(_raw_site_df, source_format=_detected_fmt)
                if _corpus.error and _corpus.total_rows == 0:
                    st.error(f"Parse failed: {_corpus.error}")
                else:
                    if _corpus.error:
                        st.warning(_corpus.error)
                    # Detect cannibalisation conflicts up-front so other
                    # pages can read them without re-running detection.
                    _conflicts = _find_cannib(state.collection_groups, _corpus)
                    state.site_keywords = _corpus.to_dict()
                    state.site_cannibalisation = {
                        c.keyword: [
                            {**u, "kind": c.kind, "search_volume": c.search_volume}
                            for u in c.urls
                        ]
                        for c in _conflicts
                    }
                    save_state(state)
                    st.success(
                        f"Loaded {_corpus.total_rows:,} rows "
                        f"({_corpus.unique_keywords:,} unique keywords). "
                        f"Detected **{len(_conflicts)}** cannibalisation conflicts."
                    )
                    st.rerun()

    st.markdown("---")

    # --- Product scraping ---
    st.markdown("### Shopify Product Scraper (optional)")
    st.markdown(
        "Fetch real product data from each collection URL so generated copy references actual "
        "products. Uses Shopify's JSON endpoint first, HTML scraping as fallback."
    )
    if st.button(
        "🔍 Scrape products for all collections",
        help="Fetches real products from each collection URL via Shopify JSON. ~1-2s per collection.",
    ):
        from core.scraper import fetch_collection_data
        from core.sitemap import ParsedSitemap as _PS, find_related_urls as _find

        # Build sitemap once if available — used as a fallback per-collection.
        _sm_dict = state.sitemap_parsed or None
        _sm_obj = None
        if _sm_dict:
            try:
                _sm_obj = _PS.from_dict(_sm_dict)
            except Exception:
                _sm_obj = None

        progress = st.progress(0.0)
        status_msg = st.empty()
        scraped_count = 0
        sitemap_fallback_count = 0
        groups = state.collection_groups
        for i, col in enumerate(groups):
            col_url = col.collection_url
            status_msg.text(f"Fetching {col.collection_name}…")
            col_data = fetch_collection_data(col_url)
            if col_data.source != "failed" and col_data.products:
                col.products_to_link = [
                    {"name": p.name, "url": p.url} for p in col_data.products[:8]
                ]
                col.scraped_products = [p.model_dump() for p in col_data.products]
                col.existing_top_copy = col_data.existing_top_copy
                col.existing_bottom_copy = col_data.existing_bottom_copy
                scraped_count += 1
            elif _sm_obj is not None:
                # No live products — fall back to sitemap suggestions.
                secondary = [
                    kw.get("keyword", "") if isinstance(kw, dict) else str(kw)
                    for kw in (col.secondary_keywords or [])
                ]
                hits = _find(
                    primary_keyword=col.primary_keyword,
                    secondary_keywords=secondary,
                    sitemap=_sm_obj,
                    target_url=col_url,
                )
                if hits["products"]:
                    col.products_to_link = [
                        {"name": p["name"], "url": p["url"]} for p in hits["products"][:8]
                    ]
                    sitemap_fallback_count += 1
            progress.progress((i + 1) / len(groups))
        summary = f"Done — scraped products for {scraped_count}/{len(groups)} collections."
        if sitemap_fallback_count:
            summary += f" Sitemap data used as fallback for {sitemap_fallback_count} collection(s)."
        status_msg.text(summary)
        progress.empty()
        st.rerun()

    st.markdown("---")
    st.success("Data input complete. Navigate to **Priority Scoring** in the sidebar to continue.")
