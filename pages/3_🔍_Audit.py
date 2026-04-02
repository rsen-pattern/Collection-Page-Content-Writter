"""Step 3: Automated Audit."""

import streamlit as st


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

st.markdown(f"## Audit {len(batch)} Collections in Batch")
st.markdown(
    "Enter current page data for each collection. In Phase 2, this will be auto-populated via DataForSEO crawl."
)

# Data input per collection
for i, col in enumerate(batch):
    with st.expander(f"📄 {col['collection_name']}", expanded=i == 0):
        st.markdown(f"**URL:** {col['collection_url']}")
        st.markdown(f"**Primary Keyword:** {col['primary_keyword']}")

        ac1, ac2 = st.columns(2)

        with ac1:
            seo_title = st.text_input(
                "Current SEO Title",
                key=f"audit_seo_title_{i}",
                value=st.session_state.audit_results.get(col["collection_url"], {}).get("input", {}).get("seo_title", ""),
            )
            h1 = st.text_input(
                "Current H1 / Collection Title",
                key=f"audit_h1_{i}",
                value=st.session_state.audit_results.get(col["collection_url"], {}).get("input", {}).get("h1", ""),
            )
            meta_desc = st.text_input(
                "Current Meta Description",
                key=f"audit_meta_{i}",
                value=st.session_state.audit_results.get(col["collection_url"], {}).get("input", {}).get("meta_description", ""),
            )

        with ac2:
            description = st.text_area(
                "Current Description",
                key=f"audit_desc_{i}",
                height=100,
                value=st.session_state.audit_results.get(col["collection_url"], {}).get("input", {}).get("description", ""),
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

        if st.button(f"Run Audit", key=f"run_audit_{i}", type="primary"):
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

            # Category breakdown
            categories = get_category_scores(result)
            cat_cols = st.columns(len(categories))
            for j, (cat_name, cat_scores) in enumerate(categories.items()):
                with cat_cols[j]:
                    st.metric(
                        cat_name,
                        f"{cat_scores['passing']}/{cat_scores['total']}",
                    )

            # Check results
            for check in result.checks:
                if check.result == "pass":
                    st.markdown(f"✅ {check.label} — {check.details}")
                elif check.result == "fail":
                    st.markdown(f"❌ {check.label} — {check.details}")
                else:
                    st.markdown(f"⚠️ {check.label} — {check.details}")

            # Priority actions
            priority_actions = get_priority_actions(result)
            if priority_actions:
                st.markdown("### Priority Actions")
                for action in priority_actions:
                    impact_badge = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(action.impact, "")
                    st.markdown(
                        f"{impact_badge} **{action.label}** — {action.details} "
                        f"(Impact: {action.impact}, Effort: {action.effort})"
                    )

# Show existing audit results
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
    st.info("No audits completed yet. Enter page data above and click 'Run Audit'.")
