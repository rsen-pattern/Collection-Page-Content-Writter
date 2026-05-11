"""Collection SEO Engine — Main Streamlit entry point with grouped navigation."""

import json
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="Collection SEO Engine",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_model_config():
    """Load available models from config."""
    config_path = Path(__file__).parent / "config" / "models.json"
    with open(config_path) as f:
        return json.load(f)


def get_model_options():
    """Build model selection options in provider_id/model_id format."""
    config = load_model_config()
    options = []
    labels = {}
    for provider_name, data in config["providers"].items():
        provider_id = data["provider_id"]
        for model in data["models"]:
            bifrost_id = f"{provider_id}/{model['id']}"
            options.append(bifrost_id)
            labels[bifrost_id] = f"{model['label']}  ({provider_name})"
    return options, labels, config.get("default_model", "anthropic/claude-sonnet-4-6")


def get_secret(key: str, default: str = "") -> str:
    """Get a value from st.secrets with fallback to default."""
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError, AttributeError):
        return default


_STATE_KEY = "_app_state_v1"

# Transient UI state — Streamlit-managed widget state and short-lived flags
# that don't belong in AppState. Listed so clear_wip_state can sweep them.
_TRANSIENT_UI_KEYS = (
    "_bp_pending_sitemap",
    "_bp_pending_sitemap_source_url",
    "_bp_pending_extracted_bans",
    "_bp_banned_phrases_merged",
    "_bp_loaded",
    "_single_prefill_name",
    "_single_prefill_products",
    "_single_prefill_related",
    "_single_prefill_blogs",
    "_single_scraped_products",
    "_existing_top",
    "_existing_bottom",
    "_ai_diagnosis",
    "_pending_generate_all",
    "_pending_brand_switch",
    "_last_used_model",
)


def get_state():
    """Return the typed :class:`AppState` for this session.

    Auto-migrates from the legacy flat-namespace shape on first call.
    Always returns a valid AppState — never raises.
    """
    from core.session_state import AppState, parse_lenient

    # New shape already in place — return it.
    existing = st.session_state.get(_STATE_KEY)
    if isinstance(existing, AppState):
        return existing

    # Legacy migration: any of these keys living at the top level means
    # this session was started before the typed shape existed.
    legacy_keys = {
        "client_profile",
        "raw_data",
        "normalized_data",
        "collection_groups",
        "batch_collections",
        "generated_content",
        "bifrost_api_key",
        "bifrost_base_url",
        "selected_model",
    }
    present = [k for k in legacy_keys if k in st.session_state]
    if present:
        from core.telemetry import log_event
        log_event("session_state_legacy_migration", source_keys_present=present)
        raw = {
            k: st.session_state[k]
            for k in list(st.session_state.keys())
            if k in AppState.model_fields
        }
        state = parse_lenient(raw)
        st.session_state[_STATE_KEY] = state
        # Drop legacy keys so reads can't split-brain across both shapes.
        for k in list(st.session_state.keys()):
            if k in AppState.model_fields:
                del st.session_state[k]
        return state

    # Fresh session — build defaults from secrets where applicable.
    state = AppState()
    state.bifrost_api_key = get_secret("BIFROST_API_KEY") or get_secret("BIFROST_KEY")
    state.bifrost_base_url = get_secret("BIFROST_BASE_URL", "https://bifrost.pattern.com")
    state.selected_model = get_secret("BIFROST_DEFAULT_MODEL", "anthropic/claude-sonnet-4-6")
    state.dataforseo_login = get_secret("DATAFORSEO_LOGIN")
    state.dataforseo_password = get_secret("DATAFORSEO_PASSWORD")
    state.webscraping_ai_key = get_secret("WEBSCRAPING_AI_KEY", "")
    state.scraperapi_key = get_secret("SCRAPERAPI_KEY", "")
    st.session_state[_STATE_KEY] = state
    return state


