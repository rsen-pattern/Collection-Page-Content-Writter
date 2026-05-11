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


def _default_client_profile() -> dict:
    """Fresh client_profile dict — built per call so callers can't mutate a shared template."""
    return {
        "brand_name": "",
        "store_url": "",
        "brand_usps": [],
        "voice_notes": "",
        "target_market": "UK",
        "faq_count": 4,
        "past_feedback": "",
    }


# Session keys considered "project work-in-progress". The brand-switch
# reset path uses this list; init_session_state() seeds these to fresh
# empties on first load. API credentials and model selection are NOT in
# this list and are never cleared on brand switch.
WIP_DEFAULT_FACTORIES = {
    "raw_data": lambda: None,
    "normalized_data": lambda: None,
    "source_format": lambda: None,
    "collection_groups": list,
    "skipped_collections": list,
    "scored_collections": list,
    "batch_collections": list,
    "batch_mode": lambda: "",
    "audit_results": dict,
    "scrape_results": dict,
    "scrape_tiers": dict,
    "sf_crawl_data": dict,
    "content_briefs": dict,
    "generated_content": dict,
    "batch_faq_topics": list,
    "implementation_tracker": dict,
    "single_url_content": dict,
    "single_url_history": list,
}


def init_session_state():
    """Initialize all session state variables.

    Each value is constructed fresh (factories / fresh literals) so a caller
    mutating ``client_profile`` in place can't taint the next initialisation.
    """
    if "client_profile" not in st.session_state:
        st.session_state["client_profile"] = _default_client_profile()

    for key, factory in WIP_DEFAULT_FACTORIES.items():
        if key not in st.session_state:
            st.session_state[key] = factory()

    # Scraper API keys — optional, tiers without a key are skipped.
    if "webscraping_ai_key" not in st.session_state:
        st.session_state["webscraping_ai_key"] = get_secret("WEBSCRAPING_AI_KEY", "")
    if "scraperapi_key" not in st.session_state:
        st.session_state["scraperapi_key"] = get_secret("SCRAPERAPI_KEY", "")

    # Bifrost API config — supports both BIFROST_API_KEY and BIFROST_KEY names.
    if "bifrost_api_key" not in st.session_state:
        st.session_state["bifrost_api_key"] = (
            get_secret("BIFROST_API_KEY") or get_secret("BIFROST_KEY")
        )
    if "bifrost_base_url" not in st.session_state:
        st.session_state["bifrost_base_url"] = get_secret(
            "BIFROST_BASE_URL", "https://bifrost.pattern.com"
        )
    if "selected_model" not in st.session_state:
        st.session_state["selected_model"] = get_secret(
            "BIFROST_DEFAULT_MODEL", "anthropic/claude-sonnet-4-6"
        )

    # DataForSEO (optional)
    if "dataforseo_login" not in st.session_state:
        st.session_state["dataforseo_login"] = get_secret("DATAFORSEO_LOGIN")
    if "dataforseo_password" not in st.session_state:
        st.session_state["dataforseo_password"] = get_secret("DATAFORSEO_PASSWORD")


def reset_wip_state() -> None:
    """Reset every work-in-progress session key to its declared default.

    Does not touch API credentials, model selection, DataForSEO credentials,
    or client_profile (callers replace client_profile explicitly with the new
    brand). Safe to call multiple times.
    """
    for key, factory in WIP_DEFAULT_FACTORIES.items():
        st.session_state[key] = factory()
    # Sitemap is per-brand and lives outside WIP_DEFAULT_FACTORIES so the
    # Brand Profile page can repopulate it without flicker. Clear it here.
    st.session_state.pop("sitemap_parsed", None)
    # Discard prompt_overrides — they belong to the previous brand.
    st.session_state.pop("prompt_overrides", None)


init_session_state()


# ============================================================
# HOME PAGE
# ============================================================
def home_page():
    st.title("Collection SEO Engine")
    st.markdown(
        "An internal agency tool for auditing and optimizing eCommerce collection pages at scale."
    )

    if st.session_state.bifrost_api_key:
        model_options, model_labels, _ = get_model_options()
        st.success(f"Connected to Bifrost — Model: **{model_labels.get(st.session_state.selected_model, st.session_state.selected_model)}**")
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
        has_data = st.session_state.normalized_data is not None
        st.markdown(f"### {'✅' if has_data else '1️⃣'} Data Input")
        st.caption("Upload keyword data")
    with col2:
        has_scores = len(st.session_state.scored_collections) > 0
        st.markdown(f"### {'✅' if has_scores else '2️⃣'} Scoring")
        st.caption("Prioritize collections")
    with col3:
        has_audits = len(st.session_state.audit_results) > 0
        st.markdown(f"### {'✅' if has_audits else '3️⃣'} Audit")
        st.caption("Page audits")
    with col4:
        has_content = len(st.session_state.generated_content) > 0
        st.markdown(f"### {'✅' if has_content else '4️⃣'} Content")
        st.caption("Generate & review")
    with col5:
        st.markdown("### 5️⃣ Export")
        st.caption("Export results")

    if st.session_state.collection_groups:
        st.markdown("---")
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Collections", len(st.session_state.collection_groups))
        with m2:
            st.metric("In Batch", len(st.session_state.batch_collections))
        with m3:
            st.metric("Content Generated", len(st.session_state.generated_content))
        with m4:
            approved = sum(
                1 for c in st.session_state.generated_content.values() if c.get("approved")
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
    st.markdown("---")
    st.markdown("### Bifrost API")

    api_key = st.text_input(
        "API Key",
        value=st.session_state.bifrost_api_key,
        type="password",
        key="sidebar_bifrost_key",
    )
    if api_key != st.session_state.bifrost_api_key:
        st.session_state.bifrost_api_key = api_key

    base_url = st.text_input(
        "Base URL",
        value=st.session_state.bifrost_base_url,
        key="sidebar_bifrost_url",
    )
    if base_url != st.session_state.bifrost_base_url:
        st.session_state.bifrost_base_url = base_url

    st.markdown("### Model")
    model_options, model_labels, default_model = get_model_options()
    default_idx = model_options.index(default_model) if default_model in model_options else 0

    selected_model = st.selectbox(
        "Generation Model",
        model_options,
        index=model_options.index(st.session_state.selected_model) if st.session_state.selected_model in model_options else default_idx,
        format_func=lambda x: model_labels.get(x, x),
        key="sidebar_model",
    )
    if selected_model != st.session_state.selected_model:
        st.session_state.selected_model = selected_model

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
            value=st.session_state.dataforseo_login,
            key="sidebar_dfs_login",
        )
        dfs_password = st.text_input(
            "Password",
            value=st.session_state.dataforseo_password,
            type="password",
            key="sidebar_dfs_password",
        )
        if dfs_login != st.session_state.dataforseo_login:
            st.session_state.dataforseo_login = dfs_login
        if dfs_password != st.session_state.dataforseo_password:
            st.session_state.dataforseo_password = dfs_password

    st.markdown("---")
    st.markdown("### Help")
    st.markdown(
        "- [📖 Documentation](https://github.com/rsen-pattern/Collection-Page-Content-Writter/blob/main/README.md)\n"
        "- [📝 Methodology](https://github.com/rsen-pattern/Collection-Page-Content-Writter/blob/main/README.md#methodology-rules)\n"
        "- [🐛 Report an issue](https://github.com/rsen-pattern/Collection-Page-Content-Writter/issues)"
    )
    st.caption("v0.1 · Internal agency tool")

# Run the selected page
pg.run()
