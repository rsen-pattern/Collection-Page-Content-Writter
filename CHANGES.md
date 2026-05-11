# Changes

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