def save_state(state) -> None:
    """Persist mutations made to the AppState. Runs invariant validators.

    Pages must call this after mutating fields. Failing to call save_state
    after a mutation means the next get_state() will return the unsaved
    version only within the same script run — across reruns, mutations to
    mutable fields (lists, dicts) are still visible because Python
    references are shared, but invariants haven't been re-checked.
    """
    from core.session_state import AppState

    try:
        validated = AppState.model_validate(state.model_dump())
        st.session_state[_STATE_KEY] = validated
    except Exception as e:
        from core.telemetry import log_event
        log_event("session_state_save_failed", error=str(e)[:200])
        # Keep the unvalidated state rather than losing user work.
        st.session_state[_STATE_KEY] = state


def clear_wip_state() -> None:
    """Reset all work-in-progress fields to defaults.

    Preserves credentials, the selected model, and the active brand profile
    (anything in :data:`core.session_state.PERSISTENT_FIELDS`). Also drops
    transient UI keys (``_pending_brand_switch``, ``_bp_pending_sitemap``,
    etc.) since they belong to the outgoing brand.
    """
    from core.session_state import AppState, PERSISTENT_FIELDS

    current = get_state()
    preserved = {
        name: getattr(current, name) for name in PERSISTENT_FIELDS
    }
    fresh = AppState(**preserved)
    st.session_state[_STATE_KEY] = fresh

    for key in _TRANSIENT_UI_KEYS:
        st.session_state.pop(key, None)


# Backwards-compatible alias.
reset_wip_state = clear_wip_state


# Prime the session on import so module-level reads in pages don't crash.
get_state()


# ============================================================
# HOME PAGE
# ============================================================
def home_page():
    state = get_state()
    st.title("Collection SEO Engine")
    st.markdown(
        "An internal agency tool for auditing and optimizing eCommerce collection pages at scale."
    )

    if state.bifrost_api_key:
        model_options, model_labels, _ = get_model_options()
        st.success(f"Connected to Bifrost — Model: **{model_labels.get(state.selected_model, state.selected_model)}**")
    else:
        st.warning("Set your Bifrost API key in the sidebar to enable content generation.")

    st.markdown("---")

    mode1, mode2 = st.columns(2)

    with mode1:
        st.markdown("### Single Page Generator")
        st.markdown(
            """
Enter one collection URL, fill in the brand context,
and generate optimized content immediately.

**Best for:** Quick jobs, individual page rewrites, one-off requests.
"""
        )

    with mode2:
        st.markdown("### Bulk Generator Pipeline")
        st.markdown(
            """
Upload CSV keyword data, score and batch collections,
run audits, generate content at scale, and export.

**Best for:** Full client engagements with 10+ collections.
"""
        )

    st.markdown("---")
    st.markdown("### Bulk Pipeline Status")

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        has_data = state.normalized_data is not None
        st.markdown(f"### {'✅' if has_data else '1️⃣'} Data Input")
        st.caption("Upload keyword data")
    with col2:
        has_scores = len(state.scored_collections) > 0
        st.markdown(f"### {'✅' if has_scores else '2️⃣'} Scoring")
        st.caption("Prioritize collections")
    with col3:
        has_audits = len(state.audit_results) > 0
        st.markdown(f"### {'✅' if has_audits else '3️⃣'} Audit")
        st.caption("Page audits")
    with col4:
        has_content = len(state.generated_content) > 0
        st.markdown(f"### {'✅' if has_content else '4️⃣'} Content")
        st.caption("Generate & review")
    with col5:
        st.markdown("### 5️⃣ Export")
        st.caption("Export results")

    if state.collection_groups:
        st.markdown("---")
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Collections", len(state.collection_groups))
        with m2:
            st.metric("In Batch", len(state.batch_collections))
        with m3:
            st.metric("Content Generated", len(state.generated_content))
        with m4:
            approved = sum(
                1 for c in state.generated_content.values()
                if getattr(c, "approved", False)
            )
            st.metric("Approved", approved)


