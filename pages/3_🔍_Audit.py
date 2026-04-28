"""Step 3: Automated Audit."""

import streamlit as st

from core.scraper import scrape_collection_page


st.title("Step 3: Automated Audit")

if not st.session_state.get("batch_collections"):
    st.warning("No batch selected. Please complete Step 2 first.")
    st.stop()

from core.auditor import (
    CollectionAuditData,
    audit_collection,
    get_priority_actions,
    get_category_scores,
)

batch = st.session_state.batch_collections

# ── Skip Audit option ─────────────────────────────────────────────────────────
st.info(
    "**Skip Audit** if you are generating content from scratch and do not need "
    "to audit existing page data. The audit is optional — content generation "
    "works without it."
)
if st.button("⏭ Skip Audit — Proceed to Content Studio", type="secondary"):
    st.switch_page("pages/4_✍️_Content_Studio.py")

st.markdown("---")

st.markdown(f"## Audit {len(batch)} Collections in Batch")
st.markdown(
    "Click **Scrape All Pages** to auto-populate fields from the live site, "
    "or enter page data manually below."
)

# ── Scrape All button ─────────────────────────────────────────────────────────
scrape_col1, scrape_col2 = st.columns([2, 5])
with scrape_col1:
    scrape_all_clicked = st.button(
        "🔍 Scrape All Pages",
        type="primary",
        help="Fetch live page data for all collections in this batch automatically.",
    )
with scrape_col2:
    est_time = max(1, round(len(batch) * 2 / 60, 1))
    st.caption(
        f"Fetches title, H1, meta description, and collection description from each live URL. "
        f"~{len(batch)} requests at ~2s each — takes roughly {est_time} mins for this batch."
    )

if scrape_all_clicked:
    progress = st.progress(0, text="Starting scrape...")
    scrape_results = {}
    for idx, col in enumerate(batch):
        url = col["collection_url"]
        progress.progress(
            idx / len(batch),
            text=f"Scraping {idx + 1}/{len(batch)}: {col['collection_name']}...",
        )
        result = scrape_collection_page(url)
        scrape_results[url] = result
    progress.progress(1.0, text="Scrape complete.")

    st.session_state.scrape_results = scrape_results

    success_count = sum(1 for r in scrape_results.values() if r.success)
    fail_count = len(scrape_results) - success_count
    if fail_count == 0:
        st.success(f"Scraped {success_count} pages successfully.")
    else:
        st.warning(
            f"Scraped {success_count} pages successfully. "
            f"{fail_count} failed — see individual collections below for details."
        )
    st.rerun()

# ── Per-collection data input ─────────────────────────────────────────────────
for i, col in enumerate(batch):
    with st.expander(f"📄 {col['collection_name']}", expanded=i == 0):
        url = col["collection_url"]
        st.markdown(f"**URL:** {url}")
        st.markdown(f"**Primary Keyword:** {col['primary_keyword']}")

        # Per-collection scrape button
        scrape_result = st.session_state.get("scrape_results", {}).get(url)

        btn_col, status_col = st.columns([1, 4])
        with btn_col:
            scrape_clicked = st.button("🔍 Scrape Page", key=f"scrape_{i}")
        with status_col:
            if scrape_result is not None:
                if scrape_result.success:
                    st.caption(
                        f"✅ Scraped — {scrape_result.fields_found}/4 fields found. "
                        "Edit any field below before running the audit."
                    )
                else:
                    st.caption(f"❌ Scrape failed: {scrape_result.error}")

        if scrape_clicked:
            with st.spinner(f"Scraping {col['collection_name']}..."):
                result = scrape_collection_page(url)
                results = st.session_state.get("scrape_results", {})
                results[url] = result
                st.session_state.scrape_results = results
            st.rerun()

        # Helper: scraped value first, then previously saved audit input, then empty
        def _default(field_key, scrape_attr, _sr=scrape_result, _url=url):
            if _sr and _sr.success:
                scraped_val = getattr(_sr, scrape_attr, "")
                if scraped_val:
                    return scraped_val
            return (
                st.session_state.audit_results
                .get(_url, {})
                .get("input", {})
                .get(field_key, "")
            )

        ac1, ac2 = st.columns(2)

        with ac1:
            seo_title = st.text_input(
                "Current SEO Title",
                key=f"audit_seo_title_{i}",
                value=_default("seo_title", "seo_title"),
            )
            h1 = st.text_input(
                "Current H1 / Collection Title",
                key=f"audit_h1_{i}",
                value=_default("h1", "h1"),
            )
            meta_desc = st.text_input(
                "Current Meta Description",
                key=f"audit_meta_{i}",
                value=_default("meta_description", "meta_description"),
            )

        with ac2:
            description = st.text_area(
                "Current Description",
                key=f"audit_desc_{i}",
                height=100,
                value=_default("description", "description"),
            )
            linked_homepage = st.selectbox(
                "Linked from Homepage?",
                ["Unknown", "Yes", "No"],
                key=f"audit_homepage_{i}",
            )
            linked_blog = st.selectbox(
                "Linked from Blog?",
                ["Unknown", "Yes", "No"],
                key=f"audit_blog_{i}",
            )

        if st.button("Run Audit", key=f"run_audit_{i}", type="primary"):
            audit_data = CollectionAuditData(
                collection_url=col["collection_url"],
                collection_name=col["collection_name"],
                primary_keyword=col["primary_keyword"],
                seo_title=seo_title,
                h1=h1,
                description=description,
                meta_description=meta_desc,
                linked_from_homepage=True if linked_homepage == "Yes" else (False if linked_homepage == "No" else None),
                linked_from_blog=True if linked_blog == "Yes" else (False if linked_blog == "No" else None),
                brand_usps=st.session_state.client_profile.get("brand_usps", []),
                url_handle=col["collection_url"].rstrip("/").split("/")[-1] if "/collections/" in col["collection_url"] else "",
            )

            result = audit_collection(audit_data)
            st.session_state.audit_results[col["collection_url"]] = {
                "result": result,
                "input": {
                    "seo_title": seo_title,
                    "h1": h1,
                    "description": description,
                    "meta_description": meta_desc,
                },
            }

            # Display results
            st.markdown(f"### Audit Score: {result.score_display}")

            categories = get_category_scores(result)
            cat_cols = st.columns(len(categories))
            for j, (cat_name, cat_scores) in enumerate(categories.items()):
                with cat_cols[j]:
                    st.metric(
                        cat_name,
                        f"{cat_scores['passing']}/{cat_scores['total']}",
                    )

            for check in result.checks:
                if check.result == "pass":
                    st.markdown(f"✅ {check.label} — {check.details}")
                elif check.result == "fail":
                    st.markdown(f"❌ {check.label} — {check.details}")
                else:
                    st.markdown(f"⚠️ {check.label} — {check.details}")

            priority_actions = get_priority_actions(result)
            if priority_actions:
                st.markdown("### Priority Actions")
                for action in priority_actions:
                    impact_badge = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(action.impact, "")
                    st.markdown(
                        f"{impact_badge} **{action.label}** — {action.details} "
                        f"(Impact: {action.impact}, Effort: {action.effort})"
                    )

# ── Audit Summary ─────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("## Audit Summary")

if st.session_state.audit_results:
    for url, data in st.session_state.audit_results.items():
        result = data["result"]
        col_name = result.collection_name
        st.markdown(
            f"**{col_name}**: {result.score_display} "
            f"({result.passing} pass, {result.failing} fail, {result.needs_review} review)"
        )
else:
    st.info("No audits completed yet. Scrape pages or enter data above and click 'Run Audit'.")
