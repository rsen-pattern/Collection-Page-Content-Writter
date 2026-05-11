"""Tests for app.py session-state defaults and reset semantics."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


class _AttrDict(dict):
    """Dict that also supports attribute access — mirrors Streamlit's SessionState."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def _import_app():
    """Import app.py with streamlit stubbed so module-level code is harmless."""
    fake_st = MagicMock()
    fake_st.session_state = _AttrDict()
    fake_st.set_page_config = MagicMock()
    fake_st.sidebar.__enter__ = MagicMock(return_value=fake_st)
    fake_st.sidebar.__exit__ = MagicMock(return_value=False)

    with patch.dict("sys.modules", {"streamlit": fake_st}):
        import importlib
        import app
        importlib.reload(app)
        return app, fake_st


def test_default_client_profile_returns_fresh_dict():
    app, _ = _import_app()
    a = app._default_client_profile()
    b = app._default_client_profile()
    assert a == b
    a["brand_usps"].append("BUILT FOR LIFE")
    a["brand_name"] = "Mutant"
    assert b["brand_usps"] == []
    assert b["brand_name"] == ""


def test_wip_factories_produce_fresh_containers():
    """Every factory in WIP_DEFAULT_FACTORIES must return a new container each call."""
    app, _ = _import_app()
    for key, factory in app.WIP_DEFAULT_FACTORIES.items():
        a = factory()
        b = factory()
        assert a == b, f"Factory for {key} produced inconsistent values"
        if isinstance(a, (list, dict)):
            assert a is not b, f"Factory for {key} returns the same instance"


def test_reset_wip_state_clears_documented_keys_without_touching_credentials():
    app, fake_st = _import_app()
    # Pre-populate the session with both WIP state and credentials.
    fake_st.session_state.update({
        "collection_groups": ["taint"],
        "batch_collections": [{"x": 1}],
        "batch_faq_topics": ["already-used"],
        "audit_results": {"taint": True},
        "single_url_history": [{"a": 1}],
        "sitemap_parsed": {"taint": True},
        "prompt_overrides": {"banned_phrases": ["x"]},
        "bifrost_api_key": "sk-keep",
        "bifrost_base_url": "https://keep.example.com",
        "selected_model": "anthropic/claude-sonnet-4-6",
        "dataforseo_login": "keep@example.com",
        "dataforseo_password": "keep",
        "client_profile": {"brand_name": "untouched-by-reset"},
        "webscraping_ai_key": "wsa-keep",
        "scraperapi_key": "sapi-keep",
    })

    app.reset_wip_state()

    # WIP keys reset
    assert fake_st.session_state["collection_groups"] == []
    assert fake_st.session_state["batch_collections"] == []
    assert fake_st.session_state["batch_faq_topics"] == []
    assert fake_st.session_state["audit_results"] == {}
    assert fake_st.session_state["single_url_history"] == []
    # Sitemap and prompt_overrides are dropped entirely
    assert "sitemap_parsed" not in fake_st.session_state
    assert "prompt_overrides" not in fake_st.session_state

    # Credentials, model, scraper keys, client_profile all preserved
    assert fake_st.session_state["bifrost_api_key"] == "sk-keep"
    assert fake_st.session_state["bifrost_base_url"] == "https://keep.example.com"
    assert fake_st.session_state["selected_model"] == "anthropic/claude-sonnet-4-6"
    assert fake_st.session_state["dataforseo_login"] == "keep@example.com"
    assert fake_st.session_state["dataforseo_password"] == "keep"
    assert fake_st.session_state["client_profile"]["brand_name"] == "untouched-by-reset"
    assert fake_st.session_state["webscraping_ai_key"] == "wsa-keep"
    assert fake_st.session_state["scraperapi_key"] == "sapi-keep"
