"""Brand Profile management — save per-client settings that persist across sessions."""

import streamlit as st

from core.app_state import get_state, save_state, clear_wip_state
from core.brand_profile import (
    BrandProfile,
    BrandPromptOverrides,
    list_profiles,
    load_profile,
    refresh_profile_sitemap,
    save_profile,
)
from core.sitemap import (
    ParsedSitemap,
    fetch_sitemap,
    parse_sitemap_file,
)
from core.text_utils import clean_keyword


def _clean_lines(raw: str) -> list[str]:
    """Split a textarea string into cleaned, non-empty lines."""
    return [cleaned for line in raw.split("\n") if (cleaned := clean_keyword(line.strip()))]


def _parse_dedup_overrides(raw: str) -> dict:
    """Parse `key=value` lines into a dict. Empty lines and lines without
    `=` are skipped silently. Keys are lowercased to match the lookup path
    in core.brief_builder._normalise_for_dedup."""
    out: dict[str, str] = {}
    for line in raw.split("\n"):
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = clean_keyword(key.strip()).lower()
        value = clean_keyword(value.strip())
        if key and value:
            out[key] = value
    return out

st.title("Brand Profiles")
st.markdown(
    "Save per-client settings — FAQ count, voice notes, custom rules, and alt-text preferences. "
    "Loaded profiles auto-fill the Content Studio."
)


