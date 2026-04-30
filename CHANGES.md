# Changes

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
