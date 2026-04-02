# Collection SEO Engine

An internal agency tool for auditing and optimizing eCommerce collection pages at scale.

Built on a methodology analysing 300+ top-ranking UK category pages, this Streamlit app turns a manual playbook into a repeatable, AI-assisted workflow — from keyword data ingestion through to Shopify-ready content output.

## What It Does

For a store with 50+ collections, manual optimization takes 15-25 hours per client. This tool compresses that to 2-4 hours of review and refinement.

**Two ways to work:**

- **Single Page Generator** — Enter one collection URL, fill in brand context, generate optimized content immediately. Best for quick jobs.
- **Bulk Generator Pipeline** — Upload CSV keyword data, score and batch collections, run audits, generate content at scale, and export. Best for full client engagements.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     STREAMLIT FRONTEND                       │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  Data     │  │ Priority │  │  Audit   │  │ Content  │    │
│  │  Input    │──│ Scoring  │──│  Engine  │──│ Studio   │──► Export
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│       │                           │              │           │
│       ▼                           ▼              ▼           │
│  ┌──────────┐              ┌──────────┐   ┌──────────┐      │
│  │DataForSEO│              │DataForSEO│   │ Bifrost  │      │
│  │  API     │              │ On-Page  │   │  (LLM    │      │
│  │ + CSV    │              │   API    │   │ Gateway) │      │
│  └──────────┘              └──────────┘   └──────────┘      │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure secrets

**For Streamlit Cloud**, add these in Settings → Secrets:

```toml
BIFROST_API_KEY = "your-bifrost-api-key"
BIFROST_BASE_URL = "https://bifrost.pattern.com"
BIFROST_DEFAULT_MODEL = "anthropic/claude-sonnet-4-6"
```

**For local development**, create `.streamlit/secrets.toml`:

```toml
BIFROST_API_KEY = "your-bifrost-api-key"
BIFROST_BASE_URL = "https://bifrost.pattern.com"
BIFROST_DEFAULT_MODEL = "anthropic/claude-sonnet-4-6"
```

Or set them via the sidebar in the app.

### 3. Run the app

```bash
streamlit run app.py
```

## Project Structure

```
collection-seo-engine/
├── app.py                         # Main Streamlit entry point + routing
├── requirements.txt               # Python dependencies
├── .env.example                   # Template for environment variables
├── .streamlit/
│   └── config.toml                # Streamlit theme configuration
│
├── pages/                         # Streamlit multi-page structure
│   ├── 1_📊_Data_Input.py         # Step 1: CSV upload, format detection, keyword grouping
│   ├── 2_🎯_Priority_Scoring.py   # Step 2: 6-factor scoring, batch builder
│   ├── 3_🔍_Audit.py              # Step 3: Automated audit checklist (22 checks)
│   ├── 4_✍️_Content_Studio.py     # Step 4: AI content generation + live validation
│   ├── 5_📦_Export.py              # Step 5: XLSX, CSV, copy-paste exports
│   └── 6_✏️_Single_URL_Writer.py  # Standalone single-page content writer
│
├── core/                          # Business logic (no Streamlit imports)
│   ├── data_ingestion.py          # CSV parsers, format detection, normalization
│   ├── dataforseo_client.py       # DataForSEO API wrapper (Phase 2)
│   ├── priority_scorer.py         # 6-factor scoring model
│   ├── auditor.py                 # Audit checklist evaluation engine
│   ├── brief_builder.py           # Content brief assembly
│   ├── content_generator.py       # Bifrost/LLM integration + prompt construction
│   ├── validator.py               # Real-time content validation rules
│   └── exporter.py                # XLSX, DOCX, CSV export formatters
│
├── prompts/                       # Prompt templates (easy to iterate without code changes)
│   ├── system_prompt.txt          # Base system prompt
│   ├── description_prompt.txt     # Collection description generation
│   ├── title_prompt.txt           # SEO title + H1 generation
│   ├── faq_prompt.txt             # FAQ generation
│   └── full_brief_prompt.txt      # Full brief package generation
│
├── config/                        # Static configuration
│   ├── audit_checklist.json       # All 22+ audit checks with scoring rules
│   ├── format_mappings.json       # Column mappings for GSC, Ahrefs, SEMrush imports
│   ├── methodology_rules.json     # Playbook rules (word counts, formulas, etc.)
│   └── models.json                # Available LLM models + fallback chain
│
└── tests/
    ├── test_data_ingestion.py
    ├── test_priority_scorer.py
    ├── test_auditor.py
    ├── test_content_generator.py
    └── fixtures/                   # Sample data for testing
        ├── sample_gsc_export.csv
        ├── sample_ahrefs_export.csv
        └── sample_collection_data.json
```

