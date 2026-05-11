"""Step 2: Priority Scoring & Batch Planning."""

import streamlit as st
import pandas as pd

from core.app_state import get_state, save_state


st.title("Step 2: Priority Scoring & Batch Planning")

state = get_state()

if not state.collection_groups:
    st.warning("No collection data found. Please complete Step 1 first.")
    st.stop()

from core.priority_scorer import (
    score_all_collections,
    identify_sub_collection_opportunities,
)
from core.sf_parser import derive_optimization_score, derive_nav_link_signal

source_format = state.source_format or ""
volume_only = source_format == "keyword_map"

HELP_TEXT = {
    "organic_traffic": (
        "Current organic clicks or estimated traffic to this collection.\n\n"
        "3 = 100+ clicks/month (or volume × 3% ≥ 100)\n"
        "2 = 20-99 clicks/month\n"
        "1 = under 20 clicks/month"
    ),
    "striking_distance": (
        "Keywords ranking just outside page 1 — small lifts win big traffic gains.\n\n"
        "3 = any keyword in positions 8-17\n"
        "2 = any keyword in positions 18-25\n"
        "1 = no keyword in striking distance, or no rank data"
    ),
    "revenue_potential": (
        "Inferred from search volume when product count is unknown.\n\n"
        "3 = total volume ≥ 1,000/month\n"
        "2 = total volume 200-999/month\n"
        "1 = total volume under 200/month"
    ),
    "homepage_nav_link": (
        "Whether this collection is linked from the homepage or main nav. "
        "Currently a manual signal — not auto-detected.\n\n"
        "3 = linked from homepage AND nav (high authority)\n"
        "2 = linked from one of the two\n"
        "1 = not linked from either"
    ),
    "current_optimization": (
        "How well-optimised the page currently is. Inverse signal — "
        "lower current optimisation means more upside.\n\n"
        "3 = nothing optimised (highest opportunity)\n"
        "2 = partially optimised\n"
        "1 = already well-optimised"
    ),
    "competitive_gap": (
        "Combines keyword difficulty against current rank.\n\n"
        "3 = low difficulty AND poor rank (big opportunity)\n"
        "2 = medium difficulty OR partial gap\n"
        "1 = high difficulty or already ranking well, or no data"
    ),
}

MODE_HELP = (
    "**Test Run** — validate prompts and brand voice on 1–2 collections before committing time. "
    "Use this for a new brand or after major prompt changes.\n\n"
    "**Standard Batch** — focused review-as-you-go session of 3–5 collections. "
    "Best for the day-to-day review workflow.\n\n"
    "**Full Run** — generate every selected collection sequentially. Use when prompts are stable "
    "and you trust the output enough to review in bulk afterwards."
)

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

if not state.scored_collections or st.button("Re-score Collections", help="Re-run the scoring engine over all collections. Useful after editing keyword data or applying new crawl data."):
    scored = score_all_collections(state.collection_groups, volume_only=volume_only)

    # ── Apply SF-derived scores where crawl data is available ────────────────
    sf_crawl_data = state.sf_crawl_data or {}
    sf_overrides_applied = 0
    if sf_crawl_data:
        for sc in scored:
            norm_url = sc.collection_url.rstrip("/").replace("http://", "https://")
            sf_page = sf_crawl_data.get(norm_url)
            if sf_page is None:
                continue
            sc.scores.current_optimization = derive_optimization_score(sf_page)
            sc.has_optimization_data = True
            nav_signal = derive_nav_link_signal(sf_page)
            if nav_signal is not None:
                sc.scores.homepage_nav_link = nav_signal
            sc.total_score = sc.scores.total
            sf_overrides_applied += 1
        if sf_overrides_applied > 0:
            scored.sort(key=lambda s: s.total_score, reverse=True)
            st.info(
                f"SF crawl data applied to **{sf_overrides_applied}** collections. "
                "Current Optimization scores updated from crawl data. "
                "Homepage Nav Link updated where signal was conclusive."
            )

    state.scored_collections = scored

scored = state.scored_collections

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
        "Optimization": str(sc.scores.current_optimization) + ("" if sc.has_optimization_data else "*"),
        "Competitive Gap": str(sc.scores.competitive_gap) + ("*" if not sc.has_difficulty_data else ""),
        "Volume": f"{sc.total_volume:,}",
        "Best Rank": sc.best_rank or "-",
        "Keywords": sc.keyword_count,
    })

