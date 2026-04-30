"""Bulk alt-text generation for scraped product images.

Runs the alt_text generation type for each product in a collection's scraped
product list. Returns a list of result dicts ready for export or display.

Defaults to Haiku for cost efficiency — alt text is a short prompt with a
short output. Override per-client via brand profile if quality is a concern.
"""

from __future__ import annotations

from core.brief_builder import ContentBrief
from core.content_generator import generate_content

_DEFAULT_MODEL = "anthropic/claude-haiku-4-5-20251001"
_MAX_PRODUCTS = 50


def generate_alt_text_batch(
    api_key: str,
    brief: ContentBrief,
    products: list[dict],
    model: str = _DEFAULT_MODEL,
    base_url: str = "https://bifrost.pattern.com",
    max_products: int = _MAX_PRODUCTS,
) -> list[dict]:
    """Generate alt text for a batch of products.

    Args:
        api_key: Bifrost API key.
        brief: ContentBrief for brand context and custom rules.
        products: List of product dicts with `name`, `handle`, `image`, `image_alt`,
                  and optionally `product_type`.
        model: Model to use (defaults to Haiku for cost/speed).
        base_url: Bifrost API base URL.
        max_products: Cap to prevent runaway costs on large collections.

    Returns:
        List of dicts: {handle, name, image, original_alt, suggested_alt, model_used}
    """
    results = []
    for product in products[:max_products]:
        suggested_text = ""
        used_model = model
        try:
            result, used_model = generate_content(
                api_key=api_key,
                brief=brief,
                generation_type="alt_text",
                model=model,
                base_url=base_url,
                product=product,
            )
            suggested_text = result.alt_text
        except Exception:
            pass

        results.append({
            "handle": product.get("handle", ""),
            "name": product.get("name", ""),
            "image": product.get("image", ""),
            "original_alt": product.get("image_alt", ""),
            "suggested_alt": suggested_text,
            "model_used": used_model,
        })
    return results
