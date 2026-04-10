"""Step 4: Content Studio — Generate, review, and refine content."""

import re
import streamlit as st


st.title("Step 4: Content Studio")

if not st.session_state.get("batch_collections"):
    st.warning("No batch selected. Please complete Step 2 first.")
    st.stop()

if not st.session_state.get("bifrost_api_key"):
    st.warning("Please set your Bifrost API key in the sidebar on the main page.")
    st.stop()

from core.brief_builder import build_brief, ContentBrief
from core.content_generator import generate_content, humanize_content, GeneratedContent
from core.validator import (
    validate_description,
    validate_seo_title,
    validate_collection_title,
    validate_meta_description,
    validate_faqs,
)


def _api_kwargs() -> dict:
    """Common kwargs for generate_content calls."""
    return {
        "api_key": st.session_state.bifrost_api_key,
        "base_url": st.session_state.get("bifrost_base_url", "https://bifrost.pattern.com"),
        "model": st.session_state.get("selected_model", "anthropic/claude-sonnet-4-6"),
    }


def _handle_result(result_tuple):
    """Unpack (result, used_model) and show fallback info if needed."""
    result, used_model = result_tuple
    selected = st.session_state.get("selected_model", "")
    if used_model != selected:
        st.info(f"Fallback: used **{used_model}** (selected model failed)")
    return result


batch = st.session_state.batch_collections
client = st.session_state.client_profile

# Humanizer toggle
humanize_enabled = st.checkbox(
    "Run humanizer pass on generated content",
    value=st.session_state.get("humanize_enabled", False),
    key="humanize_toggle",
    help="When enabled, a second LLM call rewrites content to remove AI artifacts and improve natural readability.",
)
st.session_state.humanize_enabled = humanize_enabled

# --- 4.1 Content Brief Review ---
st.markdown("## Content Briefs")

# Build briefs for each collection
for i, col in enumerate(batch):
    brief_key = col["collection_url"]

    if brief_key not in st.session_state.content_briefs:
        kw_difficulty = None
        for kw in col.get("secondary_keywords", []):
            if isinstance(kw, dict) and "keyword_difficulty" in kw:
                kw_difficulty = kw["keyword_difficulty"]
                break

        brief = build_brief(
            collection_url=col["collection_url"],
            collection_name=col["collection_name"],
            primary_keyword=col["primary_keyword"],
            primary_keyword_volume=col.get("primary_keyword_volume"),
            secondary_keywords=col.get("secondary_keywords", []),
            brand_usps=client.get("brand_usps", []),
            brand_name=client.get("brand_name", ""),
            store_url=client.get("store_url", ""),
            target_market=client.get("target_market", "UK"),
            voice_notes=client.get("voice_notes", ""),
            keyword_difficulty=kw_difficulty,
        )
        st.session_state.content_briefs[brief_key] = brief