df = pd.DataFrame(table_data)
st.dataframe(
    df,
    width="stretch",
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
                help=HELP_TEXT["organic_traffic"],
            )
        with oc2:
            striking = st.selectbox(
                striking_label, [1, 2, 3],
                index=sc.scores.striking_distance - 1,
                key=f"sd_{i}",
                help=HELP_TEXT["striking_distance"],
            )
        with oc3:
            revenue = st.selectbox(
                "Revenue", [1, 2, 3],
                index=sc.scores.revenue_potential - 1,
                key=f"rp_{i}",
                help=HELP_TEXT["revenue_potential"],
            )
        with oc4:
            nav_link = st.selectbox(
                nav_label, [1, 2, 3],
                index=sc.scores.homepage_nav_link - 1,
                key=f"nl_{i}",
                help=HELP_TEXT["homepage_nav_link"],
            )
        with oc5:
            optimization = st.selectbox(
                "Optimisation", [1, 2, 3],
                index=sc.scores.current_optimization - 1,
                key=f"co_{i}",
                help=HELP_TEXT["current_optimization"],
            )
        with oc6:
            competitive = st.selectbox(
                gap_label, [1, 2, 3],
                index=sc.scores.competitive_gap - 1,
                key=f"cg_{i}",
                help=HELP_TEXT["competitive_gap"],
            )

        sc.scores.organic_traffic = traffic
        sc.scores.striking_distance = striking
        sc.scores.revenue_potential = revenue
        sc.scores.homepage_nav_link = nav_link
        sc.scores.current_optimization = optimization
        sc.scores.competitive_gap = competitive
        sc.total_score = sc.scores.total

        missing_signals = []
        if not sc.has_rank_data:
            missing_signals.append("rank data (Striking Distance, Competitive Gap defaulted)")
        if not sc.has_difficulty_data:
            missing_signals.append("keyword difficulty (Competitive Gap defaulted)")
        if not sc.has_optimization_data:
            missing_signals.append("crawl data (Current Optimisation defaulted to 'unoptimised')")
        if missing_signals:
            st.caption(f"⚠️ Defaulted: {'; '.join(missing_signals)}")

    # Re-sort after overrides
    state.scored_collections.sort(
        key=lambda s: s.total_score, reverse=True
    )

st.markdown("---")

# --- 2.2 Batch Builder ---
st.markdown("## Batch Builder")

mode = st.radio(
    "Select a run mode",
    ["🧪 Test Run (1–2 collections)", "📋 Standard Batch (3–5)", "🚀 Full Run (all or custom)"],
    horizontal=True,
    help=MODE_HELP,
)

if "Test Run" in mode:
    _model_label = state.selected_model or "default model"
    st.info(
        f"🧪 **Test Run mode** — limited to 2 collections. Uses your selected model "
        f"(`{_model_label}`). Switch to Standard Batch or Full Run when you're ready to scale."
    )

# Select All / Clear All for Full Run mode
if "Full Run" in mode:
    sa_col1, sa_col2, _ = st.columns([1, 1, 4])
    with sa_col1:
        if st.button("Select All", key="select_all_btn"):
            for i in range(len(scored)):
                st.session_state[f"batch_{i}"] = True
            st.rerun()
    with sa_col2:
        if st.button("Clear All", key="clear_all_btn"):
            for i in range(len(scored)):
                st.session_state[f"batch_{i}"] = False
            st.rerun()

# ── Sub-collection opportunities indexed per parent for inline badges ─────
# Cached so the (potentially expensive) modifier scan doesn't run on every
# checkbox click. Invalidated when the underlying collection set changes.
def _opps_cache_key(collection_groups) -> str:
    import hashlib
    urls = sorted(g.collection_url for g in collection_groups)
    return hashlib.sha256("|".join(urls).encode()).hexdigest()[:16]

_current_opps_key = _opps_cache_key(state.collection_groups)
_cached_opps_key = state.opps_cache_key
if _current_opps_key != _cached_opps_key:
    opps_for_badges = identify_sub_collection_opportunities(
        state.collection_groups
    )
    opps_by_parent: dict[str, list[dict]] = {}
    for _opp in opps_for_badges:
        opps_by_parent.setdefault(_opp["parent_url"], []).append(_opp)
    state.sub_collection_opportunities = opps_by_parent
    state.opps_cache_key = _current_opps_key
else:
    opps_by_parent = state.sub_collection_opportunities or {}

