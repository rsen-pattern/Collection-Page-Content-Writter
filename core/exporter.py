"""XLSX, DOCX, and CSV export formatters."""

import io
import re
from datetime import datetime
from typing import Optional

import pandas as pd

from core.schema import build_faq_schema, build_itemlist_schema, schema_to_script_tag


def _markdown_to_html(text: str) -> str:
    """Convert markdown links to HTML links."""
    return re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )


def _build_shopify_body_html(content: dict) -> str:
    """Build the full Body HTML for a Shopify collection page.

    Combines description copy, FAQ HTML, and JSON-LD schema blocks.
    Falls back to `description` when top/bottom_of_page_copy are absent
    so the exporter works with both the old single-description format and
    the new split format.
    """
    parts = []

    top = content.get("top_of_page_copy", "")
    if top:
        parts.append("<!-- TOP OF PAGE -->\n" + _markdown_to_html(top))

    bottom = content.get("bottom_of_page_copy", "") or content.get("description", "")
    if bottom:
        parts.append("<!-- BOTTOM OF PAGE -->\n" + _markdown_to_html(bottom))

    faqs = content.get("faqs", [])
    if faqs:
        faq_html = '<div class="collection-faqs">'
        for faq in faqs:
            faq_html += '<div class="faq-item">'
            faq_html += f'<h3>{faq.get("question", "")}</h3>'
            faq_html += f'<p>{faq.get("answer", "")}</p>'
            faq_html += "</div>"
        faq_html += "</div>"
        parts.append(faq_html)

    faq_schema_tag = schema_to_script_tag(build_faq_schema(faqs))
    if faq_schema_tag:
        parts.append("<!-- FAQ Schema -->\n" + faq_schema_tag)

    products = content.get("products", []) or content.get("products_to_link", [])
    collection_url = content.get("collection_url", "")
    collection_name = content.get("collection_name", "")
    item_schema_tag = schema_to_script_tag(
        build_itemlist_schema(products, collection_url, collection_name)
    )
    if item_schema_tag:
        parts.append("<!-- ItemList Schema -->\n" + item_schema_tag)

    return "\n\n".join(parts)


