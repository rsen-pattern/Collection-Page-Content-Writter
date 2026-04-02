"""Single URL Content Writer — Draft content for a specific collection page."""

import re
import streamlit as st

st.set_page_config(page_title="Single URL Writer - Collection SEO Engine", layout="wide")
st.title("Single URL Content Writer")
st.markdown("Generate optimized content for a single collection page — no CSV upload or batch workflow needed.")

# --- Session state init ---
if "single_url_content" not in st.session_state:
    st.session_state.single_url_content = {}
if "single_url_history" not in st.session_state:
    st.session_state.single_url_history = []

# --- Sidebar: Previous URLs ---
with st.sidebar:
    st.markdown("### Previous URLs")
    for item in st.session_state.single_url_history:
        st.caption(f"• {item['collection_name']}")

st.markdown("---")

# ============================================================
# 1. COLLECTION & BRAND CONTEXT (single form)
# ============================================================
st.markdown("## 1. Collection Details")

col_left, col_right = st.columns(2)

with col_left:
    collection_url = st.text_input(
        "Collection URL *",
        placeholder="https://yourstore.com/collections/example",
    )
    collection_name = st.text_input(
        "Collection Name *",
        placeholder="e.g. Waterproof Necklaces",
    )
    primary_keyword = st.text_input(
        "Primary Keyword *",
        placeholder="e.g. waterproof necklaces",
    )
    secondary_keywords_text = st.text_area(
        "Secondary Keywords (one per line)",
        placeholder="gold waterproof necklaces\nsilver waterproof necklaces\nwaterproof jewelry",
        height=100,
    )
    primary_keyword_volume = st.number_input(
        "Primary Keyword Search Volume (optional)",
        min_value=0,
        value=0,
        step=10,
    )

with col_right:
    brand_name = st.text_input(
        "Brand / Store Name *",
        placeholder="e.g. Lunar Jewelry",
    )
    store_url = st.text_input(
        "Store URL",
        placeholder="https://yourstore.com",
    )
    usps_text = st.text_area(
        "Brand USPs (one per line, min 2) *",
        placeholder="Handcrafted in London using recycled metals\n100% waterproof\nLifetime warranty",
        height=100,
    )
    voice_notes = st.text_area(
        "Brand Voice Notes (optional)",
        placeholder="Warm, approachable tone. Speaks to style-conscious women 25-45.",
        height=68,
    )
    target_market = st.selectbox("Target Market", ["UK", "US", "AU", "CA", "EU", "Global"])

st.markdown("---")

# ============================================================
# 2. CONTENT INPUTS (products, related collections, PAA)
# ============================================================
st.markdown("## 2. Content Inputs")

ci_left, ci_right = st.columns(2)

with ci_left:
    products_text = st.text_area(
        "Products to Link (one per line: Product Name | /products/handle)",
        placeholder="Gold Snake Chain | /products/gold-snake-chain\nSilver Pendant | /products/silver-pendant",
        height=100,
    )
    related_text = st.text_area(
        "Related Collections to Link (one per line: Name | /collections/handle)",
        placeholder="Gold Earrings | /collections/gold-earrings\nSilver Rings | /collections/silver-rings",
        height=80,
    )

with ci_right:
    paa_text = st.text_area(
        "People Also Ask / FAQ Seed Questions (one per line, optional)",
        placeholder="Can you shower with waterproof necklaces?\nDo waterproof necklaces tarnish?",
        height=100,
    )
    keyword_difficulty = st.slider(
        "Keyword Difficulty (affects target word count)",
        min_value=0,
        max_value=100,
        value=30,
        help="Higher difficulty → longer description target. 0-29: ~75 words, 30-49: ~88 words, 50+: ~125 words",
    )

st.markdown("---")

# ============================================================
# 3. GENERATE
# ============================================================
st.markdown("## 3. Generate Content")

# Parse inputs
secondary_keywords = [kw.strip() for kw in secondary_keywords_text.strip().split("\n") if kw.strip()]
brand_usps = [u.strip() for u in usps_text.strip().split("\n") if u.strip()]

products_to_link = []
for line in products_text.strip().split("\n"):
    if "|" in line:
        parts = line.split("|", 1)
        products_to_link.append({"name": parts[0].strip(), "url": parts[1].strip()})

related_collections = []
for line in related_text.strip().split("\n"):
    if "|" in line:
        parts = line.split("|", 1)
        related_collections.append({"name": parts[0].strip(), "url": parts[1].strip()})

paa_questions = [q.strip() for q in paa_text.strip().split("\n") if q.strip()]

# Validation
required_filled = all([collection_url, collection_name, primary_keyword, brand_name, len(brand_usps) >= 2])
has_api_key = bool(st.session_state.get("bifrost_api_key"))