## LLM Integration (Bifrost via Pattern)

All AI content generation routes through **Bifrost** (`https://bifrost.pattern.com`), which provides a unified OpenAI-compatible API gateway to multiple LLM providers.

### Available Models

Models are configured in `config/models.json` using `provider_id/model_id` format:

| Provider | Models |
|----------|--------|
| **Anthropic** | Claude Opus 4.6, Sonnet 4.6, Opus 4.5, Sonnet 4.5, Haiku 4.5 |
| **OpenAI** | GPT-5.4, GPT-5.2, GPT-5.1, GPT-5, GPT-4.1, GPT-4o, o3, o4 |
| **Google** | Gemini 3 Pro, Gemini 3 Flash, Gemini 2.5 Pro/Flash |
| **AWS Bedrock** | Claude models (Bedrock), Amazon Nova 2 Lite, Nova Premier, Nova Pro |

### Fallback Chain

If the selected model fails (rate limit, outage, etc.), the tool automatically tries the next model in the fallback chain:

```
anthropic/claude-sonnet-4-6
  → anthropic/claude-sonnet-4-5
  → anthropic/claude-haiku-4-5
  → openai/gpt-4.1
  → gemini/gemini-2.5-flash
```

The fallback chain is configurable in `config/models.json`.

## Workflow: Bulk Pipeline

### Step 1: Data Input
- Upload CSV/XLSX from Google Search Console, Ahrefs, SEMrush, or custom format
- Auto-detects source format by column headers
- Normalizes to internal schema and groups keywords by collection URL
- Confirm/override primary keyword per collection

### Step 2: Priority Scoring
- Each collection scored 1-3 on 6 factors (max 18): organic traffic, striking distance, revenue potential, homepage link, current optimization, competitive gap
- Manual score overrides available
- Select 3-5 collections as optimization batch
- Sub-collection opportunity detection (modifier keywords with significant volume)

### Step 3: Automated Audit
- 22 checks across 5 categories: SEO title, collection title, description, internal linking, technical SEO
- Each check evaluated as Pass / Fail / Needs Review
- Priority actions ranked by impact and effort

### Step 4: Content Studio
- AI generates full content packages: description, SEO title, H1, meta description, FAQs
- Live validation against playbook methodology rules
- Per-element regeneration with fallback support
- Batch generation for all collections at once

### Step 5: Export
- **Keyword Map XLSX** — matches toolkit schema with optimized columns
- **Content Delivery XLSX** — per-collection sheets for client handoff
- **Shopify Bulk CSV** — Matrixify-compatible import format
- **Copy-Paste Cards** — markdown + HTML ready for Shopify admin
- **Implementation Tracker** — track content status and deployment

## Workflow: Single Page Generator

A streamlined flow for one-off pages:

1. Enter collection URL, name, primary keyword, brand details
2. Add products to link, related collections, PAA questions
3. Select model and click Generate
4. Review with live validation, edit, regenerate individual elements
5. Copy-paste or download Shopify CSV

## Methodology Rules

These are encoded as hard constraints in the generation prompts:

- **Description length:** 50-125 words (sweet spot), 200 word warning, 400 word hard ceiling
- **USP references:** minimum 2 per description
- **Internal links:** 2-4 product links + 1-2 collection links per description
- **SEO title formula:** `[Primary Keyword] | [Variation / USP] | For Sale at [Brand]`
- **Competitor test:** Content must include brand-specific details that couldn't appear on a competitor's page
- **No definitions:** Never generate "What is [product]?" content
- **FAQ deduplication:** No duplicate topics across collections in the same batch

Rules are stored in `config/methodology_rules.json` and can be updated without code changes.

## Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

58 tests covering data ingestion, priority scoring, audit engine, and content generator (prompt building + response parsing).

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Frontend | Streamlit | UI framework, multi-page app |
| AI Gateway | Bifrost (Pattern) | Unified LLM API with model fallback |
| Data Processing | Pandas | Data normalization, analysis |
| Excel I/O | OpenPyXL | Read/write XLSX |
| Validation | Pydantic | Data models, input validation |
| HTTP | httpx | Async API calls |
| LLM SDK | OpenAI SDK | Bifrost-compatible API client |

## Development Phases

- **Phase 1 (Current):** CSV upload → priority scoring → AI content generation → XLSX/CSV export
- **Phase 2:** DataForSEO integration for automated data gathering and on-page audits
- **Phase 3:** Content Studio polish — side-by-side views, content history, brand voice learning
- **Phase 4:** Shopify Admin API integration, multi-client project management
