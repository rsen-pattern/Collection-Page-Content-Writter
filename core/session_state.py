"""Typed session state schema for the Streamlit app.

Replaces the flat-namespace ``st.session_state`` pattern with a single
Pydantic model. Pages read via attribute access on ``get_state()``; writes
go through ``save_state()`` or specific helpers.

Validation is lenient — invalid values are coerced to defaults with a
telemetry warning rather than raising. This keeps the app resilient to
legacy session blobs and bugs while still surfacing issues.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.telemetry import log_event


# ─────────────────────────────────────────────────────────────────────
# Sub-models — these mirror existing dict shapes 1:1
# ─────────────────────────────────────────────────────────────────────


class PromptOverrides(BaseModel):
    """Mirrors ``core.brand_profile.BrandPromptOverrides`` as a Pydantic model.

    The dataclass version stays for disk persistence backward compatibility;
    this Pydantic version is what session state holds at runtime.
    """

    model_config = ConfigDict(extra="ignore")

    brand_custom_rules: str = ""
    voice_examples: str = ""
    alt_text_rules: str = ""
    alt_text_examples: str = ""
    banned_phrases: list[str] = Field(default_factory=list)
    dedup_overrides: dict[str, str] = Field(default_factory=dict)


class ClientProfile(BaseModel):
    """Runtime mirror of ``core.brand_profile.BrandProfile``.

    The full BrandProfile dataclass remains for disk save/load; this is the
    runtime representation. Conversion via :func:`client_profile_from_brand_profile`.
    """

    model_config = ConfigDict(extra="ignore")

    brand_name: str = ""
    store_url: str = ""
    brand_usps: list[str] = Field(default_factory=list)
    voice_notes: str = ""
    target_market: str = "UK"
    faq_count: int = Field(default=4, ge=3, le=8)
    past_feedback: str = ""
    humanize_by_default: bool = False
    sitemap_url: str = ""
    sitemap_parsed: dict = Field(default_factory=dict)
    sitemap_fetched_at: str = ""


class CollectionGroupModel(BaseModel):
    """Runtime mirror of ``core.data_ingestion.CollectionGroup``.

    Field shape matches the dataclass so the dataclass can be lifted into
    session state without translation.
    """

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    collection_url: str
    collection_name: str = ""
    primary_keyword: str = ""
    primary_keyword_volume: Optional[int] = None
    secondary_keywords: list[dict] = Field(default_factory=list)
    total_volume: int = 0
    best_rank: Optional[int] = None
    total_clicks: Optional[int] = None
    total_impressions: Optional[int] = None
    products_to_link: list[dict] = Field(default_factory=list)
    scraped_products: list[dict] = Field(default_factory=list)
    existing_top_copy: str = ""
    existing_bottom_copy: str = ""


class BatchCollectionEntry(BaseModel):
    """Shape of items in ``state.batch_collections``."""

    model_config = ConfigDict(extra="allow")

    collection_url: str
    collection_name: str = ""
    primary_keyword: str = ""
    primary_keyword_volume: Optional[int] = None
    total_volume: int = 0
    best_rank: Optional[int] = None
    total_clicks: Optional[int] = None
    keyword_count: int = 0
    secondary_keywords: list[dict] = Field(default_factory=list)
    priority_score: Optional[int] = None


class FAQItem(BaseModel):
    question: str = ""
    answer: str = ""


class GenerationHistoryEntry(BaseModel):
    """One entry in the per-collection generation history."""

    timestamp: str = ""
    model_used: str = ""
    generation_type: str = "full"
    humanized: bool = False
    snapshot: dict = Field(default_factory=dict)


class GeneratedContent(BaseModel):
    """Per-collection generated content blob.

    The ``collection_url`` key in the parent dict maps to one of these.
    ``extra="allow"`` keeps undeclared fields like the underscore-tagged
    generation metadata (``_humanized``, ``_generated_at``, etc.).
    """

    model_config = ConfigDict(extra="allow")

    seo_title: str = ""
    collection_title: str = ""
    description: str = ""
    meta_description: str = ""
    faqs: list[FAQItem] = Field(default_factory=list)
    suggested_headings: list[str] = Field(default_factory=list)
    suggested_tags: list[str] = Field(default_factory=list)
    alt_text: str = ""
    approved: bool = False
    history: list[GenerationHistoryEntry] = Field(default_factory=list)


class AuditInputSnapshot(BaseModel):
    """The page-content snapshot an audit ran against."""

    seo_title: str = ""
    h1: str = ""
    description: str = ""
    meta_description: str = ""


class AuditEntry(BaseModel):
    """Shape of values in ``audit_results`` / ``audit_results_generated``."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    result: Any = None  # core.auditor.AuditResult — kept as Any to avoid cycles
    input: AuditInputSnapshot = Field(default_factory=AuditInputSnapshot)


class ImplementationTrackerEntry(BaseModel):
    collection_name: str = ""
    content_status: str = "Pending"
    implemented: bool = False
    date: str = ""
    notes: str = ""