def _render_sitemap_banner(profile: BrandProfile) -> None:
    """Render the site-structure status line for the active profile."""
    if profile.sitemap_parsed:
        try:
            parsed = ParsedSitemap.from_dict(profile.sitemap_parsed)
            st.info(
                f"📍 Site structure: {parsed.total_urls:,} URLs from sitemap "
                f"(fetched {profile.sitemap_fetched_at or 'unknown'})."
            )
        except Exception:
            st.warning("📍 Site structure: sitemap data unreadable — re-fetch recommended.")
    else:
        st.caption(
            "📍 Site structure: No sitemap loaded — link suggestions are limited to user-provided URLs."
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
    load_clicked = st.button("Load", width="stretch", disabled=(selected_name == "(new profile)"))

if load_clicked and selected_name != "(new profile)":
    loaded = load_profile(selected_name)
    if loaded:
        st.session_state["_bp_loaded"] = loaded
        st.success(f"Loaded profile for **{loaded.brand_name}**.")
        st.rerun()

st.markdown("---")

# ─── Build current profile from session or loaded ───────────────────────

state = get_state()
_loaded: BrandProfile = st.session_state.get("_bp_loaded", BrandProfile())

_render_sitemap_banner(_loaded)

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

# ─── Past feedback ───────────────────────────────────────────────────────

st.divider()
st.subheader("Past feedback")
st.caption(
    "Paste rejected content, client comments, or specific guidance from prior reviews. "
    "This gets injected into every prompt so the model learns from past mistakes."
)

bp_past_feedback = st.text_area(
    "Past feedback log",
    value=_loaded.past_feedback,
    height=200,
    key="bp_past_feedback",
    placeholder=(
        "e.g.\n"
        "- Client rejected last batch's FAQs for being too formal — keep them conversational.\n"
        "- Stop using 'perfect for' — flagged as filler in two reviews.\n"
        "- Top copy was over-pushing the warranty USP. Mention it once max, not every page.\n"
        "- The phrase 'discover our range' was rejected by Stanley reviewer."
    ),
    help=(
        "Freeform text. The model sees this as 'past feedback to apply'. "
        "Use natural language — it doesn't need to be structured."
    ),
)

extract_col, _ = st.columns([1, 3])
with extract_col:
    extract_clicked = st.button(
        "🔍 Extract bans from feedback",
        width="stretch",
        disabled=not bp_past_feedback.strip(),
        help="Uses Haiku to find specific phrases mentioned as rejected. You'll review before saving.",
    )

if extract_clicked:
    from core.feedback_extractor import extract_banned_phrases
    api_key = state.bifrost_api_key or st.session_state.get("api_key", "")
    if not api_key:
        st.error("Bifrost API key not set. Add it on the Home page first.")
    else:
        with st.spinner("Extracting banned phrases..."):
            try:
                extracted = extract_banned_phrases(api_key, bp_past_feedback)
                st.session_state["_pending_extracted_bans"] = extracted
            except Exception as e:
                st.error(f"Extraction failed: {e}")

pending = st.session_state.get("_pending_extracted_bans", [])
if pending:
    st.markdown("**Extracted phrases — review before adding to banned list:**")
    keep = []
    for i, phrase in enumerate(pending):
        if st.checkbox(f"`{phrase}`", value=True, key=f"keep_ban_{i}"):
            keep.append(phrase)
    if st.button("Add selected to banned phrases"):
        existing_bans = [b.strip() for b in (_loaded.prompt_overrides.banned_phrases or []) if b.strip()]
        also_in_area = st.session_state.get("bp_banned_phrases", "")
        area_bans = [b.strip() for b in also_in_area.split("\n") if b.strip()]
        all_existing = list(dict.fromkeys(existing_bans + area_bans))
        merged = all_existing + [p for p in keep if p not in all_existing]
        st.session_state["_bp_banned_phrases_merged"] = merged
        st.session_state.pop("_pending_extracted_bans", None)
        st.success(f"Added {len(keep)} phrases. Review the 'Banned phrases' field below and save.")
        st.rerun()

# ─── Site Structure (sitemap) ────────────────────────────────────────────

st.divider()
st.subheader("Site Structure (optional)")
st.caption(
    "Give the tool your sitemap so it can suggest real internal links — products, "
    "collections, and blog posts — instead of inventing paths."
)

_pending_parsed: ParsedSitemap | None = st.session_state.get("_bp_pending_sitemap")
if _pending_parsed is None and _loaded.sitemap_parsed:
    try:
        _pending_parsed = ParsedSitemap.from_dict(_loaded.sitemap_parsed)
    except Exception:
        _pending_parsed = None

sitemap_url_input_default = _loaded.sitemap_url

sm_tab_fetch, sm_tab_upload = st.tabs(["Fetch from URL", "Upload File"])

with sm_tab_fetch:
    bp_sitemap_url = st.text_input(
        "Sitemap URL",
        value=sitemap_url_input_default,
        key="bp_sitemap_url",
        placeholder="https://yourstore.com/sitemap.xml",
        help="Shopify stores typically expose a sitemap index at <store>/sitemap.xml.",
    )
    if st.button("🔄 Fetch sitemap", disabled=not bp_sitemap_url.strip()):
        with st.spinner("Fetching sitemap…"):
            parsed = fetch_sitemap(bp_sitemap_url.strip())
        if parsed.error and parsed.total_urls == 0:
            st.error(f"Fetch failed: {parsed.error}")
        else:
            if parsed.error:
                st.warning(parsed.error)
            st.session_state["_bp_pending_sitemap"] = parsed
            st.session_state["_bp_pending_sitemap_source_url"] = bp_sitemap_url.strip()
            _pending_parsed = parsed

with sm_tab_upload:
    uploaded_sm = st.file_uploader(
        "Sitemap file (.xml or .xml.gz)",
        type=["xml", "gz"],
        key="bp_sitemap_upload",
    )
    if uploaded_sm and st.button("Parse uploaded file"):
        parsed = parse_sitemap_file(uploaded_sm.read(), source_url=uploaded_sm.name)
        if parsed.error and parsed.total_urls == 0:
            st.error(f"Parse failed: {parsed.error}")
        else:
            if parsed.error:
                st.warning(parsed.error)
            st.session_state["_bp_pending_sitemap"] = parsed
            st.session_state["_bp_pending_sitemap_source_url"] = ""  # uploaded → no refresh URL
            _pending_parsed = parsed

if _pending_parsed and _pending_parsed.total_urls:
    st.success(
        f"✅ Parsed {_pending_parsed.total_urls:,} URLs — "
        f"{len(_pending_parsed.products):,} products · "
        f"{len(_pending_parsed.collections):,} collections · "
        f"{len(_pending_parsed.blog_posts):,} blog posts · "
        f"{len(_pending_parsed.pages):,} pages · "
        f"{len(_pending_parsed.other):,} other"
    )
    if _pending_parsed.fetched_at:
        st.caption(f"Fetched: {_pending_parsed.fetched_at}")

    with st.expander("Show URL preview", expanded=False):
        import pandas as _pd

        def _preview(rows, label):
            if not rows:
                return
            st.markdown(f"**{label} (first 20)**")
            st.dataframe(
                _pd.DataFrame(
                    [{"title": r.title_guess, "url": r.url} for r in rows[:20]]
                ),
                width="stretch",
                hide_index=True,
            )

        _preview(_pending_parsed.products, "Products")
        _preview(_pending_parsed.collections, "Collections")
        _preview(_pending_parsed.blog_posts, "Blog posts")
        _preview(_pending_parsed.pages, "Pages")

    refresh_disabled = not _loaded.sitemap_url
    if st.button(
        "Refresh sitemap (re-fetch from URL)",
        disabled=refresh_disabled,
        help="Re-fetches the sitemap from the saved URL. Disabled for uploaded files.",
    ):
        with st.spinner("Re-fetching sitemap…"):
            updated, err = refresh_profile_sitemap(_loaded)
        if err:
            st.warning(f"Refresh had issues: {err}")
        save_profile(updated)
        st.session_state["_bp_loaded"] = updated
        st.session_state["_bp_pending_sitemap"] = ParsedSitemap.from_dict(updated.sitemap_parsed)
        st.success("Sitemap refreshed.")
        st.rerun()

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

    bp_humanize_by_default = st.checkbox(
        "Humanise content by default for this brand",
        value=bool(_loaded.humanize_by_default),
        key="bp_humanize_by_default",
        help=(
            "When checked, the humaniser pass runs automatically on every "
            "generation for this brand. Can still be toggled per-session in "
            "the Content Studio."
        ),
    )

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
    _merged_bans = st.session_state.pop("_bp_banned_phrases_merged", None)
    _default_bans = "\n".join(_merged_bans) if _merged_bans is not None else "\n".join(overrides.banned_phrases or [])
    bp_banned_phrases = st.text_area(
        "Banned phrases (one per line)",
        value=_default_bans,
        key="bp_banned_phrases",
        height=100,
        placeholder="e.g.\nperfect for\ndiscover our range\nwhether you're looking for",
        help="These phrases will never appear in generated content. Add manually or extract from feedback above.",
    )

with st.expander("🔧 Dedup overrides (advanced)", expanded=False):
    st.caption(
        "By default the tool deduplicates keywords like 'shirt' / 'shirts'. "
        "If your brand targets different intents for singular vs plural variants, "
        "add overrides here — one per line in the format `keyword=normalised_form`. "
        "Example: `gold cap=gold-cap-distinct` keeps it separate from `gold caps`."
    )
    _existing_dedup_lines = "\n".join(
        f"{k}={v}" for k, v in (overrides.dedup_overrides or {}).items()
    )
    bp_dedup_overrides = st.text_area(
        "Dedup overrides",
        value=_existing_dedup_lines,
        key="bp_dedup_overrides",
        height=100,
        placeholder="gold cap=gold-cap-distinct\ngold caps=gold-caps-distinct",
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
        # Carry forward existing sitemap unless a new one is pending in the session.
        pending_sm = st.session_state.get("_bp_pending_sitemap")
        if pending_sm is not None:
            sitemap_parsed_dict = pending_sm.to_dict()
            sitemap_fetched_at = pending_sm.fetched_at
            sitemap_url_to_save = st.session_state.get(
                "_bp_pending_sitemap_source_url", _loaded.sitemap_url
            )
        else:
            sitemap_parsed_dict = _loaded.sitemap_parsed
            sitemap_fetched_at = _loaded.sitemap_fetched_at
            sitemap_url_to_save = bp_sitemap_url.strip() if "bp_sitemap_url" in st.session_state else _loaded.sitemap_url

        profile = BrandProfile(
            brand_name=clean_keyword(bp_brand_name.strip()),
            store_url=bp_store_url.strip(),
            brand_usps=_clean_lines(bp_usps),
            voice_notes=clean_keyword(bp_voice_notes.strip()),
            target_market=bp_target_market,
            faq_count=int(bp_faq_count),
            past_feedback=clean_keyword(bp_past_feedback.strip()),
            humanize_by_default=bool(bp_humanize_by_default),
            sitemap_url=sitemap_url_to_save,
            sitemap_parsed=sitemap_parsed_dict,
            sitemap_fetched_at=sitemap_fetched_at,
            prompt_overrides=BrandPromptOverrides(
                brand_custom_rules=clean_keyword(bp_custom_rules.strip()),
                voice_examples=clean_keyword(bp_voice_examples.strip()),
                alt_text_rules=clean_keyword(bp_alt_rules.strip()),
                alt_text_examples=clean_keyword(bp_alt_examples.strip()),
                banned_phrases=_clean_lines(bp_banned_phrases),
                dedup_overrides=_parse_dedup_overrides(bp_dedup_overrides),
            ),
        )
        save_profile(profile)
        st.session_state["_bp_loaded"] = profile
        st.session_state.pop("_bp_pending_sitemap", None)
        st.session_state.pop("_bp_pending_sitemap_source_url", None)
        st.success(f"Profile saved for **{profile.brand_name}**.")

with sc2:
    def _build_apply_payload() -> dict:
        return {
            "client_profile": {
                "brand_name": clean_keyword(bp_brand_name.strip()),
                "store_url": bp_store_url.strip(),
                "brand_usps": _clean_lines(bp_usps),
                "voice_notes": clean_keyword(bp_voice_notes.strip()),
                "target_market": bp_target_market,
                "faq_count": int(bp_faq_count),
                "past_feedback": clean_keyword(bp_past_feedback.strip()),
                "humanize_by_default": bool(bp_humanize_by_default),
            },
            "prompt_overrides": {
                "brand_custom_rules": clean_keyword(bp_custom_rules.strip()),
                "voice_examples": clean_keyword(bp_voice_examples.strip()),
                "alt_text_rules": clean_keyword(bp_alt_rules.strip()),
                "alt_text_examples": clean_keyword(bp_alt_examples.strip()),
                "banned_phrases": _clean_lines(bp_banned_phrases),
                "dedup_overrides": _parse_dedup_overrides(bp_dedup_overrides),
            },
        }

    def _apply_brand_payload(payload: dict) -> None:
        from core.session_state import ClientProfile, PromptOverrides
        # Re-fetch state so we always write to the current instance —
        # clear_wip_state replaces the AppState on the brand-switch path,
        # which would invalidate any closure-captured reference.
        current = get_state()
        current.client_profile = ClientProfile.model_validate(payload["client_profile"])
        current.prompt_overrides = PromptOverrides.model_validate(payload["prompt_overrides"])
        # Apply the brand's humaniser default to the session toggle so the
        # Content Studio picks it up on first render.
        current.humanize_enabled = bool(
            payload["client_profile"].get("humanize_by_default", False)
        )
        # Push sitemap into session so Data Input + Single URL Writer can pick it up.
        pending_sm = st.session_state.get("_bp_pending_sitemap")
        if pending_sm is not None:
            current.sitemap_parsed = pending_sm.to_dict()
        elif _loaded.sitemap_parsed:
            current.sitemap_parsed = _loaded.sitemap_parsed
        save_state(current)

    if st.button("📋 Apply to Session", help="Load this profile's settings into the Content Studio session"):
        has_wip = any(
            getattr(state, k)
            for k in (
                "collection_groups",
                "scored_collections",
                "batch_collections",
                "generated_content",
                "audit_results",
                "scrape_results",
                "single_url_content",
            )
        )
        if has_wip:
            st.session_state["_pending_brand_switch"] = _build_apply_payload()
        else:
            _apply_brand_payload(_build_apply_payload())
            st.toast("Profile applied to session.", icon="✅")

def _summarise_wip() -> list[str]:
    """Return a human-readable inventory of what's currently in WIP state."""
    lines = []

    collections = state.collection_groups or []
    if collections:
        upload_format = state.source_format or "unknown format"
        lines.append(
            f"- **{len(collections)} collections** from uploaded data ({upload_format})"
        )

    batch = state.batch_collections or []
    if batch:
        lines.append(f"- **{len(batch)} collections** in current batch")

    generated = state.generated_content or {}
    if generated:
        approved_count = sum(1 for c in generated.values() if c.get("approved"))
        lines.append(
            f"- Generated content for **{len(generated)} collections** "
            f"({approved_count} approved)"
        )

    audits = state.audit_results or {}
    if audits:
        lines.append(f"- **{len(audits)} audit results**")

    single = state.single_url_content or {}
    if single:
        name = single.get("collection_name", "unnamed")
        lines.append(f"- 1 Single URL Writer draft (*{name}*)")

    tracker = state.implementation_tracker or {}
    if tracker:
        lines.append(f"- **{len(tracker)} implementation-tracker entries**")

    return lines


if st.session_state.get("_pending_brand_switch"):
    _wip_summary = _summarise_wip()
    if _wip_summary:
        st.warning(
            "**Switching brands will clear all in-progress work:**\n\n"
            + "\n".join(_wip_summary)
            + "\n\nThis cannot be undone."
        )
    else:
        st.warning(
            "Switching brands will clear any in-progress work. "
            "This cannot be undone."
        )
    _bs1, _bs2 = st.columns(2)
    with _bs1:
        if st.button("✅ Clear and switch", type="primary", key="confirm_brand_switch"):
            payload = st.session_state.pop("_pending_brand_switch")
            clear_wip_state()
            _apply_brand_payload(payload)
            st.success("Switched to new brand.")
            st.rerun()
    with _bs2:
        if st.button("Cancel", key="cancel_brand_switch"):
            st.session_state.pop("_pending_brand_switch", None)
            st.rerun()
