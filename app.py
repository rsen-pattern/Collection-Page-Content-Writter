"""Collection SEO Engine — Main Streamlit entry point with grouped navigation."""

import json
import os
import warnings
from pathlib import Path

import streamlit as st


def __getattr__(name: str):
    """Module-level shim that warns on legacy access patterns.

    Catches imports like ``from app import init_session_state`` from any
    code that hasn't been migrated to ``get_state()`` / ``save_state()``.
    Removed in a later release.
    """
    if name == "init_session_state":
        warnings.warn(
            "init_session_state is deprecated; use get_state() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return get_state
    if name in ("WIP_DEFAULT_FACTORIES", "PERSISTENT_SESSION_KEYS"):
        warnings.warn(
            f"{name} has been replaced by core.session_state.PERSISTENT_FIELDS "
            "and the AppState model. Update callers to use get_state().",
            DeprecationWarning,
            stacklevel=2,
        )
        from core.session_state import AppState, PERSISTENT_FIELDS
        if name == "PERSISTENT_SESSION_KEYS":
            return tuple(PERSISTENT_FIELDS)
        # WIP_DEFAULT_FACTORIES — derive from model fields minus persistent set.
        return {
            field: type(None) for field in AppState.model_fields
            if field not in PERSISTENT_FIELDS
        }
    raise AttributeError(f"module 'app' has no attribute {name!r}")

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
    """Get a value from st.secrets with fallback to default.

    Kept here as a thin re-export from core.app_state for any code that
    imports it via ``from app import get_secret``.
    """
    from core.app_state import get_secret as _get_secret
    return _get_secret(key, default)


# State-access helpers live in core/app_state.py because Streamlit runs the
# entry script (this module) as __main__. Pages that do `from app import …`
# would otherwise trigger a fresh import of app.py and re-run all the
# module-level Streamlit calls (sidebar widgets), raising
# StreamlitDuplicateElementKey. Re-exported here for backwards compatibility
# with any external callers that already import from ``app``.
from core.app_state import (  # noqa: E402  (intentional after st.set_page_config)
    _STATE_KEY,
    _TRANSIENT_UI_KEYS,
    clear_wip_state,
    get_state,
    reset_wip_state,
    save_state,
)


# Prime the session on entry so module-level reads in pages don't crash.
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

    # Debug expander — only when SHOW_DEBUG env var is set.
    if os.getenv("SHOW_DEBUG", "").lower() in ("true", "1", "yes"):
        with st.expander("🔧 Debug: session state"):
            st.json({
                "state_shape": type(_state).__name__,
                "collections": len(_state.collection_groups),
                "batch_size": len(_state.batch_collections),
                "generated": len(_state.generated_content),
                "audited": len(_state.audit_results),
                "has_brand": bool(_state.client_profile.brand_name),
                "humanize_enabled": _state.humanize_enabled,
                "batch_mode": _state.batch_mode,
            })
            st.caption("Raw state dump:")
            try:
                st.json(_state.model_dump(mode="json"))
            except Exception as e:
                st.caption(f"(dump failed: {e})")

    if _state_dirty:
        save_state(_state)

# Run the selected page
pg.run()
