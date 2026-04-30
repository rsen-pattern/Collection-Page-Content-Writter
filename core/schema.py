"""JSON-LD structured data generators for collection pages.

Pure transforms — no LLM calls. Builds the schema dicts from existing content
(FAQ pairs, product lists) and wraps them in <script> tags ready to drop into
the page Body HTML.
"""

from __future__ import annotations

import json
from typing import Optional
from urllib.parse import urljoin


def build_faq_schema(faqs: list[dict]) -> Optional[dict]:
    """Build a FAQPage JSON-LD dict from FAQ Q&A pairs.

    Returns None when faqs is empty so callers can skip emission.
    """
    if not faqs:
        return None

    main_entity = []
    for faq in faqs:
        question = (faq.get("question") or "").strip()
        answer = (faq.get("answer") or "").strip()
        if not question or not answer:
            continue
        main_entity.append({
            "@type": "Question",
            "name": question,
            "acceptedAnswer": {
                "@type": "Answer",
                "text": answer,
            },
        })

    if not main_entity:
        return None

    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": main_entity,
    }


def build_itemlist_schema(
    products: list[dict],
    collection_url: str,
    collection_name: str = "",
) -> Optional[dict]:
    """Build an ItemList JSON-LD dict from a product list.

    `products` is a list of dicts with at least `name` and `url`. Optional
    keys: `image`, `price`, `currency`. Relative URLs are resolved against
    the collection URL's origin when possible.
    """
    if not products:
        return None

    items = []
    for i, product in enumerate(products, start=1):
        name = (product.get("name") or "").strip()
        url = (product.get("url") or "").strip()
        if not name or not url:
            continue

        absolute_url = urljoin(collection_url, url) if collection_url else url

        item: dict = {
            "@type": "ListItem",
            "position": i,
            "item": {
                "@type": "Product",
                "name": name,
                "url": absolute_url,
            },
        }
        if product.get("image"):
            item["item"]["image"] = product["image"]
        if product.get("price") and product.get("currency"):
            item["item"]["offers"] = {
                "@type": "Offer",
                "price": str(product["price"]),
                "priceCurrency": product["currency"],
            }
        items.append(item)

    if not items:
        return None

    schema: dict = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": items,
    }
    if collection_name:
        schema["name"] = collection_name
    return schema


def schema_to_script_tag(schema: Optional[dict]) -> str:
    """Wrap a schema dict in a <script type='application/ld+json'> tag.

    Returns empty string when schema is None. The `</` sequence is escaped to
    `<\\/` to prevent premature script tag termination (XSS defence).
    """
    if schema is None:
        return ""
    payload = json.dumps(schema, ensure_ascii=False, indent=2)
    payload = payload.replace("</", "<\\/")
    return f'<script type="application/ld+json">\n{payload}\n</script>'