if not required_filled:
    missing = []
    if not collection_url:
        missing.append("Collection URL")
    if not collection_name:
        missing.append("Collection Name")
    if not primary_keyword:
        missing.append("Primary Keyword")
    if not brand_name:
        missing.append("Brand Name")
    if len(brand_usps) < 2:
        missing.append(f"Brand USPs ({len(brand_usps)}/2 minimum)")
    st.warning(f"Fill in required fields: {', '.join(missing)}")

if not has_api_key:
    st.warning("Set your Bifrost API key in the sidebar on the main page.")

# Generation options
gen_col1, gen_col2 = st.columns(2)
with gen_col1:
    generation_type = st.radio(
        "What to generate",
        ["Full Package (all elements)", "Description Only", "Titles Only", "FAQs Only"],
        horizontal=True,
    )

type_map = {
    "Full Package (all elements)": "full",
    "Description Only": "description",
    "Titles Only": "titles",
    "FAQs Only": "faqs",
}

if st.button(
    "Generate Content",
    type="primary",
    disabled=not (required_filled and has_api_key),
    use_container_width=True,
):
    from core.brief_builder import build_brief
    from core.content_generator import generate_content

    brief = build_brief(
        collection_url=collection_url,
        collection_name=collection_name,
        primary_keyword=primary_keyword,
        primary_keyword_volume=primary_keyword_volume or None,
        secondary_keywords=[{"keyword": kw} for kw in secondary_keywords],
        brand_usps=brand_usps,
        brand_name=brand_name,
        store_url=store_url,
        target_market=target_market,
        voice_notes=voice_notes,
        products_to_link=products_to_link,
        related_collections=related_collections,
        paa_questions=paa_questions,
        keyword_difficulty=float(keyword_difficulty),
    )

    with st.spinner("Generating content..."):
        try:
            result, used_model = generate_content(
                api_key=st.session_state.bifrost_api_key,
                base_url=st.session_state.get("bifrost_base_url", "https://api.getbifrost.ai"),
                model=st.session_state.get("selected_model", "anthropic/claude-sonnet-4-6"),
                brief=brief,
                generation_type=type_map[generation_type],
            )
            selected = st.session_state.get("selected_model", "")
            if used_model != selected:
                st.info(f"Fallback: used **{used_model}** (selected model failed)")
            st.session_state.single_url_content = {
                "seo_title": result.seo_title,
                "collection_title": result.collection_title,
                "description": result.description,
                "meta_description": result.meta_description,
                "faqs": result.faqs,
                "collection_name": collection_name,
                "collection_url": collection_url,
                "primary_keyword": primary_keyword,
                "secondary_keywords": secondary_keywords,
                "brand_usps": brand_usps,
                "brand_name": brand_name,
            }
            # Track history
            if not any(h["collection_url"] == collection_url for h in st.session_state.single_url_history):
                st.session_state.single_url_history.append({
                    "collection_url": collection_url,
                    "collection_name": collection_name,
                })
            st.rerun()
        except Exception as e:
            st.error(f"Generation failed: {e}")

# ============================================================
# 4. REVIEW, EDIT & VALIDATE
# ============================================================
content = st.session_state.single_url_content