# --- 4.2 & 4.3 Generation & Editing ---
for i, col in enumerate(batch):
    brief_key = col["collection_url"]
    brief = st.session_state.content_briefs[brief_key]
    content_key = col["collection_url"]
    content = st.session_state.generated_content.get(content_key, {})

    st.markdown("---")
    st.markdown(f"## {col['collection_name']}")

    tab_brief, tab_desc, tab_faq, tab_titles, tab_meta = st.tabs(
        ["Brief", "Description", "FAQs", "Titles", "Meta"]
    )

    with tab_brief:
        bc1, bc2 = st.columns(2)
        with bc1:
            st.markdown(f"**Primary Keyword:** {brief.primary_keyword}")
            st.markdown(f"**Volume:** {brief.primary_keyword_volume or 'N/A'}")
            st.markdown(f"**Target Word Count:** {brief.target_word_count}")
            st.markdown(f"**Secondary Keywords:** {', '.join(brief.secondary_keywords[:5])}")

        with bc2:
            st.markdown(f"**Brand USPs:** {', '.join(brief.brand_usps)}")
            st.markdown(f"**Target Market:** {brief.target_market}")

            products_text = st.text_area(
                "Products to Link (one per line: name|url)",
                value="\n".join(f"{p['name']}|{p['url']}" for p in brief.products_to_link) if brief.products_to_link else "",
                key=f"products_{i}",
                height=80,
            )
            related_text = st.text_area(
                "Related Collections (one per line: name|url)",
                value="\n".join(f"{c['name']}|{c['url']}" for c in brief.related_collections) if brief.related_collections else "",
                key=f"related_{i}",
                height=60,
            )
            paa_text = st.text_area(
                "People Also Ask Questions (one per line)",
                value="\n".join(brief.paa_questions),
                key=f"paa_{i}",
                height=60,
            )

            if products_text.strip():
                products = []
                for line in products_text.strip().split("\n"):
                    parts = line.split("|", 1)
                    if len(parts) == 2:
                        products.append({"name": parts[0].strip(), "url": parts[1].strip()})
                brief.products_to_link = products

            if related_text.strip():
                related = []
                for line in related_text.strip().split("\n"):
                    parts = line.split("|", 1)
                    if len(parts) == 2:
                        related.append({"name": parts[0].strip(), "url": parts[1].strip()})
                brief.related_collections = related

            if paa_text.strip():
                brief.paa_questions = [q.strip() for q in paa_text.strip().split("\n") if q.strip()]

        if st.button("Generate Full Brief Package", key=f"gen_full_{i}", type="primary"):
            with st.spinner("Generating content..."):
                try:
                    result = _handle_result(generate_content(
                        **_api_kwargs(),
                        brief=brief,
                        generation_type="full",
                        batch_faq_topics=st.session_state.batch_faq_topics,
                    ))
                    generated = {
                        "seo_title": result.seo_title,
                        "collection_title": result.collection_title,
                        "description": result.description,
                        "meta_description": result.meta_description,
                        "faqs": result.faqs,
                        "approved": False,
                    }
                    # Humanizer pass if enabled
                    if st.session_state.get("humanize_enabled"):
                        with st.spinner("Humanizing content..."):
                            if generated["description"]:
                                h_text, h_model = humanize_content(
                                    **_api_kwargs(),
                                    content_text=generated["description"],
                                    brand_name=client.get("brand_name", ""),
                                    voice_notes=client.get("voice_notes", ""),
                                )
                                generated["description"] = h_text
                    st.session_state.generated_content[content_key] = generated
                    for faq in result.faqs:
                        st.session_state.batch_faq_topics.append(faq.get("question", ""))
                    st.rerun()
                except Exception as e:
                    st.error(f"Generation failed: {e}")

    if not content:
        continue

    with tab_desc:
        desc_text = st.text_area(
            "Description",
            value=content.get("description", ""),
            height=200,
            key=f"desc_{i}",
        )
        content["description"] = desc_text

        desc_validation = validate_description(
            desc_text, brief.primary_keyword, brief.secondary_keywords, brief.brand_usps,
        )

        wc = len(desc_text.split()) if desc_text.strip() else 0
        vc1, vc2, vc3, vc4 = st.columns(4)
        with vc1:
            st.metric("Word Count", f"{wc}/{brief.target_word_count}")
        with vc2:
            kw_found = sum(1 for kw in brief.secondary_keywords if kw.lower() in desc_text.lower())
            st.metric("Keywords Found", f"{kw_found}/{len(brief.secondary_keywords)}")
        with vc3:
            link_count = len(re.findall(r"\[.*?\]\(.*?\)", desc_text))
            st.metric("Internal Links", link_count)
        with vc4:
            usp_count = sum(
                1 for usp in brief.brand_usps
                if any(w in desc_text.lower() for w in usp.lower().split() if len(w) > 3)
            )
            st.metric("USPs Referenced", f"{usp_count}/{len(brief.brand_usps)}")

        for vr in desc_validation.results:
            icon = "✅" if vr.passed else ("❌" if vr.severity == "error" else "⚠️")
            st.markdown(f"{icon} {vr.message}")

        desc_btn1, desc_btn2 = st.columns(2)
        with desc_btn1:
            if st.button("Regenerate Description", key=f"regen_desc_{i}"):
                with st.spinner("Regenerating..."):
                    try:
                        result = _handle_result(generate_content(
                            **_api_kwargs(), brief=brief, generation_type="description",
                        ))
                        content["description"] = result.description
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")
        with desc_btn2:
            if st.button("Humanize Description", key=f"humanize_desc_{i}"):
                with st.spinner("Humanizing..."):
                    try:
                        h_text, h_model = humanize_content(
                            **_api_kwargs(),
                            content_text=content.get("description", ""),
                            brand_name=client.get("brand_name", ""),
                            voice_notes=client.get("voice_notes", ""),
                        )
                        content["description"] = h_text
                        selected = st.session_state.get("selected_model", "")
                        if h_model != selected:
                            st.info(f"Humanizer fallback: used **{h_model}**")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Humanize failed: {e}")

    with tab_faq:
        faqs = content.get("faqs", [])
        updated_faqs = []
        for j, faq in enumerate(faqs):
            st.markdown(f"**FAQ {j+1}**")
            q = st.text_input("Question", value=faq.get("question", ""), key=f"faq_q_{i}_{j}")
            a = st.text_area("Answer", value=faq.get("answer", ""), key=f"faq_a_{i}_{j}", height=80)
            updated_faqs.append({"question": q, "answer": a})
        content["faqs"] = updated_faqs

        faq_validation = validate_faqs(
            updated_faqs,
            brand_name=client.get("brand_name", ""),
            batch_faq_topics=[
                t for t in st.session_state.batch_faq_topics
                if t not in [f.get("question", "") for f in updated_faqs]
            ],
        )
        for vr in faq_validation.results:
            icon = "✅" if vr.passed else ("❌" if vr.severity == "error" else "⚠️")
            st.markdown(f"{icon} {vr.message}")

        if st.button("Regenerate FAQs", key=f"regen_faqs_{i}"):
            with st.spinner("Regenerating..."):
                try:
                    result = _handle_result(generate_content(
                        **_api_kwargs(), brief=brief, generation_type="faqs",
                        batch_faq_topics=st.session_state.batch_faq_topics,
                    ))
                    content["faqs"] = result.faqs
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")

    with tab_titles:
        tc1, tc2 = st.columns(2)
        with tc1:
            seo_title = st.text_input("SEO Title", value=content.get("seo_title", ""), key=f"seo_title_{i}")
            content["seo_title"] = seo_title
            title_validation = validate_seo_title(seo_title, brief.primary_keyword, h1=content.get("collection_title", ""), brand_name=client.get("brand_name", ""))
            for vr in title_validation.results:
                icon = "✅" if vr.passed else ("❌" if vr.severity == "error" else "⚠️")
                st.markdown(f"{icon} {vr.message}")

        with tc2:
            h1 = st.text_input("Collection Title (H1)", value=content.get("collection_title", ""), key=f"h1_{i}")
            content["collection_title"] = h1
            h1_validation = validate_collection_title(h1, brief.primary_keyword, seo_title=content.get("seo_title", ""))
            for vr in h1_validation.results:
                icon = "✅" if vr.passed else ("❌" if vr.severity == "error" else "⚠️")
                st.markdown(f"{icon} {vr.message}")

        if st.button("Regenerate Titles", key=f"regen_titles_{i}"):
            with st.spinner("Regenerating..."):
                try:
                    result = _handle_result(generate_content(
                        **_api_kwargs(), brief=brief, generation_type="titles",
                    ))
                    content["seo_title"] = result.seo_title
                    content["collection_title"] = result.collection_title
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")

    with tab_meta:
        meta_desc = st.text_input("Meta Description", value=content.get("meta_description", ""), key=f"meta_desc_{i}")
        content["meta_description"] = meta_desc
        meta_validation = validate_meta_description(meta_desc, brief.primary_keyword)
        for vr in meta_validation.results:
            icon = "✅" if vr.passed else ("❌" if vr.severity == "error" else "⚠️")
            st.markdown(f"{icon} {vr.message}")

    # Approval
    st.markdown("---")
    ac1, ac2, ac3 = st.columns(3)
    with ac1:
        if st.button("Approve", key=f"approve_{i}", type="primary"):
            content["approved"] = True
            st.success("Content approved!")
    with ac2:
        if content.get("approved"):
            st.success("Approved")
    with ac3:
        if st.button("Copy All to Clipboard", key=f"copy_{i}"):
            clipboard_text = f"""SEO Title: {content.get('seo_title', '')}
Collection Title: {content.get('collection_title', '')}
Meta Description: {content.get('meta_description', '')}

Description:
{content.get('description', '')}

FAQs:
"""
            for faq in content.get("faqs", []):
                clipboard_text += f"\nQ: {faq.get('question', '')}\nA: {faq.get('answer', '')}\n"
            st.code(clipboard_text, language=None)

    st.session_state.generated_content[content_key] = content

