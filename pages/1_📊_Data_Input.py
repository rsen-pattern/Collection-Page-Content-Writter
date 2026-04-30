"""Step 1: Project Setup & Data Input."""

import streamlit as st
import pandas as pd


st.title("Step 1: Data Input")

# Ensure session state is initialized
if "client_profile" not in st.session_state:
    st.warning("Please start from the main page to initialize the app.")
    st.stop()

# --- 1.1 Brand Profile status banner ---
cp = st.session_state.get("client_profile", {})
if not cp.get("brand_name"):
    st.warning("⚠️ No brand profile loaded.")
    st.page_link("pages/0_🏷️_Brand_Profile.py", label="→ Set up brand profile", icon="🏷️")
    st.stop()
else:
    st.success(f"Active brand: **{cp['brand_name']}** · {len(cp.get('brand_usps', []))} USPs")
    st.page_link("pages/0_🏷️_Brand_Profile.py", label="Edit brand profile", icon="🏷️")

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

_FORMAT_LABELS = {
    "gsc": "Google Search Console",
    "ahrefs": "Ahrefs",
    "semrush": "SEMrush",
    "keyword_map": "Keyword Mapping Document",
    "custom": "Custom Format",
}

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

        st.success(f"Detected format: **{format_label}** ({len(raw_df)} rows)")

        # Show raw preview
        with st.expander("Raw Data Preview"):
            st.dataframe(raw_df.head(20))

        if source_format == "keyword_map":
            # --- Keyword Mapping format: fully auto-handled, no dropdowns ---
            st.markdown("### Keyword Mapping Document — Auto Configuration")
            st.info(
                "Column mapping is automatic for this format. "
                "Keywords 1–4 and their volumes have been detected. "
                "Click **Process Data** to load all collections."
            )

            if st.button("Process Data", type="primary", disabled=not profile_valid):
                groups, skipped = normalize_keyword_map(raw_df)

                no_kw_count = sum(1 for s in skipped if s.reason == "no_keywords")
                zero_vol_count = sum(1 for s in skipped if s.reason == "zero_volume")

                st.session_state.normalized_data = pd.DataFrame()
                st.session_state.source_format = source_format
                st.session_state.collection_groups = groups
                st.session_state.skipped_collections = skipped
                st.session_state.raw_data = raw_df

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

                st.session_state.normalized_data = normalized
                st.session_state.source_format = source_format
                st.session_state.collection_groups = groups
                st.session_state.skipped_collections = []
                st.session_state.raw_data = raw_df

                st.success(f"Processed {len(normalized)} keywords into {len(groups)} collections")

    except Exception as e:
        st.error(f"Error processing file: {e}")

# --- 1.3 Keyword-to-Collection Grouping ---
if st.session_state.collection_groups:
    st.markdown("---")
    st.markdown("## Keyword-to-Collection Grouping")
    st.markdown(f"**{len(st.session_state.collection_groups)} collections** identified")

    # Keyword Mapping format: show summary preview table before expanders
    if st.session_state.get("source_format") == "keyword_map":
        preview_rows = [
            {
                "Collection Name": g.collection_name,
                "Primary Keyword": g.primary_keyword,
                "Primary Volume": g.primary_keyword_volume or 0,
                "Secondary Keywords": len(g.secondary_keywords),
            }
            for g in st.session_state.collection_groups
        ]
        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True)

    # Build set of zero-volume URLs for inline warnings
    zero_vol_urls = {
        s.collection_url
        for s in st.session_state.get("skipped_collections", [])
        if s.reason == "zero_volume"
    }

    for i, group in enumerate(st.session_state.collection_groups):
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
                    new_primary = all_keywords[primary_idx]
                    st.session_state.collection_groups[i].primary_keyword = new_primary

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
        progress = st.progress(0.0)
        status_msg = st.empty()
        scraped_count = 0
        groups = st.session_state.collection_groups
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
            progress.progress((i + 1) / len(groups))
        status_msg.text(f"Done — scraped products for {scraped_count}/{len(groups)} collections.")
        progress.empty()
        st.rerun()

    st.markdown("---")
    st.success("Data input complete. Navigate to **Priority Scoring** in the sidebar to continue.")