if content:
    st.markdown("---")
    st.markdown("## 4. Review & Edit")

    from core.validator import (
        validate_description,
        validate_seo_title,
        validate_collection_title,
        validate_meta_description,
        validate_faqs,
    )

    tab_desc, tab_titles, tab_faq, tab_meta, tab_export = st.tabs(
        ["Description", "Titles", "FAQs", "Meta Description", "Export"]
    )

    # --- Description ---
    with tab_desc:
        desc = st.text_area(
            "Collection Description",
            value=content.get("description", ""),
            height=250,
            key="single_desc",
        )
        content["description"] = desc

        if desc.strip():
            v = validate_description(
                desc,
                content.get("primary_keyword", ""),
                content.get("secondary_keywords", []),
                content.get("brand_usps", []),
            )

            wc = len(desc.split())
            mc1, mc2, mc3, mc4 = st.columns(4)
            with mc1:
                st.metric("Word Count", wc)
            with mc2:
                kf = sum(1 for kw in content.get("secondary_keywords", []) if kw.lower() in desc.lower())
                st.metric("Keywords Found", f"{kf}/{len(content.get('secondary_keywords', []))}")
            with mc3:
                lc = len(re.findall(r"\[.*?\]\(.*?\)", desc))
                st.metric("Internal Links", lc)
            with mc4:
                uc = sum(
                    1 for usp in content.get("brand_usps", [])
                    if any(w in desc.lower() for w in usp.lower().split() if len(w) > 3)
                )
                st.metric("USPs Referenced", f"{uc}/{len(content.get('brand_usps', []))}")

            for vr in v.results:
                icon = "✅" if vr.passed else ("❌" if vr.severity == "error" else "⚠️")
                st.markdown(f"{icon} {vr.message}")

    # --- Titles ---
    with tab_titles:
        tc1, tc2 = st.columns(2)
        with tc1:
            seo_title = st.text_input(
                "SEO Title",
                value=content.get("seo_title", ""),
                key="single_seo_title",
            )
            content["seo_title"] = seo_title

            if seo_title:
                v = validate_seo_title(
                    seo_title,
                    content.get("primary_keyword", ""),
                    h1=content.get("collection_title", ""),
                    brand_name=content.get("brand_name", ""),
                )
                for vr in v.results:
                    icon = "✅" if vr.passed else ("❌" if vr.severity == "error" else "⚠️")
                    st.markdown(f"{icon} {vr.message}")

        with tc2:
            h1 = st.text_input(
                "Collection Title (H1)",
                value=content.get("collection_title", ""),
                key="single_h1",
            )
            content["collection_title"] = h1

            if h1:
                v = validate_collection_title(
                    h1,
                    content.get("primary_keyword", ""),
                    seo_title=content.get("seo_title", ""),
                )
                for vr in v.results:
                    icon = "✅" if vr.passed else ("❌" if vr.severity == "error" else "⚠️")
                    st.markdown(f"{icon} {vr.message}")

    # --- FAQs ---
    with tab_faq:
        faqs = content.get("faqs", [])
        updated_faqs = []
        for j, faq in enumerate(faqs):
            st.markdown(f"**FAQ {j+1}**")
            q = st.text_input("Question", value=faq.get("question", ""), key=f"single_faq_q_{j}")
            a = st.text_area("Answer", value=faq.get("answer", ""), key=f"single_faq_a_{j}", height=80)
            updated_faqs.append({"question": q, "answer": a})
        content["faqs"] = updated_faqs

        if updated_faqs:
            v = validate_faqs(updated_faqs, brand_name=content.get("brand_name", ""))
            for vr in v.results:
                icon = "✅" if vr.passed else ("❌" if vr.severity == "error" else "⚠️")
                st.markdown(f"{icon} {vr.message}")

        # Add blank FAQ
        if st.button("+ Add FAQ"):
            content["faqs"].append({"question": "", "answer": ""})
            st.rerun()

    # --- Meta Description ---
    with tab_meta:
        meta = st.text_input(
            "Meta Description",
            value=content.get("meta_description", ""),
            key="single_meta",
        )
        content["meta_description"] = meta

        if meta:
            v = validate_meta_description(meta, content.get("primary_keyword", ""))
            for vr in v.results:
                icon = "✅" if vr.passed else ("❌" if vr.severity == "error" else "⚠️")
                st.markdown(f"{icon} {vr.message}")

    # --- Export / Copy ---
    with tab_export:
        st.markdown("### Copy-Paste Ready")
        st.markdown(f"**Collection:** {content.get('collection_name', '')}")
        st.markdown(f"**URL:** {content.get('collection_url', '')}")

        st.markdown("---")

        st.markdown("**SEO Title:**")
        st.code(content.get("seo_title", ""), language=None)

        st.markdown("**Collection Title (H1):**")
        st.code(content.get("collection_title", ""), language=None)

        st.markdown("**Meta Description:**")
        st.code(content.get("meta_description", ""), language=None)

        st.markdown("**Description (Markdown):**")
        st.code(content.get("description", ""), language="markdown")

        # HTML version
        desc_html = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            r'<a href="\2">\1</a>',
            content.get("description", ""),
        )
        st.markdown("**Description (HTML for Shopify):**")
        st.code(desc_html, language="html")

        if content.get("faqs"):
            st.markdown("**FAQs (HTML):**")
            faq_html = ""
            for faq in content["faqs"]:
                if faq.get("question"):
                    faq_html += f'<h3>{faq["question"]}</h3>\n<p>{faq.get("answer", "")}</p>\n\n'
            st.code(faq_html, language="html")

        # Full block for easy copy
        st.markdown("---")
        st.markdown("**Everything (plain text):**")
        full_text = f"""SEO Title: {content.get('seo_title', '')}
Collection Title: {content.get('collection_title', '')}
Meta Description: {content.get('meta_description', '')}

Description:
{content.get('description', '')}
"""
        if content.get("faqs"):
            full_text += "\nFAQs:\n"
            for faq in content["faqs"]:
                if faq.get("question"):
                    full_text += f"\nQ: {faq['question']}\nA: {faq.get('answer', '')}\n"

        st.code(full_text, language=None)

        # Shopify CSV for single URL
        st.markdown("---")
        if st.button("Download Shopify CSV"):
            from core.exporter import export_shopify_csv
            export_data = [{
                "collection_url": content.get("collection_url", ""),
                "collection_name": content.get("collection_name", ""),
                "content": content,
            }]
            buffer = export_shopify_csv(export_data)
            st.download_button(
                label="Download CSV",
                data=buffer,
                file_name=f"shopify_{content.get('collection_name', 'export').replace(' ', '_').lower()}.csv",
                mime="text/csv",
            )
