"""Claude API integration and prompt construction for content generation."""

import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from core.brief_builder import ContentBrief


class GeneratedContent(BaseModel):
    """Generated content for a collection."""

    collection_url: str
    collection_name: str
    seo_title: str = ""
    collection_title: str = ""
    description: str = ""
    meta_description: str = ""
    faqs: list[dict] = Field(default_factory=list)  # [{question, answer}]
    suggested_headings: list[str] = Field(default_factory=list)
    suggested_tags: list[str] = Field(default_factory=list)
    approved: bool = False


def _load_prompt(filename: str) -> str:
    """Load a prompt template from the prompts directory."""
    prompt_path = Path(__file__).parent.parent / "prompts" / filename
    with open(prompt_path) as f:
        return f.read()


def _load_methodology_rules() -> dict:
    """Load methodology rules."""
    import json

    config_path = Path(__file__).parent.parent / "config" / "methodology_rules.json"
    with open(config_path) as f:
        return json.load(f)


def build_system_prompt(brief: ContentBrief) -> str:
    """Build the system prompt from template and brief data."""
    rules = _load_methodology_rules()
    template = _load_prompt("system_prompt.txt")

    cl = rules["content_length"]["description"]
    ci = rules["content_inclusion"]

    return template.format(
        min_words=cl["sweet_spot_min"],
        max_words=cl["sweet_spot_max"],
        hard_ceiling=cl["hard_ceiling"],
        min_usps=ci["description_min_usps"],
        min_product_links=ci["description_product_links_min"],
        max_product_links=ci["description_product_links_max"],
        min_collection_links=ci["description_collection_links_min"],
        max_collection_links=ci["description_collection_links_max"],
        brand_name=brief.brand_name,
        store_url=brief.store_url,
        usps="\n".join(f"- {usp}" for usp in brief.brand_usps),
        voice_notes=brief.voice_notes or "No specific voice notes provided.",
        target_market=brief.target_market,
    )


def build_full_brief_prompt(
    brief: ContentBrief, batch_faq_topics: list[str] = None
) -> str:
    """Build the full brief generation prompt."""
    rules = _load_methodology_rules()
    template = _load_prompt("full_brief_prompt.txt")

    cl = rules["content_length"]["description"]
    ci = rules["content_inclusion"]

    product_links_str = (
        "\n".join(f"- [{p['name']}]({p['url']})" for p in brief.products_to_link)
        if brief.products_to_link
        else "No specific products provided — use placeholder product names relevant to the collection."
    )

    related_collections_str = (
        "\n".join(f"- [{c['name']}]({c['url']})" for c in brief.related_collections)
        if brief.related_collections
        else "No related collections provided — use placeholder collection names."
    )

    paa_str = (
        "\n".join(f"- {q}" for q in brief.paa_questions)
        if brief.paa_questions
        else "No PAA data available — generate questions based on secondary keywords."
    )

    batch_note = ""
    if batch_faq_topics:
        batch_note = (
            f"\n- Do NOT use these FAQ topics (already used in this batch): "
            f"{', '.join(batch_faq_topics)}"
        )

    existing_content_block = ""
    if brief.existing_content:
        existing_content_block = (
            "\nEXISTING CONTENT (reference for tone, details, and improvement):\n"
            "The page currently has the following content. Use it as context — retain any "
            "brand-specific facts, product details, or tone that works well, but rewrite and "
            "improve rather than copying:\n"
            f"```\n{brief.existing_content}\n```\n"
        )

    return template.format(
        collection_name=brief.collection_name,
        primary_keyword=brief.primary_keyword,
        volume=brief.primary_keyword_volume or "N/A",
        secondary_keywords=", ".join(brief.secondary_keywords),
        product_links=product_links_str,
        related_collections=related_collections_str,
        paa_questions=paa_str,
        brand_name=brief.brand_name,
        store_url=brief.store_url,
        usps="\n".join(f"- {usp}" for usp in brief.brand_usps),
        voice_notes=brief.voice_notes or "No specific voice notes.",
        target_market=brief.target_market,
        target_word_count=brief.target_word_count,
        min_words=cl["sweet_spot_min"],
        max_words=cl["sweet_spot_max"],
        min_usps=ci["description_min_usps"],
        min_product_links=ci["description_product_links_min"],
        max_product_links=ci["description_product_links_max"],
        min_collection_links=ci["description_collection_links_min"],
        max_collection_links=ci["description_collection_links_max"],
        faq_count=brief.faq_count,
        batch_exclusion_note=batch_note,
        existing_content_block=existing_content_block,
    )