# ─────────────────────────────────────────────────────────────────────
# Root model — the entire session state
# ─────────────────────────────────────────────────────────────────────


class AppState(BaseModel):
    """The complete app session state. One instance lives on ``st.session_state``.

    Reads use attribute access via ``get_state()``. Writes go through
    ``save_state()``. Internal mutations are validated on save.

    Lenient mode: invalid values during construction are logged via telemetry
    and replaced with defaults, never raise.
    """

    model_config = ConfigDict(
        extra="ignore",
        validate_assignment=False,  # explicit save_state controls validation
        arbitrary_types_allowed=True,
    )

    # ── Credentials and config (persistent across brand switches) ───
    bifrost_api_key: str = ""
    bifrost_base_url: str = "https://bifrost.pattern.com"
    selected_model: str = "anthropic/claude-sonnet-4-6"
    dataforseo_login: str = ""
    dataforseo_password: str = ""
    webscraping_ai_key: str = ""
    scraperapi_key: str = ""

    # ── Active brand context (persistent across batches) ────────────
    client_profile: ClientProfile = Field(default_factory=ClientProfile)
    prompt_overrides: PromptOverrides = Field(default_factory=PromptOverrides)
    sitemap_parsed: dict = Field(default_factory=dict)

    # ── WIP state (cleared on brand switch) ─────────────────────────
    raw_data: Optional[Any] = None  # pandas DataFrame
    normalized_data: Optional[Any] = None  # pandas DataFrame
    source_format: str = ""
    source_keyword_width: int = 4

    # Mutated heavily by pages — kept as ``list[Any]`` so in-place writes
    # don't suffer an in-session type drift between assignment and save_state.
    # The sub-models (CollectionGroupModel etc.) remain in the schema for
    # documentation and helper conversions; validation happens at the
    # container's edges, not inside.
    collection_groups: list[Any] = Field(default_factory=list)
    skipped_collections: list[Any] = Field(default_factory=list)

    scored_collections: list[Any] = Field(default_factory=list)

    batch_collections: list[Any] = Field(default_factory=list)
    batch_mode: str = ""
    batch_faq_topics: list[str] = Field(default_factory=list)

    audit_results: dict[str, Any] = Field(default_factory=dict)
    audit_results_generated: dict[str, Any] = Field(default_factory=dict)
    scrape_results: dict[str, Any] = Field(default_factory=dict)
    scrape_tiers: dict[str, str] = Field(default_factory=dict)
    scrape_all_attempts: dict[str, Any] = Field(default_factory=dict)
    sf_crawl_data: dict[str, Any] = Field(default_factory=dict)

    content_briefs: dict[str, Any] = Field(default_factory=dict)
    generated_content: dict[str, Any] = Field(default_factory=dict)

    implementation_tracker: dict[str, Any] = Field(default_factory=dict)

    sub_collection_opportunities: dict[str, list[dict]] = Field(default_factory=dict)

    # ── Single URL Writer (its own WIP namespace) ───────────────────
    single_url_content: dict = Field(default_factory=dict)
    single_url_history: list[dict] = Field(default_factory=list)

    # ── UI preferences and transient flags ──────────────────────────
    humanize_enabled: bool = False
    force_regenerate: bool = False
    cancel_generation: bool = False

    # ── Internal caches ─────────────────────────────────────────────
    # Pydantic v2 disallows leading-underscore field names on models;
    # the page reads this as plain `state.opps_cache_key`.
    opps_cache_key: str = ""

    # ── Cross-field invariants ──────────────────────────────────────

    @model_validator(mode="after")
    def _check_batch_has_collections(self) -> "AppState":
        """If batch_collections is non-empty, collection_groups must also be.

        Catches the bug where a stale batch survives a state clear.
        """
        if self.batch_collections and not self.collection_groups:
            log_event(
                "session_state_invariant_violated",
                rule="batch_without_collections",
                batch_size=len(self.batch_collections),
            )
            # Lenient: clear the orphaned batch rather than raise.
            self.batch_collections = []
        return self

    @model_validator(mode="after")
    def _check_generated_content_in_batch(self) -> "AppState":
        """Log when generated_content URLs drift from batch URLs.

        Doesn't drop entries — sometimes generated content is held over from
        a prior batch on purpose (e.g. cache lookup). Just surfaces drift.
        Tolerates batch entries shaped as either dicts or pydantic models.
        """
        if self.generated_content and self.batch_collections:
            batch_urls: set[str] = set()
            for entry in self.batch_collections:
                url = (
                    entry.get("collection_url")
                    if isinstance(entry, dict)
                    else getattr(entry, "collection_url", "")
                )
                if url:
                    batch_urls.add(url)
            orphan_count = sum(
                1 for url in self.generated_content if url not in batch_urls
            )
            if orphan_count > 0:
                log_event(
                    "session_state_invariant_violated",
                    rule="orphan_generated_content",
                    orphan_count=orphan_count,
                )
        return self

    @model_validator(mode="after")
    def _check_audit_results_have_result(self) -> "AppState":
        """Drop audit_results entries that are missing a result.

        Tolerates entries shaped as either dicts or pydantic models so the
        invariant survives the dict/model boundary inside pages.
        """
        def _has_result(entry) -> bool:
            if isinstance(entry, dict):
                return entry.get("result") is not None
            return getattr(entry, "result", None) is not None

        bad_keys = [k for k, v in self.audit_results.items() if not _has_result(v)]
        for k in bad_keys:
            log_event(
                "session_state_invariant_violated",
                rule="audit_missing_result",
                key=k,
            )
            del self.audit_results[k]
        return self