def export_keyword_map(
    collections: list[dict],
    client_name: str = "",
) -> io.BytesIO:
    """Export the completed keyword map as XLSX matching toolkit schema."""
    rows = []
    for col in collections:
        content = col.get("content", {})
        row = {
            "Collection URL": col.get("collection_url", ""),
            "Collection Name": col.get("collection_name", ""),
            "Primary Keyword": col.get("primary_keyword", ""),
            "Secondary Keywords": ", ".join(col.get("secondary_keywords", [])),
            "Search Volume": col.get("search_volume", ""),
            "Current Rank": col.get("current_rank", ""),
            "Keyword Difficulty": col.get("keyword_difficulty", ""),
            "Optimized SEO Title": content.get("seo_title", ""),
            "Optimized H1": content.get("collection_title", ""),
            "Optimized Description": content.get("description", ""),
            "Optimized Meta Description": content.get("meta_description", ""),
            "FAQ Count": len(content.get("faqs", [])),
            "Status": "Done" if content.get("approved") else "In Review",
            "Last Optimized": datetime.now().strftime("%Y-%m-%d") if content.get("approved") else "",
            "Priority Score": col.get("priority_score", ""),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Keyword Map", index=False)

        worksheet = writer.sheets["Keyword Map"]
        for column in worksheet.columns:
            max_length = max(
                (len(str(cell.value or "")) for cell in column),
                default=10,
            )
            worksheet.column_dimensions[column[0].column_letter].width = min(
                max_length + 2, 50
            )

    buffer.seek(0)
    return buffer


def export_content_delivery(
    collections: list[dict],
    client_name: str = "",
) -> io.BytesIO:
    """Export content delivery document as XLSX with per-collection sheets."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        # Summary sheet
        summary_rows = []
        for col in collections:
            content = col.get("content", {})
            summary_rows.append({
                "Collection": col.get("collection_name", ""),
                "URL": col.get("collection_url", ""),
                "Status": "Approved" if content.get("approved") else "In Review",
                "SEO Title": content.get("seo_title", ""),
                "H1": content.get("collection_title", ""),
                "Description Words": len(content.get("description", "").split()),
                "FAQs": len(content.get("faqs", [])),
            })
        pd.DataFrame(summary_rows).to_excel(
            writer, sheet_name="Summary", index=False
        )

        # Per-collection sheets
        for i, col in enumerate(collections):
            content = col.get("content", {})
            name = col.get("collection_name", f"Collection {i+1}")
            sheet_name = name[:31]  # Excel 31-char limit

            elements = [
                {"Element": "Collection URL", "Content": col.get("collection_url", "")},
                {"Element": "Primary Keyword", "Content": col.get("primary_keyword", "")},
                {"Element": "Secondary Keywords", "Content": ", ".join(col.get("secondary_keywords", []))},
                {"Element": "", "Content": ""},
                {"Element": "SEO Title", "Content": content.get("seo_title", "")},
                {"Element": "Collection Title (H1)", "Content": content.get("collection_title", "")},
                {"Element": "Meta Description", "Content": content.get("meta_description", "")},
                {"Element": "", "Content": ""},
                {"Element": "Collection Description", "Content": content.get("description", "")},
                {"Element": "", "Content": ""},
            ]

            for j, faq in enumerate(content.get("faqs", []), 1):
                elements.append({"Element": f"FAQ {j} - Question", "Content": faq.get("question", "")})
                elements.append({"Element": f"FAQ {j} - Answer", "Content": faq.get("answer", "")})

            pd.DataFrame(elements).to_excel(writer, sheet_name=sheet_name, index=False)

    buffer.seek(0)
    return buffer


def export_shopify_csv(
    collections: list[dict],
) -> io.BytesIO:
    """Export Shopify bulk import CSV (Matrixify-compatible)."""
    rows = []
    for col in collections:
        content = col.get("content", {})

        content_with_meta = {
            **content,
            "collection_url": col.get("collection_url", ""),
            "collection_name": col.get("collection_name", ""),
            "products": col.get("products_to_link", []),
        }
        body_html = _build_shopify_body_html(content_with_meta)

        url = col.get("collection_url", "")
        handle = url.rstrip("/").split("/")[-1] if "/collections/" in url else ""

        rows.append({
            "Handle": handle,
            "Title": content.get("collection_title", col.get("collection_name", "")),
            "Body HTML": body_html,
            "Meta Title": content.get("seo_title", ""),
            "Meta Description": content.get("meta_description", ""),
        })

    df = pd.DataFrame(rows)
    buffer = io.BytesIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)
    return buffer


def export_keyword_map_roundtrip(
    collections: list[dict],
    client_name: str = "",
) -> io.BytesIO:
    """Export in the same wide format as the keyword mapping document input.

    Columns: URL | Target Keyword 1 | Search Volume | Target Keyword 2 |
    Search Volume.1 | ... plus optimized content columns appended on the right.
    """
    rows = []
    for col in collections:
        content = col.get("content", {})
        # Use raw dicts when available (preserves volumes); fall back to string list
        sec_kws = col.get("secondary_keywords_raw") or col.get("secondary_keywords", [])
        sec_kw_list = [
            kw if isinstance(kw, str) else kw.get("keyword", "") for kw in sec_kws
        ]
        sec_vol_list = [
            kw.get("search_volume", "") if isinstance(kw, dict) else "" for kw in sec_kws
        ]
        row = {
            "URL": col.get("collection_url", ""),
            "Target Keyword 1": col.get("primary_keyword", ""),
            "Search Volume": col.get("primary_keyword_volume") or col.get("search_volume", ""),
        }
        for idx in range(3):  # Keywords 2, 3, 4
            kw_num = idx + 2
            row[f"Target Keyword {kw_num}"] = sec_kw_list[idx] if idx < len(sec_kw_list) else ""
            row[f"Search Volume.{idx + 1}"] = sec_vol_list[idx] if idx < len(sec_vol_list) else ""
        row["Optimized SEO Title"] = content.get("seo_title", "")
        row["Optimized H1"] = content.get("collection_title", "")
        row["Optimized Description"] = content.get("description", "")
        row["Optimized Meta Description"] = content.get("meta_description", "")
        row["Status"] = "Done" if content.get("approved") else "In Review"
        rows.append(row)

    df = pd.DataFrame(rows)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Keyword Map", index=False)
        ws = writer.sheets["Keyword Map"]
        for column in ws.columns:
            ws.column_dimensions[column[0].column_letter].width = min(
                max(len(str(c.value or "")) for c in column) + 2, 60
            )
    buffer.seek(0)
    return buffer


def generate_copy_paste_cards(collections: list[dict]) -> list[dict]:
    """Generate copy-paste card data for each collection."""
    cards = []
    for col in collections:
        content = col.get("content", {})
        collection_url = col.get("collection_url", "")
        collection_name = col.get("collection_name", "")

        faq_schema_html = schema_to_script_tag(build_faq_schema(content.get("faqs", [])))
        item_schema_html = schema_to_script_tag(
            build_itemlist_schema(
                col.get("products_to_link", []),
                collection_url,
                collection_name,
            )
        )

        description = content.get("description", "")
        cards.append({
            "collection_name": collection_name,
            "collection_url": collection_url,
            "seo_title": content.get("seo_title", ""),
            "collection_title": content.get("collection_title", ""),
            "meta_description": content.get("meta_description", ""),
            "description": description,
            "description_html": _markdown_to_html(description),
            "faqs": content.get("faqs", []),
            "faq_schema_html": faq_schema_html,
            "item_schema_html": item_schema_html,
        })
    return cards


def export_alt_text(alt_text_results: list[dict]) -> io.BytesIO:
    """Export alt-text suggestions as XLSX for Shopify bulk update.

    Columns match Matrixify Products format so the user can paste the
    Suggested Alt column directly into a Shopify bulk image update.
    """
    rows = []
    for r in alt_text_results:
        rows.append({
            "Handle": r.get("handle", ""),
            "Product Name": r.get("name", ""),
            "Image Src": r.get("image", ""),
            "Original Alt": r.get("original_alt", ""),
            "Suggested Alt": r.get("suggested_alt", ""),
            "Model Used": r.get("model_used", ""),
        })
    df = pd.DataFrame(rows)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Alt Text Suggestions", index=False)
        ws = writer.sheets["Alt Text Suggestions"]
        for column in ws.columns:
            ws.column_dimensions[column[0].column_letter].width = min(
                max(len(str(c.value or "")) for c in column) + 2, 60
            )
    buffer.seek(0)
    return buffer