def build_description_prompt(
    brief: ContentBrief,
) -> str:
    """Build the description-only generation prompt."""
    rules = _load_methodology_rules()
    template = _load_prompt("description_prompt.txt")

    cl = rules["content_length"]["description"]
    ci = rules["content_inclusion"]

    product_links_str = (
        "\n".join(f"- [{p['name']}]({p['url']})" for p in brief.products_to_link)
        if brief.products_to_link
        else "No specific products — use placeholder product names."
    )

    related_str = (
        "\n".join(f"- [{c['name']}]({c['url']})" for c in brief.related_collections)
        if brief.related_collections
        else "No related collections — use placeholder names."
    )

    existing_content_block = ""
    if brief.existing_content:
        existing_content_block = (
            "\nEXISTING CONTENT (reference for tone, details, and improvement):\n"
            "The page currently has the following content. Use it as context — retain any "
            "brand-specific facts, product details, or tone that works well, but rewrite and "
            "improve rather than copying:\n"
            f"```\n{brief.existing_content}\n```\n"
        )

    return template.format(
        collection_name=brief.collection_name,
        primary_keyword=brief.primary_keyword,
        volume=brief.primary_keyword_volume or "N/A",
        secondary_keywords=", ".join(brief.secondary_keywords),
        product_links=product_links_str,
        related_collections=related_str,
        target_word_count=brief.target_word_count,
        min_words=cl["sweet_spot_min"],
        max_words=cl["sweet_spot_max"],
        min_usps=ci["description_min_usps"],
        min_product_links=ci["description_product_links_min"],
        max_product_links=ci["description_product_links_max"],
        min_collection_links=ci["description_collection_links_min"],
        max_collection_links=ci["description_collection_links_max"],
        usps="\n".join(f"- {usp}" for usp in brief.brand_usps),
        brand_name=brief.brand_name,
        existing_content_block=existing_content_block,
    )


def build_title_prompt(brief: ContentBrief) -> str:
    """Build the title generation prompt."""
    template = _load_prompt("title_prompt.txt")
    return template.format(
        collection_name=brief.collection_name,
        primary_keyword=brief.primary_keyword,
        volume=brief.primary_keyword_volume or "N/A",
        brand_name=brief.brand_name,
    )


def build_faq_prompt(
    brief: ContentBrief, batch_faq_topics: list[str] = None
) -> str:
    """Build the FAQ generation prompt."""
    template = _load_prompt("faq_prompt.txt")

    paa_str = (
        "\n".join(f"- {q}" for q in brief.paa_questions)
        if brief.paa_questions
        else "No PAA data available — generate based on secondary keywords."
    )

    batch_note = ""
    if batch_faq_topics:
        batch_note = (
            f"- Do NOT use these FAQ topics (already used in this batch): "
            f"{', '.join(batch_faq_topics)}"
        )

    return template.format(
        faq_count=brief.faq_count,
        collection_name=brief.collection_name,
        primary_keyword=brief.primary_keyword,
        secondary_keywords=", ".join(brief.secondary_keywords),
        brand_name=brief.brand_name,
        usps="\n".join(f"- {usp}" for usp in brief.brand_usps),
        paa_questions=paa_str,
        batch_exclusion_note=batch_note,
    )


