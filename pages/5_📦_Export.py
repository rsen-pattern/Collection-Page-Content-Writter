"""Step 5: Export & Implementation Tracking."""

import streamlit as st
from datetime import datetime


st.title("Step 5: Export & Implementation Tracking")

if not st.session_state.get("batch_collections"):
    st.warning("No batch selected. Please complete Step 2 first.")
    st.stop()

from core.exporter import (
    export_keyword_map,
    export_content_delivery,
    export_shopify_csv,
    export_keyword_map_roundtrip,
    generate_copy_paste_cards,
)

batch = st.session_state.batch_collections
content = st.session_state.generated_content
client = st.session_state.client_profile

# Prepare export data
export_collections = []
for col in batch:
    url = col["collection_url"]
    col_content = content.get(url, {})

    # Get secondary keywords as strings (for standard exporters)
    # and as original dicts (for round-trip exporter)
    sec_kws = []
    sec_kws_raw = col.get("secondary_keywords", [])
    for kw in sec_kws_raw:
        if isinstance(kw, dict):
            sec_kws.append(kw.get("keyword", ""))
        else:
            sec_kws.append(str(kw))

    export_collections.append({
        "collection_url": url,
        "collection_name": col["collection_name"],
        "primary_keyword": col["primary_keyword"],
        "primary_keyword_volume": col.get("primary_keyword_volume"),
        "secondary_keywords": sec_kws,
        "secondary_keywords_raw": sec_kws_raw,
        "search_volume": col.get("total_volume", ""),
        "current_rank": col.get("best_rank", ""),
        "keyword_difficulty": "",
        "priority_score": col.get("priority_score", ""),
        "content": col_content,
    })

approved_count = sum(1 for c in export_collections if c["content"].get("approved"))
total_count = len(export_collections)
generated_count = sum(1 for c in export_collections if c["content"])

st.markdown(f"**{generated_count}/{total_count}** collections have generated content, **{approved_count}** approved")

if generated_count == 0:
    st.warning("No content generated yet. Please complete Step 4 first.")
    st.stop()

st.markdown("---")

# --- 5.1 Export Formats ---
st.markdown("## Export Formats")

source_format = st.session_state.get("source_format", "")

if source_format == "keyword_map":
    st.markdown("### Keyword Mapping Round-Trip (XLSX)")
    st.markdown(
        "Exports in the same format as your original keyword mapping document — "
        "same column structure with optimized content columns appended on the right."
    )
    if st.button("Generate Round-Trip Export", type="primary"):
        buffer = export_keyword_map_roundtrip(export_collections, client.get("brand_name", ""))
        st.download_button(
            label="Download Round-Trip Keyword Map",
            data=buffer,
            file_name=f"keyword_map_optimized_{client.get('brand_name', 'export').replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    st.markdown("---")

ec1, ec2, ec3 = st.columns(3)

with ec1:
    st.markdown("### Keyword Map (XLSX)")
    st.markdown("Completed keyword map matching the toolkit schema with optimized columns filled in.")
    if st.button("Generate Keyword Map", type="primary"):
        buffer = export_keyword_map(export_collections, client.get("brand_name", ""))
        st.download_button(
            label="Download Keyword Map",
            data=buffer,
            file_name=f"keyword_map_{client.get('brand_name', 'export').replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

with ec2:
    st.markdown("### Content Delivery (XLSX)")
    st.markdown("Per-collection sheets with all approved content, formatted for client handoff.")
    if st.button("Generate Content Delivery", type="primary"):
        buffer = export_content_delivery(export_collections, client.get("brand_name", ""))
        st.download_button(
            label="Download Content Delivery",
            data=buffer,
            file_name=f"content_delivery_{client.get('brand_name', 'export').replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

with ec3:
    st.markdown("### Shopify Bulk CSV")
    st.markdown("Matrixify-compatible CSV with handle, title, body HTML, meta title, meta description.")
    if st.button("Generate Shopify CSV", type="primary"):
        buffer = export_shopify_csv(export_collections)
        st.download_button(
            label="Download Shopify CSV",
            data=buffer,
            file_name=f"shopify_import_{client.get('brand_name', 'export').replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

st.markdown("---")

# --- Copy-Paste Cards ---
st.markdown("## Copy-Paste Cards")
st.markdown("One card per collection with clearly labeled fields. Copy directly into Shopify admin.")

cards = generate_copy_paste_cards(export_collections)

for card in cards:
    if not card.get("seo_title") and not card.get("description"):
        continue

    with st.expander(f"📋 {card['collection_name']}", expanded=False):
        st.markdown(f"**URL:** {card['collection_url']}")

        # SEO Title
        st.markdown("**SEO Title:**")
        st.code(card.get("seo_title", ""), language=None)

        # Collection Title
        st.markdown("**Collection Title (H1):**")
        st.code(card.get("collection_title", ""), language=None)

        # Meta Description
        st.markdown("**Meta Description:**")
        st.code(card.get("meta_description", ""), language=None)

        # Description (Markdown)
        st.markdown("**Description (Markdown):**")
        st.code(card.get("description", ""), language="markdown")

        # Description (HTML)
        st.markdown("**Description (HTML for Shopify):**")
        st.code(card.get("description_html", ""), language="html")

        # FAQs
        if card.get("faqs"):
            st.markdown("**FAQs:**")
            faq_text = ""
            for faq in card["faqs"]:
                faq_text += f"Q: {faq.get('question', '')}\nA: {faq.get('answer', '')}\n\n"
            st.code(faq_text, language=None)

st.markdown("---")

# --- 5.2 Implementation Tracker ---
st.markdown("## Implementation Tracker")

tracker = st.session_state.implementation_tracker

for col in export_collections:
    url = col["collection_url"]
    name = col["collection_name"]
    has_content = bool(col["content"])
    approved = col["content"].get("approved", False)

    if url not in tracker:
        tracker[url] = {
            "collection_name": name,
            "content_status": "Approved" if approved else ("In Review" if has_content else "Pending"),
            "implemented": False,
            "date": "",
            "notes": "",
        }
    else:
        # Update content status
        tracker[url]["content_status"] = "Approved" if approved else ("In Review" if has_content else "Pending")

tc1, tc2, tc3, tc4, tc5 = st.columns([2, 1.5, 1, 1, 2])
tc1.markdown("**Collection**")
tc2.markdown("**Content Status**")
tc3.markdown("**Implemented?**")
tc4.markdown("**Date**")
tc5.markdown("**Notes**")

for url, data in tracker.items():
    tc1, tc2, tc3, tc4, tc5 = st.columns([2, 1.5, 1, 1, 2])

    with tc1:
        st.markdown(data["collection_name"])
    with tc2:
        status_icon = {"Approved": "✅", "In Review": "🔄", "Pending": "⬜"}.get(data["content_status"], "")
        st.markdown(f"{status_icon} {data['content_status']}")
    with tc3:
        implemented = st.checkbox(
            "Live",
            value=data.get("implemented", False),
            key=f"impl_{url}",
            label_visibility="collapsed",
        )
        data["implemented"] = implemented
    with tc4:
        if implemented and not data.get("date"):
            data["date"] = datetime.now().strftime("%Y-%m-%d")
        st.markdown(data.get("date", "—"))
    with tc5:
        notes = st.text_input(
            "Notes",
            value=data.get("notes", ""),
            key=f"notes_{url}",
            label_visibility="collapsed",
        )
        data["notes"] = notes

st.session_state.implementation_tracker = tracker
