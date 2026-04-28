"""Step 2: Priority Scoring & Batch Planning."""

import streamlit as st
import pandas as pd


st.title("Step 2: Priority Scoring & Batch Planning")

if not st.session_state.get("collection_groups"):
    st.warning("No collection data found. Please complete Step 1 first.")
    st.stop()

from core.priority_scorer import (
    score_all_collections,
    identify_sub_collection_opportunities,
)

source_format = st.session_state.get("source_format", "")
volume_only = source_format == "keyword_map"

# --- Limited data banner for keyword_map format ---
if volume_only:
    st.info(
        "**Limited scoring data** — Keyword Mapping documents contain keyword "
        "and volume data only. Four of the six scoring factors have no data signal "
        "and will default as follows:\n\n"
        "- **Striking Distance** → 1 (no rank data)\n"
        "- **Homepage Nav Link** → 1 (manual input required)\n"
        "- **Competitive Gap** → 1 (no rank or difficulty data)\n"
        "- **Current Optimization** → 3 (assumed unoptimized)\n\n"
        "Traffic and Revenue scores use search volume bands. "
        "Use **Manual Score Overrides** below to adjust factors you know from other sources."
    )

# --- 2.1 Auto-Scoring ---
st.markdown("## Collection Scoring")

if not st.session_state.get("scored_collections") or st.button("Re-score Collections"):
    scored = score_all_collections(st.session_state.collection_groups, volume_only=volume_only)
    st.session_state.scored_collections = scored

scored = st.session_state.scored_collections

if not scored:
    st.info("No collections to score.")
    st.stop()

# Scoring table
st.markdown(f"**{len(scored)} collections scored** (max score: 18)")

table_data = []
for sc in scored:
    table_data.append({
        "Collection": sc.collection_name,
        "Primary Keyword": sc.primary_keyword,
        "Total Score": sc.total_score,
        "Traffic": sc.scores.organic_traffic,
        "Striking Dist.": str(sc.scores.striking_distance) + ("*" if not sc.has_rank_data else ""),
        "Revenue": sc.scores.revenue_potential,
        "Nav Link": str(sc.scores.homepage_nav_link) + "*",
        "Optimization": sc.scores.current_optimization,
        "Competitive Gap": str(sc.scores.competitive_gap) + ("*" if not sc.has_difficulty_data else ""),
        "Volume": f"{sc.total_volume:,}",
        "Best Rank": sc.best_rank or "-",
        "Keywords": sc.keyword_count,
    })

df = pd.DataFrame(table_data)
st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Total Score": st.column_config.ProgressColumn(
            min_value=0, max_value=18, format="%d/18"
        ),
    },
)

if volume_only:
    st.caption("* Defaulted — no data available. Use Manual Score Overrides to adjust.")

# Manual overrides
st.markdown("### Manual Score Overrides")
with st.expander("Adjust individual factor scores", expanded=volume_only):
    for i, sc in enumerate(scored):
        st.markdown(f"**{sc.collection_name}**")
        oc1, oc2, oc3, oc4, oc5, oc6 = st.columns(6)

        striking_label = "Striking Dist." + (" ⚠️" if not sc.has_rank_data else "")
        nav_label = "Nav Link ⚠️"
        gap_label = "Comp. Gap" + (" ⚠️" if not sc.has_difficulty_data else "")

        with oc1:
            traffic = st.selectbox(
                "Traffic", [1, 2, 3],
                index=sc.scores.organic_traffic - 1,
                key=f"ot_{i}",
            )
        with oc2:
            striking = st.selectbox(
                striking_label, [1, 2, 3],
                index=sc.scores.striking_distance - 1,
                key=f"sd_{i}",
            )
        with oc3:
            revenue = st.selectbox(
                "Revenue", [1, 2, 3],
                index=sc.scores.revenue_potential - 1,
                key=f"rp_{i}",
            )
        with oc4:
            nav_link = st.selectbox(
                nav_label, [1, 2, 3],
                index=sc.scores.homepage_nav_link - 1,
                key=f"nl_{i}",
            )
        with oc5:
            optimization = st.selectbox(
                "Optimization", [1, 2, 3],
                index=sc.scores.current_optimization - 1,
                key=f"co_{i}",
            )
        with oc6:
            competitive = st.selectbox(
                gap_label, [1, 2, 3],
                index=sc.scores.competitive_gap - 1,
                key=f"cg_{i}",
            )

        sc.scores.organic_traffic = traffic
        sc.scores.striking_distance = striking
        sc.scores.revenue_potential = revenue
        sc.scores.homepage_nav_link = nav_link
        sc.scores.current_optimization = optimization
        sc.scores.competitive_gap = competitive
        sc.total_score = sc.scores.total

    # Re-sort after overrides
    st.session_state.scored_collections.sort(
        key=lambda s: s.total_score, reverse=True
    )

st.markdown("---")

# --- 2.2 Batch Builder ---
st.markdown("## Batch Builder")
st.markdown("Select **3-5 collections** for the current optimization batch.")

batch_selections = []
for i, sc in enumerate(scored):
    selected = st.checkbox(
        f"{sc.collection_name} (Score: {sc.total_score}/18, Vol: {sc.total_volume:,})",
        value=sc.in_batch,
        key=f"batch_{i}",
    )
    batch_selections.append(selected)

selected_count = sum(batch_selections)

if selected_count < 3:
    st.warning(f"Select at least 3 collections ({selected_count}/3 minimum)")
elif selected_count > 5:
    st.warning(f"Recommended maximum is 5 collections ({selected_count} selected)")
else:
    st.success(f"{selected_count} collections selected for this batch")

if st.button("Confirm Batch", type="primary", disabled=selected_count < 1):
    batch = []
    for i, selected in enumerate(batch_selections):
        scored[i].in_batch = selected
        if selected:
            batch.append({
                "collection_url": scored[i].collection_url,
                "collection_name": scored[i].collection_name,
                "primary_keyword": scored[i].primary_keyword,
                "primary_keyword_volume": st.session_state.collection_groups[i].primary_keyword_volume
                    if i < len(st.session_state.collection_groups) else None,
                "total_volume": scored[i].total_volume,
                "best_rank": scored[i].best_rank,
                "total_clicks": scored[i].total_clicks,
                "keyword_count": scored[i].keyword_count,
                "secondary_keywords": scored[i].secondary_keywords,
                "priority_score": scored[i].total_score,
            })

    st.session_state.batch_collections = batch
    st.success(f"Batch confirmed: {len(batch)} collections ready for audit and content generation.")

st.markdown("---")

# --- 2.3 Sub-Collection Opportunities ---
st.markdown("## Sub-Collection Opportunities")

opportunities = identify_sub_collection_opportunities(
    st.session_state.collection_groups
)

if opportunities:
    st.markdown(f"**{len(opportunities)} potential sub-collection keywords** identified:")
    opp_df = pd.DataFrame(opportunities)
    st.dataframe(opp_df, use_container_width=True, hide_index=True)
else:
    st.info(
        "No sub-collection opportunities detected with significant volume. "
        "These are identified from modifier keywords (colour, material, size, etc.) "
        "with 500+ monthly searches."
    )