def parse_full_brief_response(response_text: str) -> dict:
    """Parse the structured response from a full brief generation."""
    result = {
        "seo_title": "",
        "collection_title": "",
        "description": "",
        "meta_description": "",
        "faqs": [],
        "suggested_headings": [],
        "suggested_tags": [],
    }

    # Split into header/content pairs using the ---HEADER--- pattern
    sections = re.split(r"---\s*(.+?)\s*---", response_text)

    # sections[0] is text before first header (usually empty)
    # sections[1] is first header, sections[2] is first content, etc.
    i = 1
    while i < len(sections) - 1:
        header = sections[i].strip().upper()
        content = sections[i + 1].strip()
        i += 2

        if "SEO TITLE" in header:
            result["seo_title"] = content
        elif "COLLECTION TITLE" in header:
            result["collection_title"] = content
        elif "META DESCRIPTION" in header or ("META" in header and "DESCRIPTION" in header):
            result["meta_description"] = content
        elif "SUGGESTED HEADING" in header or header == "HEADINGS":
            result["suggested_headings"] = [
                line.strip().lstrip("-•* ") for line in content.split("\n")
                if line.strip() and not line.strip().startswith("#")
            ]
        elif "SUGGESTED TAG" in header or header == "TAGS":
            # Tags can be comma-separated on one line or one per line
            if "," in content:
                result["suggested_tags"] = [t.strip() for t in content.split(",") if t.strip()]
            else:
                result["suggested_tags"] = [
                    line.strip().lstrip("-•* ") for line in content.split("\n") if line.strip()
                ]
        elif "DESCRIPTION" in header:
            result["description"] = content
        elif "FAQ" in header:
            result["faqs"] = parse_faqs(content)

    return result


def parse_title_response(response_text: str) -> dict:
    """Parse SEO title and collection title from response."""
    result = {"seo_title": "", "collection_title": ""}

    for line in response_text.strip().split("\n"):
        line = line.strip()
        if line.lower().startswith("seo title:"):
            result["seo_title"] = line.split(":", 1)[1].strip()
        elif line.lower().startswith("collection title:"):
            result["collection_title"] = line.split(":", 1)[1].strip()

    return result


def parse_faqs(text: str) -> list[dict]:
    """Parse FAQ Q&A pairs from response text."""
    faqs = []
    current_q = ""
    current_a = ""

    for line in text.strip().split("\n"):
        line = line.strip()
        if line.upper().startswith("Q:"):
            if current_q and current_a:
                faqs.append({"question": current_q, "answer": current_a})
            current_q = line[2:].strip()
            current_a = ""
        elif line.upper().startswith("A:"):
            current_a = line[2:].strip()
        elif current_a and line:
            current_a += " " + line

    if current_q and current_a:
        faqs.append({"question": current_q, "answer": current_a})

    return faqs


def load_available_models() -> dict:
    """Load available models from config."""
    import json

    config_path = Path(__file__).parent.parent / "config" / "models.json"
    with open(config_path) as f:
        return json.load(f)


def get_model_list() -> list[dict]:
    """Get a flat list of all models in provider_id/model_id format."""
    config = load_available_models()
    models = []
    for provider_name, data in config["providers"].items():
        provider_id = data["provider_id"]
        for model in data["models"]:
            bifrost_id = f"{provider_id}/{model['id']}"
            models.append({
                "id": bifrost_id,
                "label": f"{model['label']}  ({provider_name})",
                "provider": provider_name,
                "provider_id": provider_id,
                "context": model["context"],
                "max_output": model["max_output"],
            })
    return models


def get_default_model() -> str:
    """Get the default model ID (provider_id/model_id format)."""
    config = load_available_models()
    return config.get("default_model", "anthropic/claude-sonnet-4-6")


def get_fallback_chain() -> list[str]:
    """Get the fallback model chain for retry logic."""
    config = load_available_models()
    return config.get("fallback_chain", [])