# Fields that PERSIST across brand switches. Everything else on AppState
# is WIP and reset by ``clear_wip_state``. Listed once so the contract is
# explicit and the clear logic can derive WIP fields automatically.
PERSISTENT_FIELDS: frozenset[str] = frozenset({
    "bifrost_api_key",
    "bifrost_base_url",
    "selected_model",
    "dataforseo_login",
    "dataforseo_password",
    "webscraping_ai_key",
    "scraperapi_key",
    "client_profile",
    "prompt_overrides",
})


# ─────────────────────────────────────────────────────────────────────
# Lenient parsing — coerce invalid values to defaults, log warnings
# ─────────────────────────────────────────────────────────────────────


def parse_lenient(raw: dict) -> AppState:
    """Build an ``AppState`` from a raw dict, falling back to defaults for
    any invalid field. Logs each coercion via telemetry.

    Strategy: try full validation first (fast path). If that fails, recover
    field-by-field so a single bad value doesn't wipe the whole session.

    Recovery uses single-field model_validate so nested-model fields like
    ``client_profile`` still get proper coercion to their typed shape rather
    than landing as raw dicts.
    """
    try:
        return AppState.model_validate(raw)
    except Exception as e:
        log_event(
            "session_state_parse_failed",
            error=str(e)[:200],
            recovering="field_by_field",
        )

    state = AppState()
    for field_name in AppState.model_fields:
        if field_name not in raw:
            continue
        try:
            # Round-trip through model_validate so the field's own coercion
            # rules apply (including nested-model coercion).
            partial = AppState.model_validate({field_name: raw[field_name]})
            setattr(state, field_name, getattr(partial, field_name))
        except Exception as e:
            log_event(
                "session_state_field_coerced",
                field=field_name,
                error=str(e)[:100],
            )
            # Leave default in place.
    return state


# ─────────────────────────────────────────────────────────────────────
# Conversion helpers between session models and the dataclass equivalents
# that live on disk for backwards compatibility
# ─────────────────────────────────────────────────────────────────────


def client_profile_from_brand_profile(bp) -> ClientProfile:
    """Build a :class:`ClientProfile` from a ``core.brand_profile.BrandProfile``."""
    return ClientProfile(
        brand_name=bp.brand_name,
        store_url=bp.store_url,
        brand_usps=list(bp.brand_usps or []),
        voice_notes=bp.voice_notes,
        target_market=bp.target_market,
        faq_count=bp.faq_count,
        past_feedback=bp.past_feedback,
        humanize_by_default=getattr(bp, "humanize_by_default", False),
        sitemap_url=getattr(bp, "sitemap_url", ""),
        sitemap_parsed=getattr(bp, "sitemap_parsed", {}) or {},
        sitemap_fetched_at=getattr(bp, "sitemap_fetched_at", ""),
    )


def prompt_overrides_from_brand_overrides(bo) -> PromptOverrides:
    """Build a :class:`PromptOverrides` from a ``BrandPromptOverrides`` dataclass."""
    return PromptOverrides(
        brand_custom_rules=bo.brand_custom_rules,
        voice_examples=bo.voice_examples,
        alt_text_rules=bo.alt_text_rules,
        alt_text_examples=bo.alt_text_examples,
        banned_phrases=list(bo.banned_phrases or []),
        dedup_overrides=dict(getattr(bo, "dedup_overrides", {}) or {}),
    )


def collection_group_to_model(cg) -> CollectionGroupModel:
    """Lift a ``CollectionGroup`` dataclass into its session model.

    The Pydantic CollectionGroupModel already accepts the same field shape,
    so this is essentially a clone via ``model_dump`` for safe nested
    mutation. Already-Pydantic inputs are returned untouched.
    """
    if isinstance(cg, CollectionGroupModel):
        return cg
    if hasattr(cg, "model_dump"):
        return CollectionGroupModel.model_validate(cg.model_dump())
    return CollectionGroupModel.model_validate(cg)


__all__ = [
    "AppState",
    "AuditEntry",
    "AuditInputSnapshot",
    "BatchCollectionEntry",
    "ClientProfile",
    "CollectionGroupModel",
    "FAQItem",
    "GeneratedContent",
    "GenerationHistoryEntry",
    "ImplementationTrackerEntry",
    "PERSISTENT_FIELDS",
    "PromptOverrides",
    "client_profile_from_brand_profile",
    "collection_group_to_model",
    "parse_lenient",
    "prompt_overrides_from_brand_overrides",
]
