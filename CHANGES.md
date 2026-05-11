# Changes

## Update — Site keyword data + cannibalisation detection

Adds an optional second data upload on Data Input — a domain-wide keyword
export from **SEMrush**, **Ahrefs**, or **Brightedge**. Drives two new
signals:

1. **Cannibalisation detection** — keywords where multiple URLs ranked.
   Two flavours:
   - *Primary keyword overlap*: two or more collections in the current
     batch share a primary keyword (detected from the per-collection data
     alone, no upload needed).
   - *Top-10 SERP overlap*: from the site keyword corpus, keywords where
     ≥2 URLs rank in positions 1–10 (configurable range).
   Surfaced on **Priority Scoring** as a `⚠️ N cannibalisation conflicts`
   badge next to affected collections, with an inline expander listing the
   conflicting keywords and competing URLs.

2. **New keyword suggestions** — site-corpus keywords that already point
   at a collection's URL (or share its `/collections/<handle>`) but aren't
   in the brief yet. Surfaced on the **Content Studio Brief tab** as a
   "🔑 N keyword suggestions from site data" expander so writers can pull
   them into the secondary-keyword list.

### Core

- New `core/site_keywords.py` with:
  - `SiteKeywordRow` / `SiteKeywordCorpus` dataclasses, JSON round-trip
    via `to_dict` / `from_dict`.
  - `detect_site_format(df)` — distinguishes SEMrush / Ahrefs / Brightedge
    by their distinctive column headers (e.g. `Current URL` + `Current
    position` → Ahrefs; `Landing Page` or `Average Rank` → Brightedge;
    `Search Volume` + `URL` + `Position` → SEMrush).
  - `parse_site_keywords(df)` — lenient parser; rows with no keyword or
    URL are dropped silently, missing position/traffic tolerated.
  - `find_primary_keyword_conflicts(collection_groups)` — pure per-
    collection check, no upload required.
  - `find_top_10_conflicts(corpus, min_position=1, max_position=10)` —
    keyword-level overlap detection across the corpus.
  - `find_all_cannibalisation(collection_groups, corpus)` — combines
    both, deduplicates, marks "primary_and_top10" when a keyword surfaces
    from both passes.
  - `suggest_keywords_for_collection(url, corpus, existing_keywords)` —
    new-keyword suggestions for the Content Studio.
- `core/session_state.AppState` gained `site_keywords: dict` (parsed
  corpus, serialised) and `site_cannibalisation: dict[str, list[dict]]`
  (pre-computed conflicts keyed by keyword).

### UI

- **Data Input page**: new "Site Keyword Data (optional)" section just
  before the Shopify scraper. Auto-detects vendor, shows a row count, and
  parses on click. Successful upload runs cannibalisation detection
  against the current `collection_groups` and stashes both the corpus and
  the conflicts on session state.
- **Priority Scoring page**: top-of-page info banner reports the total
  conflict count. Each scored-collection checkbox now carries a
  `⚠️ N cannibalisation conflict(s)` badge when relevant, with an inline
  expander listing the conflicting keywords, the conflict kind (primary
  vs top-10 vs both), search volume, position, and the competing URLs.
- **Content Studio Brief tab**: new "🔑 N keyword suggestions from site
  data" expander surfaces unassigned keywords for the active collection
  with per-keyword search volume and SERP position.

### Tests

- `tests/test_site_keywords.py` (new) — 28 tests covering vendor format
  detection, parsing (Ahrefs / SEMrush / Brightedge / missing columns /
  empty rows), primary-keyword conflict detection, top-10 conflict
  detection (range filtering, distinct URL requirement, same-URL
  dedup), combined detection (primary_and_top10 merge), per-URL
  filtering, and keyword suggestions (URL match, handle match,
  existing-keyword filter, volume floor, max cap).

**Files touched:** `core/site_keywords.py` (new),
`core/session_state.py`, `pages/1_📊_Data_Input.py`,
`pages/2_🎯_Priority_Scoring.py`, `pages/4_✍️_Content_Studio.py`,
`tests/test_site_keywords.py` (new).

### Constraints respected

- No new pip dependencies — stdlib + already-vendored `pandas`.
- Feature is optional throughout — every reference is guarded so
  existing flows behave unchanged when no site keyword corpus is loaded.
- Lenient parsing — unknown columns ignored, malformed rows dropped
  silently, vendor falls back to "custom" rather than raising.

---

## Update — Typed session state schema

Replaces the flat ``st.session_state`` namespace with a Pydantic ``AppState``
model. Pages now access state via ``get_state()`` and persist mutations via
``save_state()``.

