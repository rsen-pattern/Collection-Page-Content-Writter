"""Session state access layer — module-level so pages can import it safely.

Lives in ``core/`` rather than ``app.py`` because Streamlit runs the entry
script (``app.py``) as ``__main__``. When a page does ``from app import …``,
Python looks up ``app`` in ``sys.modules``, doesn't find it (the entry
script lives as ``__main__``), and re-executes ``app.py`` from disk —
which renders the sidebar widgets a second time and raises
``StreamlitDuplicateElementKey``.

Pages import from this module instead. ``app.py`` re-exports the same
names for any external code that still imports from the entry script.
"""

from __future__ import annotations

import streamlit as st


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


def get_secret(key: str, default: str = "") -> str:
    """Get a value from ``st.secrets`` with fallback to default."""
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError, AttributeError):
        return default


def get_state():
    """Return the typed :class:`~core.session_state.AppState` for this session.

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

    Validation walks ``state.__dict__`` rather than ``state.model_dump()`` so
    that item references in ``list[Any]`` / ``dict[str, Any]`` fields survive
    unchanged. A round-trip through ``model_dump`` would recursively serialise
    nested Pydantic models (e.g. ``CollectionGroup`` instances inside
    ``collection_groups``) into plain dicts, breaking attribute access on the
    next render.
    """
    from core.session_state import AppState

    try:
        validated = AppState.model_validate(state.__dict__)
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
    preserved = {name: getattr(current, name) for name in PERSISTENT_FIELDS}
    fresh = AppState(**preserved)
    st.session_state[_STATE_KEY] = fresh

    for key in _TRANSIENT_UI_KEYS:
        st.session_state.pop(key, None)


# Backwards-compatible alias.
reset_wip_state = clear_wip_state


__all__ = [
    "_STATE_KEY",
    "_TRANSIENT_UI_KEYS",
    "clear_wip_state",
    "get_secret",
    "get_state",
    "reset_wip_state",
    "save_state",
]
