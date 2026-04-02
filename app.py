"""Collection SEO Engine — Main Streamlit entry point."""

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
    """Build model selection options grouped by provider."""
    config = load_model_config()
    options = []
    labels = {}
    for provider, data in config["providers"].items():
        for model in data["models"]:
            options.append(model["id"])
            labels[model["id"]] = f"{model['label']}  ({provider})"
    return options, labels, config.get("default_model", "claude-sonnet-4-6")


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
        # Scoring
        "scored_collections": [],
        "batch_collections": [],
        # Audit
        "audit_results": {},
        # Content
        "content_briefs": {},
        "generated_content": {},
        "batch_faq_topics": [],
        # Export
        "implementation_tracker": {},
        # Bifrost API config (session only)
        "bifrost_api_key": "",
        "bifrost_base_url": "https://api.getbifrost.ai",
        "selected_model": "claude-sonnet-4-6",
        # DataForSEO (optional)
        "dataforseo_login": "",
        "dataforseo_password": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()

# ============================================================
# SIDEBAR — API Configuration & Model Selection
# ============================================================
with st.sidebar:
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


# ============================================================
# MAIN PAGE
# ============================================================
st.title("Collection SEO Engine")
st.markdown(
    "An internal agency tool for auditing and optimizing eCommerce collection pages at scale."
)

# Connection status
if st.session_state.bifrost_api_key:
    st.success(f"Connected to Bifrost — Model: **{model_labels.get(st.session_state.selected_model, st.session_state.selected_model)}**")
else:
    st.warning("Set your Bifrost API key in the sidebar to enable content generation.")

st.markdown("---")

# ============================================================
# TWO MODES
# ============================================================
mode1, mode2 = st.columns(2)

with mode1:
    st.markdown("### Single Page Generator")
    st.markdown(
        """
Enter one collection URL, fill in the brand context,
and generate optimized content immediately.

**Best for:** Quick jobs, individual page rewrites, one-off requests.

**Go to** → **Single URL Writer** in the sidebar.
"""
    )

with mode2:
    st.markdown("### Bulk Generator Pipeline")
    st.markdown(
        """
Upload CSV keyword data, score and batch collections,
run audits, generate content at scale, and export.

**Best for:** Full client engagements with 10+ collections.

**Go to** → **Data Input** in the sidebar to start.
"""
    )

st.markdown("---")

# ============================================================
# BULK PIPELINE STATUS
# ============================================================
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
            1
            for c in st.session_state.generated_content.values()
            if c.get("approved")
        )
        st.metric("Approved", approved)
