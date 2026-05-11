"""Tests for app.py — get_state, save_state, clear_wip_state, legacy migration."""

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


def _build_fake_streamlit(secrets: dict | None = None):
    """Build a Streamlit stub where input widgets echo their default values."""
    fake_st = MagicMock()
    fake_st.session_state = _AttrDict()
    fake_st.set_page_config = MagicMock()
    fake_st.sidebar.__enter__ = MagicMock(return_value=fake_st)
    fake_st.sidebar.__exit__ = MagicMock(return_value=False)
    fake_st.secrets = secrets or {}

    # Widget stubs that pass the default through — so the module-level sidebar
    # block doesn't write MagicMock instances into the state during reload.
    def _echo_value(*args, **kwargs):
        return kwargs.get("value", "")

    def _echo_selectbox(*args, **kwargs):
        # Mirror st.selectbox returning the option at `index=`
        if args and "index" in kwargs:
            options = args[1] if len(args) > 1 else kwargs.get("options", [])
            idx = kwargs.get("index", 0) or 0
            if isinstance(options, (list, tuple)) and 0 <= idx < len(options):
                return options[idx]
        if "options" in kwargs:
            opts = kwargs["options"]
            idx = kwargs.get("index", 0) or 0
            if 0 <= idx < len(opts):
                return opts[idx]
        return ""

    fake_st.text_input.side_effect = _echo_value
    fake_st.text_area.side_effect = _echo_value
    fake_st.selectbox.side_effect = _echo_selectbox
    return fake_st


def _import_app(secrets: dict | None = None):
    """Import app.py with streamlit stubbed so module-level code is harmless."""
    fake_st = _build_fake_streamlit(secrets)
    with patch.dict("sys.modules", {"streamlit": fake_st}):
        import importlib
        import app
        importlib.reload(app)
        return app, fake_st


class TestGetState:
    def test_fresh_session_returns_appstate(self):
        app, fake_st = _import_app()
        from core.session_state import AppState
        state = app.get_state()
        assert isinstance(state, AppState)
        # _app_state_v1 holds the live instance.
        assert fake_st.session_state[app._STATE_KEY] is state

    def test_get_state_is_idempotent_per_session(self):
        app, _ = _import_app()
        a = app.get_state()
        b = app.get_state()
        assert a is b

    def test_secrets_loaded_into_state_on_first_init(self):
        app, _ = _import_app(
            secrets={
                "BIFROST_API_KEY": "sk-secret",
                "BIFROST_DEFAULT_MODEL": "anthropic/claude-haiku-4-5",
            }
        )
        state = app.get_state()
        assert state.bifrost_api_key == "sk-secret"
        assert state.selected_model == "anthropic/claude-haiku-4-5"


class TestLegacyMigration:
    def test_flat_namespace_migrates_into_app_state(self):
        app, fake_st = _import_app()
        # Drop the auto-built AppState so we can simulate a pre-upgrade session.
        del fake_st.session_state[app._STATE_KEY]
        # Plant legacy flat-namespace keys.
        fake_st.session_state["bifrost_api_key"] = "sk-legacy"
        fake_st.session_state["client_profile"] = {"brand_name": "Legacy Brand"}
        fake_st.session_state["collection_groups"] = [
            {"collection_url": "https://x.com/collections/y", "primary_keyword": "y"}
        ]

        state = app.get_state()
        # Legacy keys swept up into the typed state.
        assert state.bifrost_api_key == "sk-legacy"
        assert state.client_profile.brand_name == "Legacy Brand"
        assert len(state.collection_groups) == 1
        # And removed from the flat namespace to prevent split-brain reads.
        assert "bifrost_api_key" not in fake_st.session_state
        assert "client_profile" not in fake_st.session_state
        assert "collection_groups" not in fake_st.session_state

    def test_migration_logs_telemetry_event(self):
        app, fake_st = _import_app()
        del fake_st.session_state[app._STATE_KEY]
        fake_st.session_state["bifrost_api_key"] = "sk-x"
        from unittest.mock import patch as _patch
        with _patch("core.telemetry.log_event") as mock_log:
            app.get_state()
        events = [c.args[0] for c in mock_log.call_args_list]
        assert "session_state_legacy_migration" in events


