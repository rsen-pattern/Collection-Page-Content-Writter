"""Step 1: Project Setup & Data Input."""

import streamlit as st
import pandas as pd


st.title("Step 1: Data Input")

# Ensure session state is initialized
if "client_profile" not in st.session_state:
    st.warning("Please start from the main page to initialize the app.")
    st.stop()

# --- 1.1 Client Profile ---
st.markdown("## Client Profile")

col1, col2 = st.columns(2)

with col1:
    brand_name = st.text_input(
        "Client / Store Name *",
        value=st.session_state.client_profile.get("brand_name", ""),
    )
    store_url = st.text_input(
        "Store URL *",
        value=st.session_state.client_profile.get("store_url", ""),
        placeholder="https://example.com",
    )
    target_market = st.selectbox(
        "Target Market *",
        ["UK", "US", "AU", "CA", "EU", "Global"],
        index=["UK", "US", "AU", "CA", "EU", "Global"].index(
            st.session_state.client_profile.get("target_market", "UK")
        ),
    )

with col2:
    usps_text = st.text_area(
        "Brand USPs (one per line, 3-5 required) *",
        value="\n".join(st.session_state.client_profile.get("brand_usps", [])),
        height=120,
        help="What makes this brand unique? These get woven into every piece of generated content.",
    )
    voice_notes = st.text_area(
        "Brand Voice Notes",
        value=st.session_state.client_profile.get("voice_notes", ""),
        height=80,
        placeholder="e.g., Warm and approachable, avoids jargon, speaks to style-conscious women 25-45",
    )

# Save profile
brand_usps = [u.strip() for u in usps_text.strip().split("\n") if u.strip()]
st.session_state.client_profile = {
    "brand_name": brand_name,
    "store_url": store_url,
    "brand_usps": brand_usps,
    "voice_notes": voice_notes,
    "target_market": target_market,
}

# Validation
profile_valid = bool(brand_name and store_url and len(brand_usps) >= 3)
if not profile_valid:
    missing = []
    if not brand_name:
        missing.append("Client Name")
    if not store_url:
        missing.append("Store URL")
    if len(brand_usps) < 3:
        missing.append(f"Brand USPs ({len(brand_usps)}/3 minimum)")
    st.warning(f"Complete the profile to continue: {', '.join(missing)}")

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

if uploaded_file is not None:
    from core.data_ingestion import ingest_file, detect_format, read_upload

    try:
        raw_df = read_upload(uploaded_file)
        source_format = detect_format(raw_df)

        st.success(f"Detected format: **{source_format.upper()}** ({len(raw_df)} rows)")

        # Show raw preview
        with st.expander("Raw Data Preview"):
            st.dataframe(raw_df.head(20))

        from core.data_ingestion import normalize_dataframe, group_by_collection, load_format_mappings, _find_column, normalize_keyword_map

        if source_format == "keyword_map":
            # --- Keyword Mapping format: fully auto-handled, no dropdowns needed ---
            st.markdown("### Column Mapping")
            st.info(
                "**Keyword Mapping format detected** — column assignments are automatic. "
                "Keywords 1–4 and their search volumes will be read directly from the file."
            )

            if st.button("Process Data", type="primary", disabled=not profile_valid):
                groups = normalize_keyword_map(raw_df)
                skipped = len(raw_df) - len(groups)

                st.session_state.normalized_data = pd.DataFrame()
                st.session_state.source_format = source_format
                st.session_state.collection_groups = groups
                st.session_state.raw_data = raw_df

                st.success(
                    f"Keyword Mapping format detected — **{len(groups)} collections loaded**, "
                    f"{skipped} skipped (no keywords)"
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

    for i, group in enumerate(st.session_state.collection_groups):
        with st.expander(
            f"{group.collection_name} — {group.primary_keyword} "
            f"(Vol: {group.total_volume:,} | Keywords: {len(group.secondary_keywords) + 1})"
        ):
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
    st.success("Data input complete. Navigate to **Priority Scoring** in the sidebar to continue.")