batch_selections = []
for i, sc in enumerate(scored):
    _opps_for_row = opps_by_parent.get(sc.collection_url, [])
    _badge = (
        f" 💡 {len(_opps_for_row)} sub-opp{'s' if len(_opps_for_row) != 1 else ''}"
        if _opps_for_row
        else ""
    )
    selected = st.checkbox(
        f"{sc.collection_name} (Score: {sc.total_score}/18, Vol: {sc.total_volume:,}){_badge}",
        value=sc.in_batch,
        key=f"batch_{i}",
    )
    batch_selections.append(selected)
    if _opps_for_row:
        with st.expander(f"💡 Sub-collection ideas for {sc.collection_name}", expanded=False):
            for _opp in _opps_for_row:
                st.caption(f"• **{_opp['keyword']}** — {_opp['volume']:,} searches/mo")

selected_count = sum(batch_selections)

if "Test Run" in mode:
    if selected_count == 0:
        st.info("Select 1–2 collections to test your setup before a full run.")
    elif selected_count <= 2:
        st.success(f"{selected_count} collection(s) selected for test run.")
    else:
        st.warning(
            f"{selected_count} selected — Test Run works best with 1–2 collections. "
            "Switch to Standard Batch or Full Run if intentional."
        )

elif "Standard Batch" in mode:
    if selected_count == 0:
        st.info("Select 3–5 collections for this batch.")
    elif selected_count < 3:
        st.warning(f"Select at least 3 collections ({selected_count}/3 minimum for Standard Batch).")
    elif selected_count > 5:
        st.warning(
            f"{selected_count} selected — recommended maximum for Standard Batch is 5. "
            "Switch to Full Run mode to remove this limit."
        )
    else:
        st.success(f"{selected_count} collections selected.")

elif "Full Run" in mode:
    if selected_count == 0:
        st.info(f"Select collections manually or use Select All ({len(scored)} available).")
    else:
        est_mins = round(selected_count * 12 / 60, 1)
        st.success(
            f"{selected_count} collections selected for full run. "
            f"Estimated generation time: ~{est_mins} mins at 12s per collection."
        )

mode_label = {
    "Test Run" in mode: "Confirm Test Run",
    "Standard" in mode: "Confirm Batch",
    "Full Run" in mode: "Confirm Full Run",
}.get(True, "Confirm Batch")

# Test Run is now a hard cap rather than an advisory. Disable confirmation
# when the user has selected more than 2 collections under Test Run mode.
test_run_blocked = "Test Run" in mode and selected_count > 2
if test_run_blocked:
    st.error(
        "Test Run is limited to 2 collections. Uncheck some to proceed, "
        "or switch to **Standard Batch** / **Full Run**."
    )

if st.button(
    mode_label,
    type="primary",
    disabled=(selected_count < 1 or test_run_blocked),
):
    batch = []
    for i, selected in enumerate(batch_selections):
        scored[i].in_batch = selected
        if selected:
            batch.append({
                "collection_url": scored[i].collection_url,
                "collection_name": scored[i].collection_name,
                "primary_keyword": scored[i].primary_keyword,
                "primary_keyword_volume": state.collection_groups[i].primary_keyword_volume
                    if i < len(state.collection_groups) else None,
                "total_volume": scored[i].total_volume,
                "best_rank": scored[i].best_rank,
                "total_clicks": scored[i].total_clicks,
                "keyword_count": scored[i].keyword_count,
                "secondary_keywords": scored[i].secondary_keywords,
                "priority_score": scored[i].total_score,
            })

    # When the batch composition changes, drop the in-batch FAQ
    # exclusion list so the new batch isn't artificially constrained.
    new_urls = {b["collection_url"] for b in batch}
    old_urls = {b["collection_url"] for b in state.batch_collections}
    if new_urls != old_urls:
        state.batch_faq_topics = []

    state.batch_collections = batch
    state.batch_mode = mode
    save_state(state)
    st.success(f"Confirmed: {len(batch)} collections ready.")

st.markdown("---")

# --- 2.3 Sub-Collection Opportunities ---
st.markdown("## Sub-Collection Opportunities")

opportunities = identify_sub_collection_opportunities(
    state.collection_groups
)

if opportunities:
    st.markdown(f"**{len(opportunities)} potential sub-collection keywords** identified:")
    opp_df = pd.DataFrame(opportunities)
    st.dataframe(opp_df, width="stretch", hide_index=True)
else:
    st.info(
        "No sub-collection opportunities detected with significant volume. "
        "These are identified from modifier keywords (colour, material, size, etc.) "
        "with 500+ monthly searches."
    )