class TestSaveState:
    def test_save_state_persists_mutation(self):
        app, fake_st = _import_app()
        state = app.get_state()
        state.bifrost_api_key = "sk-changed"
        app.save_state(state)
        assert fake_st.session_state[app._STATE_KEY].bifrost_api_key == "sk-changed"

    def test_save_state_runs_invariants(self):
        app, _ = _import_app()
        from core.session_state import BatchCollectionEntry
        state = app.get_state()
        # Set a batch without any collection_groups — the invariant should clear it.
        state.batch_collections = [BatchCollectionEntry(collection_url="u1")]
        state.collection_groups = []
        app.save_state(state)
        # Re-fetched state should have the batch cleared by the invariant.
        assert app.get_state().batch_collections == []

    def test_save_state_swallows_validation_errors(self):
        """A model_validate failure must not break save_state — keep user work."""
        app, fake_st = _import_app()
        from core.session_state import AppState
        state = app.get_state()
        # Build a state that round-trip will fail by injecting a non-serialisable value.
        class _Unserialisable:
            def __repr__(self):
                return "<unserialisable>"
        # Use sf_crawl_data which is dict[str, Any] — accepts anything but
        # model_dump may choke. We trip the save_state recovery path by
        # forcing model_validate to raise.
        with patch.object(AppState, "model_validate", side_effect=RuntimeError("boom")):
            with patch("core.telemetry.log_event") as mock_log:
                app.save_state(state)
        events = [c.args[0] for c in mock_log.call_args_list]
        assert "session_state_save_failed" in events
        # The state instance is preserved even though validation failed.
        assert fake_st.session_state[app._STATE_KEY] is state


class TestClearWipState:
    def test_preserves_credentials_and_brand_profile(self):
        app, _ = _import_app()
        state = app.get_state()
        from core.session_state import (
            ClientProfile, PromptOverrides, BatchCollectionEntry,
        )
        # Populate persistent + WIP fields.
        state.bifrost_api_key = "sk-keep"
        state.selected_model = "anthropic/claude-sonnet-4-6"
        state.dataforseo_login = "login@example.com"
        state.client_profile = ClientProfile(brand_name="Stay")
        state.prompt_overrides = PromptOverrides(brand_custom_rules="rule")
        state.collection_groups = [{"collection_url": "u"}]
        state.batch_collections = [BatchCollectionEntry(collection_url="u")]
        state.batch_faq_topics = ["already"]
        state.humanize_enabled = True  # WIP-ish toggle — reset to default

        app.save_state(state)
        app.clear_wip_state()

        new = app.get_state()
        # Persistent: kept.
        assert new.bifrost_api_key == "sk-keep"
        assert new.selected_model == "anthropic/claude-sonnet-4-6"
        assert new.dataforseo_login == "login@example.com"
        assert new.client_profile.brand_name == "Stay"
        assert new.prompt_overrides.brand_custom_rules == "rule"
        # WIP: reset.
        assert new.collection_groups == []
        assert new.batch_collections == []
        assert new.batch_faq_topics == []
        assert new.humanize_enabled is False

    def test_clears_transient_ui_keys(self):
        app, fake_st = _import_app()
        fake_st.session_state["_pending_brand_switch"] = {"x": 1}
        fake_st.session_state["_bp_pending_sitemap"] = {"y": 2}
        fake_st.session_state["_ai_diagnosis"] = "diag"
        app.clear_wip_state()
        assert "_pending_brand_switch" not in fake_st.session_state
        assert "_bp_pending_sitemap" not in fake_st.session_state
        assert "_ai_diagnosis" not in fake_st.session_state

    def test_reset_wip_state_alias(self):
        app, _ = _import_app()
        assert app.reset_wip_state is app.clear_wip_state


class TestSaveStatePreservesTypes:
    """save_state must NOT destroy item references in list[Any]/dict[str, Any] fields.

    Regression test for the AttributeError that hit the Data Input page after
    Process Data: model_dump+model_validate round-trip was converting
    list[CollectionGroup] items into plain dicts, breaking `g.collection_name`
    attribute access on the next render.
    """

    def test_collection_group_instances_survive_save_state(self):
        app, _ = _import_app()
        from core.data_ingestion import CollectionGroup
        state = app.get_state()
        state.collection_groups = [
            CollectionGroup(
                collection_url="https://x.com/collections/y",
                collection_name="Y",
                primary_keyword="y",
            )
        ]
        app.save_state(state)
        new = app.get_state()
        assert type(new.collection_groups[0]).__name__ == "CollectionGroup"
        # Attribute access still works after the save round-trip.
        assert new.collection_groups[0].collection_name == "Y"

    def test_dict_coercion_to_subtyped_field_still_works(self):
        """When a page assigns a dict to client_profile (Brand Profile apply
        path) save_state should still coerce it to a ClientProfile."""
        app, _ = _import_app()
        state = app.get_state()
        state.client_profile = {"brand_name": "X", "faq_count": 5}
        app.save_state(state)
        new = app.get_state()
        from core.session_state import ClientProfile
        assert isinstance(new.client_profile, ClientProfile)
        assert new.client_profile.brand_name == "X"
        assert new.client_profile.faq_count == 5