**Why:** New contributors couldn't tell what shape ``generated_content[url]``
should have without reading every page that wrote it. The contract was
implicit and growing. Past 5-6 pages with significant business logic, this
becomes a real maintenance tax. A typed schema makes the contract
discoverable in one file.

### What changed

- New ``core/session_state.py`` with the ``AppState`` root model and
  documentation-grade sub-models (``ClientProfile``, ``PromptOverrides``,
  ``CollectionGroupModel``, ``BatchCollectionEntry``, ``FAQItem``,
  ``GeneratedContent``, ``GenerationHistoryEntry``, ``AuditEntry``,
  ``AuditInputSnapshot``, ``ImplementationTrackerEntry``).
  ``PERSISTENT_FIELDS`` frozenset documents which fields survive a brand
  switch — everything else is WIP by default.
- ``app.py`` gains ``get_state()``, ``save_state()``, and ``clear_wip_state()``.
  Legacy ``init_session_state`` / ``WIP_DEFAULT_FACTORIES`` removed; the
  registry is derived from ``AppState`` itself. Backwards-compat shim
  emits ``DeprecationWarning`` for any code that still imports the old
  names.
- Auto-migration from the flat shape — transparent to users; emits
  ``session_state_legacy_migration`` telemetry on first read.
- Three cross-field invariants (lenient: log + coerce, never raise):
  ``batch_without_collections`` clears orphaned batches,
  ``orphan_generated_content`` surfaces drift but keeps data,
  ``audit_missing_result`` drops audit entries without an underlying
  AuditResult.
- All 7 pages migrated to the typed access pattern: app.py home_page +
  sidebar, Brand Profile, Data Input, Priority Scoring, Audit, Content
  Studio, Export, Single URL Writer.
- Widget keys and transient UI flags continue to live directly on
  ``st.session_state`` — Streamlit's contract, not ours.
- Sidebar gains a ``SHOW_DEBUG=true`` env-gated debug expander that
  dumps the current AppState as JSON for migration-health visibility.
- README gains a "Session state architecture" section explaining the
  read/write contract.

### Tests

- ``tests/test_session_state.py`` (new) — 17 tests: empty defaults,
  per-instance isolation, ``parse_lenient`` happy path + field-by-field
  recovery, every invariant, every conversion helper.
- ``tests/test_app.py`` rewritten for the new API: fresh session
  returns ``AppState``, ``get_state`` is idempotent, secrets populate
  on first init, legacy migration sweeps flat keys and removes them,
  ``save_state`` runs invariants + swallows validation failures,
  ``clear_wip_state`` preserves credentials and drops transient UI
  keys, ``reset_wip_state`` alias still works.

### Validation mode

Lenient throughout. Bugs surface as telemetry events
(``session_state_invariant_violated``, ``session_state_field_coerced``,
``session_state_save_failed``) rather than crashes.

### Breaking changes

None at runtime — auto-migration is transparent. Code-level: imports
of ``init_session_state``, ``WIP_DEFAULT_FACTORIES``, or
``PERSISTENT_SESSION_KEYS`` from ``app`` now emit ``DeprecationWarning``
and return shim values. Remove the shim in a later release once any
external callers are updated.

**Files touched:** ``core/session_state.py`` (new), ``app.py``,
``pages/0_🏷️_Brand_Profile.py``, ``pages/1_📊_Data_Input.py``,
``pages/2_🎯_Priority_Scoring.py``, ``pages/3_🔍_Audit.py``,
``pages/4_✍️_Content_Studio.py``, ``pages/5_📦_Export.py``,
``pages/6_✏️_Single_URL_Writer.py``,
``tests/test_session_state.py`` (new), ``tests/test_app.py``,
``README.md``.

---

## Update — Post-merge upgrade (debt, precision, loops, architecture)

Fourteen items from a review of the recent text_utils / sub-collection /
telemetry merges. Landed across four commits.

### Debt cleanup (Commit 1)

- `app.py` WIP_DEFAULT_FACTORIES now registers `source_keyword_width`,
  `sub_collection_opportunities`, `audit_results_generated`, and
  `scrape_all_attempts` — features that arrived in later PRs without
  being added to the registry. New `PERSISTENT_SESSION_KEYS` tuple
  documents which keys MUST survive a brand switch. New
  `_INTERNAL_CACHE_KEYS` tuple captures underscore-prefixed UI cache
  state cleared on brand switch. `clear_wip_state` alias of
  `reset_wip_state` for API symmetry.
