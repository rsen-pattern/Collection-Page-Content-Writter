"""Pan-app text helpers — keyword cleaning, URL handle extraction, Bifrost URL parsing.

These were previously duplicated across data_ingestion, scraper, auditor,
content_generator, feedback_extractor, exporter, and several pages. The
canonical implementations now live here; old call sites re-export or import.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse, urlunparse


def clean_keyword(text: str) -> str:
    """Strip unicode format characters and normalise whitespace.

    Removes zero-width spaces (U+200B), BOM (U+FEFF), soft hyphens, and all
    other characters in unicode category 'Cf'. Collapses runs of whitespace
    into a single space. Returns "" for falsy inputs.
    """
    if not text:
        return text if text == "" else ""
    cleaned = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return " ".join(cleaned.split())


_COLLECTION_HANDLE_RE = re.compile(r"/collections/([^/?#]+)")


def extract_collection_handle(url: str) -> str:
    """Extract the collection handle from a Shopify-style URL.

    Returns "" when the URL has no /collections/ segment. Handles query
    strings, fragments, trailing slashes, and unicode characters in handles.
    """
    if not url:
        return ""
    match = _COLLECTION_HANDLE_RE.search(url)
    return match.group(1) if match else ""


def extract_collection_name(url: str) -> str:
    """Extract a human-readable name from a collection URL.

    Returns Title Case of the handle, e.g. ``/collections/gold-earrings`` →
    "Gold Earrings". Falls back to the last path segment when no
    ``/collections/`` segment exists. Returns the input unchanged when it has
    no recognisable path structure.
    """
    if not url:
        return ""
    handle = extract_collection_handle(url)
    if handle:
        return handle.replace("-", " ").replace("_", " ").title()
    # Fallback to last path segment
    parsed_path = urlparse(url).path or url
    parts = [p for p in parsed_path.rstrip("/").split("/") if p]
    if not parts:
        return url
    return parts[-1].replace("-", " ").replace("_", " ").title()


def ensure_v1_path(base_url: str) -> str:
    """Append ``/v1`` to a Bifrost base URL when not already present.

    Uses proper URL parsing so we don't append to URLs whose path already
    contains ``/v1`` further up the tree (e.g. ``/v1/foo``).
    """
    if not base_url:
        return base_url
    parsed = urlparse(base_url.rstrip("/"))
    path = parsed.path
    # Avoid double-appending when /v1 is already the last segment.
    if path.endswith("/v1") or path == "/v1":
        return urlunparse(parsed)
    # Avoid appending when /v1 appears anywhere as a segment (e.g. /v1/foo).
    segments = [s for s in path.split("/") if s]
    if "v1" in segments:
        return urlunparse(parsed)
    path = path + "/v1"
    return urlunparse(parsed._replace(path=path))


__all__ = [
    "clean_keyword",
    "extract_collection_handle",
    "extract_collection_name",
    "ensure_v1_path",
]