# ============================================================
# NAVIGATION — Grouped pages
# ============================================================
pages_dir = Path(__file__).parent / "pages"

pg = st.navigation(
    {
        "": [
            st.Page(home_page, title="Home", icon="🏠"),
        ],
        "Setup": [
            st.Page(str(pages_dir / "0_🏷️_Brand_Profile.py"), title="Brand Profile", icon="🏷️"),
        ],
        "Single Page": [
            st.Page(str(pages_dir / "6_✏️_Single_URL_Writer.py"), title="Single URL Writer", icon="✏️"),
        ],
        "Bulk Pipeline": [
            st.Page(str(pages_dir / "1_📊_Data_Input.py"), title="Data Input", icon="📊"),
            st.Page(str(pages_dir / "2_🎯_Priority_Scoring.py"), title="Priority Scoring", icon="🎯"),
            st.Page(str(pages_dir / "3_🔍_Audit.py"), title="Audit", icon="🔍"),
            st.Page(str(pages_dir / "4_✍️_Content_Studio.py"), title="Content Studio", icon="✍️"),
            st.Page(str(pages_dir / "5_📦_Export.py"), title="Export", icon="📦"),
        ],
    }
)

# ============================================================
# SIDEBAR — API Configuration & Model Selection
# ============================================================
with st.sidebar:
    _state = get_state()
    _state_dirty = False
    st.markdown("---")
    st.markdown("### Bifrost API")

    api_key = st.text_input(
        "API Key",
        value=_state.bifrost_api_key,
        type="password",
        key="sidebar_bifrost_key",
    )
    if api_key != _state.bifrost_api_key:
        _state.bifrost_api_key = api_key
        _state_dirty = True

    base_url = st.text_input(
        "Base URL",
        value=_state.bifrost_base_url,
        key="sidebar_bifrost_url",
    )
    if base_url != _state.bifrost_base_url:
        _state.bifrost_base_url = base_url
        _state_dirty = True

    st.markdown("### Model")
    model_options, model_labels, default_model = get_model_options()
    default_idx = model_options.index(default_model) if default_model in model_options else 0

    selected_model = st.selectbox(
        "Generation Model",
        model_options,
        index=model_options.index(_state.selected_model) if _state.selected_model in model_options else default_idx,
        format_func=lambda x: model_labels.get(x, x),
        key="sidebar_model",
    )
    if selected_model != _state.selected_model:
        _state.selected_model = selected_model
        _state_dirty = True

    config = load_model_config()
    fallback_chain = config.get("fallback_chain", [])
    if fallback_chain:
        with st.expander("Fallback Chain"):
            st.caption("If the selected model fails, these are tried in order:")
            for i, m in enumerate(fallback_chain, 1):
                st.caption(f"{i}. `{m}`")

    st.markdown("---")

    with st.expander("DataForSEO (Optional)"):
        dfs_login = st.text_input(
            "Login",
            value=_state.dataforseo_login,
            key="sidebar_dfs_login",
        )
        dfs_password = st.text_input(
            "Password",
            value=_state.dataforseo_password,
            type="password",
            key="sidebar_dfs_password",
        )
        if dfs_login != _state.dataforseo_login:
            _state.dataforseo_login = dfs_login
            _state_dirty = True
        if dfs_password != _state.dataforseo_password:
            _state.dataforseo_password = dfs_password
            _state_dirty = True

    st.markdown("---")
    st.markdown("### Help")
    st.markdown(
        "- [📖 Documentation](https://github.com/rsen-pattern/Collection-Page-Content-Writter/blob/main/README.md)\n"
        "- [📝 Methodology](https://github.com/rsen-pattern/Collection-Page-Content-Writter/blob/main/README.md#methodology-rules)\n"
        "- [🐛 Report an issue](https://github.com/rsen-pattern/Collection-Page-Content-Writter/issues)"
    )
    st.caption("v0.1 · Internal agency tool")

    if _state_dirty:
        save_state(_state)

# Run the selected page
pg.run()