# Batch actions
st.markdown("---")
st.markdown("## Batch Actions")

ba1, ba2 = st.columns(2)
with ba1:
    if st.button("Generate All (Full Brief)", type="primary"):
        progress = st.progress(0)
        for idx, col in enumerate(batch):
            bk = col["collection_url"]
            if bk in st.session_state.generated_content:
                progress.progress((idx + 1) / len(batch))
                continue
            brief = st.session_state.content_briefs.get(bk)
            if brief:
                with st.spinner(f"Generating {col['collection_name']}..."):
                    try:
                        result = _handle_result(generate_content(
                            **_api_kwargs(),
                            brief=brief,
                            generation_type="full",
                            batch_faq_topics=st.session_state.batch_faq_topics,
                        ))
                        generated = {
                            "seo_title": result.seo_title,
                            "collection_title": result.collection_title,
                            "description": result.description,
                            "meta_description": result.meta_description,
                            "faqs": result.faqs,
                            "approved": False,
                        }
                        # Humanizer pass if enabled
                        if st.session_state.get("humanize_enabled") and generated["description"]:
                            with st.spinner(f"Humanizing {col['collection_name']}..."):
                                h_text, _ = humanize_content(
                                    **_api_kwargs(),
                                    content_text=generated["description"],
                                    brand_name=client.get("brand_name", ""),
                                    voice_notes=client.get("voice_notes", ""),
                                )
                                generated["description"] = h_text
                        st.session_state.generated_content[bk] = generated
                        for faq in result.faqs:
                            st.session_state.batch_faq_topics.append(faq.get("question", ""))
                    except Exception as e:
                        st.error(f"Failed for {col['collection_name']}: {e}")
            progress.progress((idx + 1) / len(batch))
        st.rerun()

with ba2:
    if st.button("Approve All"):
        for col in batch:
            ck = col["collection_url"]
            if ck in st.session_state.generated_content:
                st.session_state.generated_content[ck]["approved"] = True
        st.success("All generated content approved!")
        st.rerun()
