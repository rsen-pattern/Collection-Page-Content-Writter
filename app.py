"""Collection SEO Engine — Main Streamlit entry point."""

import streamlit as st

st.set_page_config(
    page_title="Collection SEO Engine",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)


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
        # API keys (session only)
        "anthropic_api_key": "",
        "dataforseo_login": "",
        "dataforseo_password": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()

# Main page
st.title("Collection SEO Engine")
st.markdown(
    "An internal agency tool for auditing and optimizing eCommerce collection pages at scale."
)

st.markdown("---")

# Workflow steps
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    has_data = st.session_state.normalized_data is not None
    st.markdown(
        f"### {'✅' if has_data else '1️⃣'} Data Input"
    )
    st.caption("Upload keyword data & set up client profile")

with col2:
    has_scores = len(st.session_state.scored_collections) > 0
    st.markdown(
        f"### {'✅' if has_scores else '2️⃣'} Priority Scoring"
    )
    st.caption("Score & batch collections")

with col3:
    has_audits = len(st.session_state.audit_results) > 0
    st.markdown(
        f"### {'✅' if has_audits else '3️⃣'} Audit"
    )
    st.caption("Automated page audits")

with col4:
    has_content = len(st.session_state.generated_content) > 0
    st.markdown(
        f"### {'✅' if has_content else '4️⃣'} Content Studio"
    )
    st.caption("Generate & review content")

with col5:
    st.markdown("### 5️⃣ Export")
    st.caption("Export for implementation")

st.markdown("---")

# Quick stats
if st.session_state.collection_groups:
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

st.markdown("---")

st.markdown("### Two Ways to Work")

tw1, tw2 = st.columns(2)
with tw1:
    st.markdown("#### Bulk Pipeline (Steps 1-5)")
    st.markdown(
        """
Upload CSV keyword data, score and batch collections,
run audits, generate content at scale, and export.
Best for **full client engagements** with 10+ collections.
"""
    )

with tw2:
    st.markdown("#### Single URL Writer")
    st.markdown(
        """
Enter one collection URL, fill in the context, and generate
optimized content immediately. No CSV needed.
Best for **quick jobs** or individual page rewrites.

Go to **Single URL Writer** in the sidebar.
"""
    )

st.markdown("---")
st.markdown("### Bulk Pipeline Steps")
st.markdown(
    """
1. **Data Input** — upload keyword data and configure the client profile
2. **Priority Scoring** — score and batch collections
3. **Audit** — check current page state and identify gaps
4. **Content Studio** — generate and review content
5. **Export** — keyword maps, content delivery docs, or Shopify-ready CSVs

Use the sidebar to navigate between steps. Progress is saved automatically.
"""
)

# Sidebar API configuration
with st.sidebar:
    st.markdown("### API Configuration")

    with st.expander("Anthropic API Key", expanded=not st.session_state.anthropic_api_key):
        api_key = st.text_input(
            "API Key",
            value=st.session_state.anthropic_api_key,
            type="password",
            key="sidebar_anthropic_key",
        )
        if api_key != st.session_state.anthropic_api_key:
            st.session_state.anthropic_api_key = api_key

    with st.expander("DataForSEO Credentials (Optional)"):
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
