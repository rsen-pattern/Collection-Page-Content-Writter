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


def init_session_state():
    """Initialize all session state variables."""
    defaults = {
        # Client profile
        "client_profile": {
            "brand_name": "",
            "store_url": "",
            "brand_usps": [],
            "voice_notes": "",
            "target_market": "UK",
        },
        # Data
        "raw_data": None,
        "normalized_data": None,
        "source_format": None,
        "collection_groups": [],
        "skipped_collections": [],
        # Scoring
        "scored_collections": [],
        "batch_collections": [],
        "batch_mode": "",
        # Audit
        "audit_results": {},
        "scrape_results": {},
        "scrape_tiers": {},
        "sf_crawl_data": {},
        # Scraper API keys — optional, tiers without a key are skipped
        "webscraping_ai_key": get_secret("WEBSCRAPING_AI_KEY", ""),
        "scraperapi_key": get_secret("SCRAPERAPI_KEY", ""),
        # Content
        "content_briefs": {},
        "generated_content": {},
        "batch_faq_topics": [],
        # Export
        "implementation_tracker": {},
        # Bifrost API config — load from secrets first, then allow override
        # Supports both BIFROST_API_KEY and BIFROST_KEY secret names
        "bifrost_api_key": get_secret("BIFROST_API_KEY") or get_secret("BIFROST_KEY"),
        "bifrost_base_url": get_secret("BIFROST_BASE_URL", "https://bifrost.pattern.com"),
        "selected_model": get_secret("BIFROST_DEFAULT_MODEL", "anthropic/claude-sonnet-4-6"),
        # DataForSEO (optional)
        "dataforseo_login": get_secret("DATAFORSEO_LOGIN"),
        "dataforseo_password": get_secret("DATAFORSEO_PASSWORD"),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


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

# Run the selected page
pg.run()
