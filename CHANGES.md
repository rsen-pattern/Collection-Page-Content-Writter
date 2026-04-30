# Changes

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
