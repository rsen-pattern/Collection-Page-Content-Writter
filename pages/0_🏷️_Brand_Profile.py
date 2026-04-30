"""Brand Profile management — save per-client settings that persist across sessions."""

import streamlit as st

from core.brand_profile import (
    BrandProfile,
    BrandPromptOverrides,
    list_profiles,
    load_profile,
    save_profile,
)

st.title("Brand Profiles")
st.markdown(
    "Save per-client settings — FAQ count, voice notes, custom rules, and alt-text preferences. "
    "Loaded profiles auto-fill the Content Studio."
)

# ─── Load existing profile ───────────────────────────────────────────────

saved_names = list_profiles()

st.markdown("## Load a Saved Profile")

lc1, lc2 = st.columns([3, 1])
with lc1:
    selected_name = st.selectbox(
        "Saved profiles",
        ["(new profile)"] + saved_names,
        label_visibility="collapsed",
    )
with lc2:
    load_clicked = st.button("Load", use_container_width=True, disabled=(selected_name == "(new profile)"))

if load_clicked and selected_name != "(new profile)":
    loaded = load_profile(selected_name)
    if loaded:
        st.session_state["_bp_loaded"] = loaded
        st.success(f"Loaded profile for **{loaded.brand_name}**.")
        st.rerun()

st.markdown("---")

# ─── Build current profile from session or loaded ───────────────────────

_loaded: BrandProfile = st.session_state.get("_bp_loaded", BrandProfile())

st.markdown("## Profile Details")

pc1, pc2 = st.columns(2)

with pc1:
    bp_brand_name = st.text_input(
        "Brand / Store Name *",
        value=_loaded.brand_name,
        key="bp_brand_name",
    )
    bp_store_url = st.text_input(
        "Store URL",
        value=_loaded.store_url,
        key="bp_store_url",
        placeholder="https://example.com",
    )
    bp_target_market = st.selectbox(
        "Target Market",
        ["UK", "US", "AU", "CA", "EU", "Global"],
        index=["UK", "US", "AU", "CA", "EU", "Global"].index(_loaded.target_market),
        key="bp_target_market",
    )

with pc2:
    bp_usps = st.text_area(
        "Brand USPs (one per line)",
        value="\n".join(_loaded.brand_usps),
        key="bp_usps",
        height=110,
        help="3-5 bullet points. These get woven into every piece of generated content.",
    )
    bp_voice_notes = st.text_area(
        "Brand Voice Notes",
        value=_loaded.voice_notes,
        key="bp_voice_notes",
        height=70,
        placeholder="e.g. Warm, approachable. Speaks to style-conscious women 25-45.",
    )

# ─── FAQ settings ────────────────────────────────────────────────────────

with st.expander("❓ FAQ Settings", expanded=False):
    bp_faq_count = st.number_input(
        "Default FAQ count for this brand",
        min_value=3,
        max_value=8,
        value=int(_loaded.faq_count if _loaded.faq_count else 4),
        key="bp_faq_count",
        help="Default number of FAQs to generate per collection. Methodology range is 3-5.",
    )
    st.caption("This overrides the global default (4) for all collections generated under this profile.")

# ─── Prompt overrides ────────────────────────────────────────────────────

overrides = _loaded.prompt_overrides

with st.expander("✏️ Prompt Override Rules", expanded=False):
    bp_custom_rules = st.text_area(
        "Brand-specific content rules",
        value=overrides.brand_custom_rules,
        key="bp_custom_rules",
        height=100,
        placeholder="e.g. Always mention Lifetime Guarantee in the opening paragraph.",
    )
    bp_voice_examples = st.text_area(
        "Approved voice examples",
        value=overrides.voice_examples,
        key="bp_voice_examples",
        height=80,
        placeholder="Paste examples of approved copy in the brand's voice (one per line).",
    )

# ─── Alt text settings ───────────────────────────────────────────────────

with st.expander("🖼️ Product Image Alt Text", expanded=False):
    bp_alt_rules = st.text_area(
        "Custom rules for alt text",
        value=overrides.alt_text_rules,
        key="bp_alt_rules",
        height=100,
        placeholder="e.g. Always mention the colour first. Include the size if part of the product name.",
    )
    bp_alt_examples = st.text_area(
        "Approved alt text examples",
        value=overrides.alt_text_examples,
        key="bp_alt_examples",
        height=80,
        placeholder="One per line — e.g. Charcoal stainless steel tumbler with handle",
    )

# ─── Save ────────────────────────────────────────────────────────────────

st.markdown("---")

sc1, sc2 = st.columns(2)

with sc1:
    if st.button("💾 Save Profile", type="primary", disabled=not bool(bp_brand_name.strip())):
        profile = BrandProfile(
            brand_name=bp_brand_name.strip(),
            store_url=bp_store_url.strip(),
            brand_usps=[u.strip() for u in bp_usps.strip().split("\n") if u.strip()],
            voice_notes=bp_voice_notes.strip(),
            target_market=bp_target_market,
            faq_count=int(bp_faq_count),
            prompt_overrides=BrandPromptOverrides(
                brand_custom_rules=bp_custom_rules.strip(),
                voice_examples=bp_voice_examples.strip(),
                alt_text_rules=bp_alt_rules.strip(),
                alt_text_examples=bp_alt_examples.strip(),
            ),
        )
        save_profile(profile)
        st.session_state["_bp_loaded"] = profile
        st.success(f"Profile saved for **{profile.brand_name}**.")

with sc2:
    if st.button("📋 Apply to Session", help="Load this profile's settings into the Content Studio session"):
        brand_usps = [u.strip() for u in bp_usps.strip().split("\n") if u.strip()]
        st.session_state.client_profile = {
            "brand_name": bp_brand_name.strip(),
            "store_url": bp_store_url.strip(),
            "brand_usps": brand_usps,
            "voice_notes": bp_voice_notes.strip(),
            "target_market": bp_target_market,
            "faq_count": int(bp_faq_count),
        }
        st.session_state["prompt_overrides"] = {
            "brand_custom_rules": bp_custom_rules.strip(),
            "voice_examples": bp_voice_examples.strip(),
            "alt_text_rules": bp_alt_rules.strip(),
            "alt_text_examples": bp_alt_examples.strip(),
        }
        st.success("Profile applied to session. Head to the Content Studio to generate content.")