def _call_bifrost(
    client,
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """Make a single call to Bifrost and return the response text."""
    response = client.chat.completions.create(
        model=model,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content


def build_humanizer_prompt(content_text: str, brand_name: str = "", voice_notes: str = "") -> str:
    """Build the humanizer post-processing prompt."""
    template = _load_prompt("humanizer_prompt.txt")
    return template.format(
        brand_name=brand_name or "the brand",
        voice_notes=voice_notes or "No specific voice notes provided.",
        content_to_humanize=content_text,
    )


def humanize_content(
    api_key: str,
    content_text: str,
    brand_name: str = "",
    voice_notes: str = "",
    model: str = "anthropic/claude-sonnet-4-6",
    base_url: str = "https://bifrost.pattern.com",
) -> tuple[str, str]:
    """Run the humanizer pass on generated content.

    Makes a second LLM call to rewrite content so it reads naturally,
    removing AI artifacts per the 24-pattern audit checklist.

    Returns:
        Tuple of (humanized_text, model_used)
    """
    from openai import OpenAI

    if not base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"

    client = OpenAI(api_key=api_key, base_url=base_url)

    system_prompt = (
        "You are a human editor specializing in ecommerce content. "
        "You rewrite AI-generated text so it reads naturally and specifically. "
        "Preserve all markdown formatting, links, and factual content."
    )
    user_prompt = build_humanizer_prompt(content_text, brand_name, voice_notes)

    fallback_chain = get_fallback_chain()
    models_to_try = [model] + [m for m in fallback_chain if m != model]

    response_text = None
    last_error = None
    used_model = model

    for attempt_model in models_to_try:
        try:
            response_text = _call_bifrost(client, attempt_model, system_prompt, user_prompt)
            used_model = attempt_model
            break
        except Exception as e:
            last_error = e
            continue

    if response_text is None:
        raise RuntimeError(
            f"Humanizer: all models failed. Tried: {', '.join(models_to_try)}. "
            f"Last error: {last_error}"
        )

    return response_text.strip(), used_model


def generate_content(
    api_key: str,
    brief: ContentBrief,
    generation_type: str = "full",
    batch_faq_topics: list[str] = None,
    model: str = "anthropic/claude-sonnet-4-6",
    base_url: str = "https://bifrost.pattern.com",
) -> GeneratedContent:
    """Generate content via Bifrost API gateway (OpenAI-compatible).

    Uses provider_id/model_id format for Bifrost routing.
    On failure, automatically falls through to the next model in the
    fallback chain defined in config/models.json.

    Args:
        api_key: Bifrost API key
        brief: Content brief with all context
        generation_type: "full", "description", "titles", or "faqs"
        batch_faq_topics: FAQ topics already used in this batch
        model: Model ID in provider_id/model_id format (e.g. anthropic/claude-sonnet-4-6)
        base_url: Bifrost API base URL
    """
    from openai import OpenAI

    # OpenAI SDK appends /chat/completions to base_url.
    # Bifrost expects /v1/chat/completions, so ensure base_url ends with /v1
    if not base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"

    client = OpenAI(api_key=api_key, base_url=base_url)
    system_prompt = build_system_prompt(brief)

    if generation_type == "full":
        user_prompt = build_full_brief_prompt(brief, batch_faq_topics)
    elif generation_type == "description":
        user_prompt = build_description_prompt(brief)
    elif generation_type == "titles":
        user_prompt = build_title_prompt(brief)
    elif generation_type == "faqs":
        user_prompt = build_faq_prompt(brief, batch_faq_topics)
    else:
        raise ValueError(f"Unknown generation type: {generation_type}")

    # Build attempt order: selected model first, then fallback chain
    fallback_chain = get_fallback_chain()
    models_to_try = [model] + [m for m in fallback_chain if m != model]

    response_text = None
    last_error = None
    used_model = model

    for attempt_model in models_to_try:
        try:
            response_text = _call_bifrost(client, attempt_model, system_prompt, user_prompt)
            used_model = attempt_model
            break
        except Exception as e:
            last_error = e
            continue

    if response_text is None:
        raise RuntimeError(
            f"All models failed. Tried: {', '.join(models_to_try)}. "
            f"Last error: {last_error}"
        )

    result = GeneratedContent(
        collection_url=brief.collection_url,
        collection_name=brief.collection_name,
    )

    if generation_type == "full":
        parsed = parse_full_brief_response(response_text)
        result.seo_title = parsed["seo_title"]
        result.collection_title = parsed["collection_title"]
        result.description = parsed["description"]
        result.meta_description = parsed["meta_description"]
        result.faqs = parsed["faqs"]
        result.suggested_headings = parsed.get("suggested_headings", [])
        result.suggested_tags = parsed.get("suggested_tags", [])
    elif generation_type == "description":
        result.description = response_text.strip()
    elif generation_type == "titles":
        parsed = parse_title_response(response_text)
        result.seo_title = parsed["seo_title"]
        result.collection_title = parsed["collection_title"]
    elif generation_type == "faqs":
        result.faqs = parse_faqs(response_text)

    return result, used_model