- `pages/0_Brand_Profile.py` brand-switch confirmation now shows a
  concrete WIP inventory ("3 collections from gsc · 2 in batch · 1
  audit result") instead of the abstract warning.
- `core/data_ingestion.CollectionGroup` and `core/brief_builder.ContentBrief`
  fields gained `Field(description=...)` for the existing-content split
  (top/bottom/other) and the scraper-hydrated fields. Pure documentation.
- `core/brand_profile.BrandPromptOverrides.dedup_overrides` — explicit
  per-brand normalisation map for keywords (case-insensitive lookup).
  Surfaced as an advanced expander on the Brand Profile page. Threaded
  through `_normalise_for_dedup` / `_deduplicate_keywords` and
  `build_brief` reads it from `prompt_overrides`.
- `core/brand_profile.BrandProfile.humanize_by_default` — when set, the
  "Apply to Session" path seeds `st.session_state.humanize_enabled`.

**Files touched:** `app.py`, `core/brand_profile.py`,
`core/brief_builder.py`, `core/data_ingestion.py`,
`pages/0_🏷️_Brand_Profile.py`, `tests/test_app.py`,
`tests/test_brand_profile.py`, `tests/test_brief_builder.py`.

### UX precision (Commit 2)

- `core/telemetry.py`: `new_correlation_id()` generates short hex IDs;
  `log_event` and `timed` accept a `correlation_id` parameter that
  lands in the JSON payload only when set. Sample rate is read from
  `TELEMETRY_SAMPLE_RATE` on every call (0.0 silences everything).
- `core/content_generator.py`: `generate_content` and `humanize_content`
  mint one correlation ID and propagate it through every `bifrost_call`
  event. Failed attempts emit a `model_attempt_failed` event.
  `model_fallback` now carries `selected_model` + `succeeded_model` +
  `attempts` count so fallback flow is reconstructable from logs alone.
- `pages/2_Priority_Scoring.py`: sub-collection opportunity computation
  is now hash-cached on collection URLs. `_opps_cache_key` is registered
  as an internal cache key so brand switches reset it.
- `pages/5_Export.py`: Test Run mode is visible in deliverables — top
  error banner, `TESTRUN_` filename prefix on every download, and an
  inline "NOT FOR CLIENT DELIVERY" banner on each copy-paste card.
- `core/exporter.export_shopify_csv` accepts `test_run=` and prepends
  a `# TEST RUN OUTPUT` + `# Generated on <ts>` comment header.
  Matrixify ignores `#`-prefixed lines so the import still works.

**Files touched:** `core/telemetry.py`, `core/content_generator.py`,
`core/exporter.py`, `pages/2_🎯_Priority_Scoring.py`,
`pages/5_📦_Export.py`, `tests/test_telemetry.py`,
`tests/test_exporter.py`.

### Closing loops (Commit 3)

- `core/generation_history.py` (new): `append_snapshot` captures only
  `SNAPSHOT_FIELDS` (seo_title, collection_title, description,
  meta_description, faqs, suggested_headings, suggested_tags, alt_text),
  never recurses into the history list, caps at `MAX_HISTORY` (10)
  entries. `restore_snapshot` rolls back without losing later history.
- `pages/4_Content_Studio.py`: every successful generation (per-collection
  and Generate All) snapshots prior content before overwriting. New
  📜 History tab between Brief and Description with per-entry ⏪ Restore
  button. Generation metadata (`_humanized`, `_generated_at`,
  `_model_used`, `_generation_type`) tracked on content so snapshots
  are correctly labelled. `_handle_result` stashes `_last_used_model`
  on session state so the snapshotter sees the actual model used.
- `pages/3_Audit.py`: new "🔄 Re-audit with generated content" action
  audits each collection's generated content as a separate result set
  stored under `audit_results_generated`. Per-collection display shows
  a 🟢/🟡/🔴 before/after score line plus a check-by-check diff expander
  (Fixed / Still failing / Regressed).

**Files touched:** `core/generation_history.py` (new),
`pages/3_🔍_Audit.py`, `pages/4_✍️_Content_Studio.py`,
`tests/test_generation_history.py` (new), `tests/test_auditor.py`.

### Architecture (Commit 4)

- `core/content_cache.py` (new): cross-run cache keyed on
  `(brand, URL, primary_keyword)`. JSON-on-disk under
  `data/content_cache/` (gitignored). `hash_inputs(brief)` fingerprints
  the brief signal so `diff_inputs(old, new)` can later flag "secondary
  keywords, voice notes" as changed since cache write.
- `core/rate_limiter.py` (new): `AdaptiveRateLimiter` — token bucket
  sized from `BIFROST_RATE_LIMIT_RPM` (default 5). `record_429()` halves
  rate, `_maybe_recover_locked` restores after the configurable recovery
  window. Thread-safe; injectable time/sleep for tests. Module-level
  `get_limiter()` singleton.
- `core/content_generator._call_bifrost` consults the limiter before
  every request, calls `on_wait(seconds)` when throttling, and
  records 429s via `limiter.record_429()`. Emits `rate_limit_wait`
  and `rate_limit_429` telemetry events.
- `core/orchestrator.py` (new): `generate_for_batch(briefs, config,
  …callbacks)` — pure Python, no Streamlit. `GenerationConfig` and
  `GenerationResult` dataclasses. Callbacks (`on_start`, `on_progress`,
  `on_throttle`, `cancel_check`) make the orchestrator headless. Skips
  already-generated entries unless `force_regenerate=True`. Cancelled
  briefs are returned in order with `cancelled=True`. Callback
  exceptions are swallowed so a broken UI shim can't stop a batch.
- `pages/4_Content_Studio.py._run_generate_all` is now a thin shim
  over the orchestrator — builds config from session state, supplies
  Streamlit progress / status / spinner shims as callbacks, snapshots
  prior content + tags metadata on each on_progress.
- `.gitignore`: added `data/content_cache/`.

**Files touched:** `core/content_cache.py` (new), `core/rate_limiter.py`
(new), `core/orchestrator.py` (new), `core/content_generator.py`,
`pages/4_✍️_Content_Studio.py`, `.gitignore`,
`tests/test_content_cache.py` (new), `tests/test_rate_limiter.py` (new),
`tests/test_orchestrator.py` (new).

---

## Update — Logic fixes (correctness, behaviour, new features)

Twelve issues from a logic review, landed across three commits.

### Correctness fixes (Commit 1)

- New `core/text_utils.py` with `clean_keyword`, `extract_collection_handle`,
  `extract_collection_name`, `ensure_v1_path`. Replaces duplicated inline
  implementations across `data_ingestion`, `scraper`, `auditor`, `exporter`,
  `content_generator`, `feedback_extractor`, and several pages.
- `clean_keyword` applied at every text-input boundary (primary keyword
  swap on Data Input; collection name, primary, secondary keywords on
  Single URL Writer; USPs / banned phrases / voice / brand name / past
  feedback on Brand Profile; FAQ Q&A, headings, tags on Content Studio;
  scraped product names / alt text / existing copy / meta fields in
  `scraper`).
- `ensure_v1_path` uses proper URL parsing — fixes a base URL like
  `/v1/foo` becoming `/v1/foo/v1` because the previous positional
  suffix check ignored deeper path segments.
- `app.init_session_state` rebuilt: every default constructed fresh per
  call so mutating `client_profile` in place no longer taints a future
  initialisation. New `WIP_DEFAULT_FACTORIES` registry + `reset_wip_state`
  helper used by the brand-switch flow.
- `_PLURAL_SUFFIXES` hardcoded list replaced with `_normalise_for_dedup` —
  handles `-ies` → `-y`, `-es` strip, `-s` strip, preserves `-ss`
  (dress, glass), protects 3-character stems (gas, bus).
- Replaced deprecated `use_container_width=True/False` with
  `width="stretch"/"content"` across all pages.

**Files touched:** `core/text_utils.py` (new), `core/data_ingestion.py`,
`core/scraper.py`, `core/exporter.py`, `core/brief_builder.py`,
`core/content_generator.py`, `core/feedback_extractor.py`,
`app.py`, `pages/0_🏷️_Brand_Profile.py`, `pages/1_📊_Data_Input.py`,
`pages/2_🎯_Priority_Scoring.py`, `pages/3_🔍_Audit.py`,
`pages/4_✍️_Content_Studio.py`, `pages/6_✏️_Single_URL_Writer.py`,
`tests/test_text_utils.py` (new), `tests/test_app.py` (new),
`tests/test_brief_builder.py`.

### Behaviour fixes (Commit 2)

- `batch_faq_topics` resets when the batch composition changes in
  Priority Scoring; regenerating FAQs for a single collection drops that
  collection's own prior questions from the exclusion list so the model
  isn't artificially constrained.
- "📋 Apply to Session" on Brand Profile now gates on a confirmation
  when WIP state exists (collections, batch, generated content, audits,
  Single URL Writer). Uses `reset_wip_state` — credentials, model,
  DataForSEO creds are never touched.
- Test Run mode is now a hard cap of 2 collections. The Confirm button
  disables, an inline error explains why, and a banner at the top of
  Priority Scoring surfaces the active model.
- `ContentBrief` gained `existing_top_copy` / `existing_bottom_copy`.
  `build_briefs_for_batch` populates them structurally rather than
  concatenating into a blob. New `_existing_content_block` helper in
  `content_generator` emits labelled sections so the model sees which
  part is top vs bottom; whole block is omitted when nothing is provided.
- `FallbackScrapeResult` gained `all_attempts` keyed by tier name. The
  Audit page surfaces a "pick a tier manually" expander when no tier
  hit ≥2 fields, with per-tier field counts and one-click apply.
- `export_keyword_map_roundtrip` accepts `keyword_width` and emits that
  many keyword/volume column pairs instead of hardcoding 4. Data Input
  stores `source_keyword_width` during keyword_map ingestion; Export
  page passes it through.

**Files touched:** `core/brief_builder.py`, `core/content_generator.py`,
`core/scraper.py`, `core/exporter.py`, `pages/0_🏷️_Brand_Profile.py`,
`pages/1_📊_Data_Input.py`, `pages/2_🎯_Priority_Scoring.py`,
`pages/3_🔍_Audit.py`, `pages/4_✍️_Content_Studio.py`,
`pages/5_📦_Export.py`, `tests/test_brief_builder.py`,
`tests/test_content_generator.py`, `tests/test_scraper.py`,
`tests/test_exporter.py` (new).

### New behaviour (Commit 3)

- Sub-collection opportunities now wired into project lifecycle.
  Priority Scoring computes opportunities once, surfaces a `💡 N sub-opps`
  badge next to each collection that has them, and an inline expander
  shows the modifier keywords + volumes. Export page gains a
  "Sub-Collection Opportunities for Next Phase" section with a CSV
  download (keyword, search_volume, parent_collection, parent_url,
  suggested_handle) so the agency walks away with a next-month scope
  artefact. Sub-opportunities are deliberately NOT shown inside Content
  Studio.
- New `core/telemetry.py` with `log_event` and `timed` context manager.
  Emits single-line JSON to stdout (caught by Streamlit Cloud's log
  viewer). Wired into `_call_bifrost` (`bifrost_call` per request with
  `model`, `generation_type`, `duration_ms`, `status`), `generate_content`
  and `humanize_content` (`model_fallback` when a non-primary model
  succeeds), `scrape_with_fallback` (`scrape_attempt` per tier),
  `feedback_extractor.extract_banned_phrases` (`feedback_extraction`
  with `phrase_count`, `feedback_length`, `model`). Never logs raw
  prompts, responses, API keys, USPs, or voice notes. `print` failure
  is swallowed silently.

**Files touched:** `core/telemetry.py` (new), `core/content_generator.py`,
`core/scraper.py`, `core/feedback_extractor.py`,
`pages/2_🎯_Priority_Scoring.py`, `pages/5_📦_Export.py`,
`tests/test_telemetry.py` (new), `tests/test_priority_scorer.py`.

---

## Update — UI/UX polish from heuristic audit

Eleven small UX fixes landed together. None change behaviour or data
models — all additive at the display layer. Help text and labels written
in en-GB to match the methodology.

- **Tooltips on every Priority Scoring factor** — each of the six score
  selectboxes (Traffic, Striking Distance, Revenue, Nav Link, Optimisation,
  Competitive Gap) now carries a `help=` explaining what it measures and
  how 1/2/3 are determined. The mode radio gained richer help covering
  Test Run / Standard Batch / Full Run.
- **Defaulted-data warnings inline with collections** — under each manual
  override row, a single-line caption explains which factors fell back to
  defaults because rank, difficulty, or crawl data was missing.
- **Sample template downloads on Data Input** — three CSV templates
  (GSC, Ahrefs, Keyword Map) shipped under `static/templates/` and
  surfaced as download buttons below the file uploader. New
  `core.data_ingestion.load_sample_template(format_key)` helper.
- **Primary action hierarchy cleanup** — at most one primary button per
  visible group: Content Studio (Approve and Copy-All demoted),
  Audit (per-row Run Audit demoted), Export (only Round-Trip OR Shopify
  CSV is primary depending on `source_format`).
- **Loading spinner on Process Data** — both keyword-map and
  standard-format Process Data buttons now wrap the work in
  `st.spinner` so the user sees activity.
- **Empty state messaging on Data Input** — when no file is uploaded, a
  bordered container with format-specific export instructions surfaces
  instead of empty space.
- **Header weight fixes** — verified all `st.markdown("## …")` calls
  represent top-level page sections rather than sub-sections. Updated
  "Optimization" → "Optimisation" for en-GB consistency.
- **Status icons paired with text labels (a11y)** — audit checks and
  validation results now render as `✅ **Pass**`, `❌ **Fail/Error**`,
  `⚠️ **Review**` so colourblind users and screen readers get the same
  signal as sighted users. 10 validation-rendering sites updated in
  Content Studio + Single URL Writer.
- **Content Studio brief-tab state summary** — when content already
  exists for a collection, the Brief tab shows a one-line summary
  (word count, FAQ count, approval state) before the form so the user
  doesn't have to click around to see status.
- **Help & docs block in sidebar** — `app.py` sidebar gained a Help
  section with links to README, methodology, and issues, plus a
  version caption.
- **Pre-flight summary before bulk generation** — Content Studio's
  "Generate All" gates on a confirmation step when the batch exceeds 10
  collections. Surfaces model, humaniser multiplier, ETA, and the
  already-generated skip count (which respects the existing
  `force_regenerate` toggle).

**Files touched:** `app.py`,
`pages/1_📊_Data_Input.py`, `pages/2_🎯_Priority_Scoring.py`,
`pages/3_🔍_Audit.py`, `pages/4_✍️_Content_Studio.py`,
`pages/5_📦_Export.py`, `pages/6_✏️_Single_URL_Writer.py`,
`core/data_ingestion.py`,
`static/templates/sample_gsc.csv` (new),
`static/templates/sample_ahrefs.csv` (new),
`static/templates/sample_keyword_map.csv` (new).

---

## Fix — `CollectionGroup` Pydantic strict-mode error

The Shopify scraper handler on `pages/1_📊_Data_Input.py` assigns
`products_to_link`, `scraped_products`, `existing_top_copy`, and
`existing_bottom_copy` on each `CollectionGroup`, but those fields were never
declared on the model. Pydantic v2 raised
`ValueError: "CollectionGroup" object has no field "products_to_link"` and
broke the "🔍 Scrape products for all collections" button end-to-end.

- `core/data_ingestion.py`: declared the four missing fields on
  `CollectionGroup` with empty defaults so the scraper can hydrate them.
- `tests/test_data_ingestion.py`: added `TestCollectionGroupScraperFields`
  covering assignment + default values.

**Files touched:** `core/data_ingestion.py`, `tests/test_data_ingestion.py`.

## Update — Sitemap ingestion at the Brand Profile level

Brand profiles can now hold a parsed sitemap of the client store. When
present, generated copy picks real, indexable URLs for internal links —
products, collections, and blog posts — instead of inventing paths.

### Core

- New `core/sitemap.py` with:
  - `SitemapUrl` / `ParsedSitemap` dataclasses, JSON round-trip via
    `to_dict` / `from_dict`.
  - `fetch_sitemap(url, …)` — fetches and parses a sitemap or sitemap index;
    recurses one level so the typical Shopify `/sitemap.xml` index expands to
    its per-type children. Handles `.xml.gz` via stdlib `gzip`. Caps total
    URLs at `5000` by default. Never raises — errors surface via the
    `error` field.
  - `parse_sitemap_file(bytes, …)` — same parser, no network.
  - `find_related_urls(primary_keyword, secondary_keywords, sitemap,
    target_url, …)` — picks best-matching sitemap URLs (excluding the page
    being written) for products / collections / blog posts. Uses
    `difflib.SequenceMatcher`, no new dependencies.
- `core/brand_profile.py`: `BrandProfile` gained `sitemap_url`,
  `sitemap_parsed` (stored as the `to_dict()` form so JSON serialization is
  clean), and `sitemap_fetched_at`. New helpers `get_sitemap(profile)` and
  `refresh_profile_sitemap(profile)`.
- `core/brief_builder.py`: `ContentBrief` gained `related_blog_posts`.
  `build_brief` and `build_briefs_for_batch` accept an optional `sitemap=`
  argument and fill empty link slots from sitemap matches; existing user-
  supplied links are always preserved.
- `core/content_generator.py`: `build_full_brief_prompt`,
  `build_description_prompt`, `build_bottom_copy_prompt` now inject a
  `{related_blog_posts}` block.

### Prompts

- `prompts/full_brief_prompt.txt`, `prompts/description_prompt.txt`,
  `prompts/bottom_of_page_copy_prompt.txt`: new "Related Blog Posts" input
  block + an explicit "MAY include 1 blog post link if genuinely relevant"
  rule. Skipped when no blog post is provided — never force-fit.

### UI

- `pages/0_🏷️_Brand_Profile.py`: new **Site Structure** section between
  Past feedback and FAQ Settings, with tabs for Fetch from URL and Upload
  File, post-parse summary (count per category), URL preview expander,
  Refresh button (disabled for uploaded files), and a status banner at
  the top of the page.
- `pages/1_📊_Data_Input.py`: status banner mirroring the Brand Profile
  page. The "🔍 Scrape products for all collections" button falls back to
  sitemap suggestions for any collection where the live scrape returns no
  products — surfaced in the completion message.
- `pages/6_✏️_Single_URL_Writer.py`: new "Related Blog Posts to Link" text
  area; the "🔍 Fetch" button pre-fills related collections + blog posts
  (and products as a fallback) from the loaded sitemap.

### Constraints respected

- No new pip dependencies — stdlib `xml.etree`, `gzip`, `urllib.parse`,
  `difflib` plus already-vendored `requests`.
- Sitemap is optional throughout — every reference is guarded so existing
  flows behave exactly as before when no sitemap is loaded.
- Parsed sitemap is cached on the brand profile JSON; no re-fetch on each
  session.

### Tests

- New `tests/test_sitemap.py` covering URL classification, title-from-handle
  derivation, urlset parsing, sitemapindex recursion, gzip decompression,
  the `max_urls` cap, malformed-XML / network-error handling, dict
  round-trip, `find_related_urls` (caps, target-URL exclusion, score
  ordering).
- `tests/test_brand_profile.py`: sitemap round-trip + `get_sitemap` reconstruction.
- `tests/test_brief_builder.py`: sitemap fallback fills empty link slots,
  preserves existing user-supplied links, no-op when sitemap is None.
- New fixtures under `tests/fixtures/`: `sample_sitemap.xml`,
  `sample_sitemap_index.xml`, `sample_sitemap_products.xml`,
  `sample_sitemap_collections.xml`.

**Files touched:**
`core/sitemap.py` (new), `core/brand_profile.py`, `core/brief_builder.py`,
`core/content_generator.py`,
`prompts/full_brief_prompt.txt`, `prompts/description_prompt.txt`,
`prompts/bottom_of_page_copy_prompt.txt`,
`pages/0_🏷️_Brand_Profile.py`, `pages/1_📊_Data_Input.py`,
`pages/6_✏️_Single_URL_Writer.py`,
`tests/test_sitemap.py` (new), `tests/test_brand_profile.py`,
`tests/test_brief_builder.py`,
`tests/fixtures/sample_sitemap*.xml` (new).

---

## Update — Past feedback log + softer brand voice quotas

**Prompt 6 — two related changes in one pass**

### Part A — Past feedback
- `BrandProfile.past_feedback: str = ""` stores freeform client feedback across saves.
- `BrandPromptOverrides.banned_phrases: list[str]` stores extracted phrase bans.
- New `build_brand_custom_context(profile: dict) -> str` in `core/brand_profile.py`:
  surfaces past feedback + banned phrases at the system-prompt level so every
  generation pass applies lessons from prior reviews.
- `ContentBrief.past_feedback: str = ""` forwards feedback to prompt builders.
- `build_brief` and `build_briefs_for_batch` read `past_feedback` from client profile.
- `build_system_prompt` calls `build_brand_custom_context` and passes result as
  `{brand_custom_context}` into `prompts/system_prompt.txt`.
- Brand Profile page gains a **Past feedback** textarea + "🔍 Extract bans from
  feedback" button (Haiku-powered, manual trigger). Extracted phrases are shown
  with checkboxes before being merged into the banned phrases field.
- New `core/feedback_extractor.py` with `extract_banned_phrases(api_key, feedback)`.

### Part B — Softer brand voice quotas
- All USP requirements changed from mandatory to advisory across all prompts.
- `prompts/system_prompt.txt`: removed `{min_usps}` quota; model uses USPs at
  its discretion rather than as a checklist.
- `prompts/description_prompt.txt`, `prompts/bottom_of_page_copy_prompt.txt`,
  `prompts/full_brief_prompt.txt`: replaced "Reference at least N brand USPs"
  with optional guidance.
- `prompts/faq_prompt.txt`: brand specificity rule softened to avoid shoehorning
  the brand name into every answer.
- `core/validator.py`: USP and secondary keyword checks in `validate_description`
  and `validate_bottom_copy` now always pass (`passed=True`) with advisory messages.
- `config/methodology_rules.json`: added `top_copy_suggested_usps`,
  `bottom_copy_suggested_usps`, `bottom_copy_suggested_secondary_keywords` keys.
- `config/audit_checklist.json`: `description_mentions_usps` impact changed
  `"high"` → `"low"`.

**Files touched:** `core/brand_profile.py`, `core/brief_builder.py`,
`core/content_generator.py`, `core/validator.py`,
`core/feedback_extractor.py` (new),
`config/methodology_rules.json`, `config/audit_checklist.json`,
`prompts/system_prompt.txt`, `prompts/description_prompt.txt`,
`prompts/bottom_of_page_copy_prompt.txt`, `prompts/full_brief_prompt.txt`,
`prompts/faq_prompt.txt`,
`pages/0_🏷️_Brand_Profile.py`, `pages/6_✏️_Single_URL_Writer.py`,
`tests/test_brand_profile.py` (extended),
`tests/test_feedback_extractor.py` (new).

---


## Update — KD-scaled bottom copy length

**Prompt 1 — `calculate_target_word_counts` + bottom copy scaling**

Bottom-of-page copy targets now scale with keyword difficulty across three brackets:

| KD range | Bottom-copy target |
|---|---|
| < 20 | 125 words (tight, low competition) |
| 20–39 | 250 words (standard) |
| 40–59 | 500 words (substantial depth) |
| ≥ 60 | 800 words (deep buyer guide) |
| `None` (unknown) | 200 words (safe midpoint) |

Hard ceiling raised to 1,100 words (global config). H2 sections used when target > 250 words.

**Files touched:** `config/methodology_rules.json`, `core/brief_builder.py`,
`core/validator.py` (new `validate_bottom_copy`), `core/content_generator.py`
(new `build_bottom_copy_prompt`, `build_alt_text_prompt`),
`prompts/bottom_of_page_copy_prompt.txt` (new), `prompts/full_brief_prompt.txt`,
`tests/test_brief_builder.py` (new).

---

## Update — FAQ count widened to 3–5

**Prompt 2 — default 4, range 3–8, brand profile override**

- `methodology_rules.json` FAQ block: `count_min: 3`, `count_max: 8`, `count_default: 4`.
- `ContentBrief.faq_count` default changed from 3 → 4.
- `build_briefs_for_batch` reads `faq_count` from `client_profile` (set by Brand Profile page).
- New `core/brand_profile.py` with `BrandProfile` dataclass, `save_profile`/`load_profile`.
- New `pages/0_🏷️_Brand_Profile.py` for per-client profile management.

**Files touched:** `config/methodology_rules.json`, `core/brief_builder.py`,
`core/brand_profile.py` (new), `pages/0_🏷️_Brand_Profile.py` (new),
`tests/test_brand_profile.py` (new).

---

## Update — FAQ + ItemList JSON-LD schema

**Prompt 3 — pure-function schema generators, no LLM call**

- New `core/schema.py` with `build_faq_schema`, `build_itemlist_schema`, `schema_to_script_tag`.
- `core/exporter.py`: new `_build_shopify_body_html` helper used by `export_shopify_csv`;
  `generate_copy_paste_cards` now includes `faq_schema_html` + `item_schema_html`.
- Content Studio and Single URL Writer FAQ tab: collapsible `<script type="application/ld+json">`
  block for copy-paste into Shopify.

**Files touched:** `core/schema.py` (new), `core/exporter.py`,
`pages/4_✍️_Content_Studio.py`, `pages/6_✏️_Single_URL_Writer.py`,
`tests/test_schema.py` (new).

---

## Update — Shopify product scraping

**Prompt 4 — JSON-first, HTML fallback**

`fetch_collection_data(url)` added to `core/scraper.py`:

1. Always fetches the page HTML for H1, meta title, meta description, existing copy.
2. Tries `<url>/products.json?limit=50` — clean, fast, schema-stable.
3. Falls back to HTML product-card selectors when JSON returns nothing.
4. Returns `CollectionPageData` with `source` set to `json | html | mixed | failed`.

**Data Input page** gains a "🔍 Scrape products for all collections" button that
hydrates each collection with real product names + URLs and existing page copy.

**Single URL Writer** gains a "🔍 Fetch" button next to the URL field that
pre-fills Products, Collection Name, and existing copy fields.

`build_briefs_for_batch` wires `existing_top_copy` + `existing_bottom_copy` from
scraped data into `brief.existing_content`.

**Files touched:** `core/scraper.py`, `core/brief_builder.py`,
`pages/1_📊_Data_Input.py`, `pages/6_✏️_Single_URL_Writer.py`,
`tests/test_scraper.py` (new).

---

## Update — Product image alt-text generator

**Prompt 5 — Haiku-based per-product alt text, XLSX export**

- New `prompts/alt_text_prompt.txt` — 5-12 word descriptive alt text, brand-aware.
- New `core/alt_text_generator.py` — `generate_alt_text_batch(api_key, brief, products)`.
- `GeneratedContent.alt_text: str = ""` added for the `alt_text` generation type.
- `generate_content` accepts `generation_type="alt_text"` with `product=` kwarg.
- `core/brand_profile.py` `BrandPromptOverrides` gains `alt_text_rules` + `alt_text_examples`.
- `core/exporter.py` gains `export_alt_text(results) -> BytesIO` (Matrixify-compatible XLSX).
- Content Studio gains "🖼️ Alt Text" tab per collection (requires scraped products).
- Export page aggregates alt results across all collections for download.
- Default model: `claude-haiku-4-5-20251001`. Cap: 50 products per batch.

**Files touched:** `prompts/alt_text_prompt.txt` (new),
`core/alt_text_generator.py` (new), `core/content_generator.py`,
`core/brand_profile.py`, `core/exporter.py`,
`pages/0_🏷️_Brand_Profile.py`, `pages/4_✍️_Content_Studio.py`,
`pages/5_📦_Export.py`.
