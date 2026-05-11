"""Sitemap ingestion, parsing, and related-URL matching.

Fetches and parses a store's sitemap.xml (or sitemap index) so generated copy
can pick real, indexable URLs for internal links — products, collections, and
blog posts — instead of inventing paths.

Pure stdlib parsing (``xml.etree``, ``gzip``, ``urllib.parse``, ``difflib``)
plus the already-vendored ``requests`` for fetches. No new dependencies.
"""

from __future__ import annotations

import datetime as _dt
import gzip
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Literal, Optional
from urllib.parse import urlparse

import requests


SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
DEFAULT_MAX_URLS = 5000
DEFAULT_TIMEOUT = 15

UrlType = Literal["product", "collection", "blog", "page", "other"]


@dataclass
class SitemapUrl:
    """A single URL pulled from a sitemap, classified by Shopify path shape."""

    url: str
    url_type: UrlType
    handle: str = ""
    last_modified: str = ""
    title_guess: str = ""

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "url_type": self.url_type,
            "handle": self.handle,
            "last_modified": self.last_modified,
            "title_guess": self.title_guess,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SitemapUrl":
        return cls(
            url=data.get("url", ""),
            url_type=data.get("url_type", "other"),
            handle=data.get("handle", ""),
            last_modified=data.get("last_modified", ""),
            title_guess=data.get("title_guess", ""),
        )


@dataclass
class ParsedSitemap:
    """All URLs extracted from a sitemap, bucketed by type."""

    source_url: str = ""
    fetched_at: str = ""
    products: list[SitemapUrl] = field(default_factory=list)
    collections: list[SitemapUrl] = field(default_factory=list)
    blog_posts: list[SitemapUrl] = field(default_factory=list)
    pages: list[SitemapUrl] = field(default_factory=list)
    other: list[SitemapUrl] = field(default_factory=list)
    error: str = ""

    @property
    def total_urls(self) -> int:
        return (
            len(self.products)
            + len(self.collections)
            + len(self.blog_posts)
            + len(self.pages)
            + len(self.other)
        )

    def to_dict(self) -> dict:
        return {
            "source_url": self.source_url,
            "fetched_at": self.fetched_at,
            "products": [u.to_dict() for u in self.products],
            "collections": [u.to_dict() for u in self.collections],
            "blog_posts": [u.to_dict() for u in self.blog_posts],
            "pages": [u.to_dict() for u in self.pages],
            "other": [u.to_dict() for u in self.other],
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ParsedSitemap":
        return cls(
            source_url=data.get("source_url", ""),
            fetched_at=data.get("fetched_at", ""),
            products=[SitemapUrl.from_dict(u) for u in data.get("products", [])],
            collections=[SitemapUrl.from_dict(u) for u in data.get("collections", [])],
            blog_posts=[SitemapUrl.from_dict(u) for u in data.get("blog_posts", [])],
            pages=[SitemapUrl.from_dict(u) for u in data.get("pages", [])],
            other=[SitemapUrl.from_dict(u) for u in data.get("other", [])],
            error=data.get("error", ""),
        )


def _classify_url(url: str) -> tuple[UrlType, str]:
    """Return (url_type, handle) for a Shopify-style URL."""
    path = urlparse(url).path or ""
    if "/products/" in path:
        handle = path.split("/products/", 1)[1].split("/", 1)[0].split("?", 1)[0]
        return "product", handle
    if "/collections/" in path:
        # Strip product suffix if present: /collections/x/products/y -> handle "x"
        remainder = path.split("/collections/", 1)[1]
        handle = remainder.split("/", 1)[0].split("?", 1)[0]
        if "/products/" in remainder:
            # collection-scoped product URL; classify as product, not collection
            product_handle = remainder.split("/products/", 1)[1].split("/", 1)[0]
            return "product", product_handle
        return "collection", handle
    if "/blogs/" in path:
        remainder = path.split("/blogs/", 1)[1]
        parts = [p for p in remainder.split("/") if p]
        # /blogs/<blog>          -> blog index, treat as "blog"
        # /blogs/<blog>/<post>   -> blog post, handle is post
        if len(parts) >= 2:
            return "blog", parts[1]
        if len(parts) == 1:
            return "blog", parts[0]
        return "blog", ""
    if "/pages/" in path:
        handle = path.split("/pages/", 1)[1].split("/", 1)[0].split("?", 1)[0]
        return "page", handle
    # Last path segment as a best-effort handle
    handle = path.rstrip("/").rsplit("/", 1)[-1] if path else ""
    return "other", handle


def _title_from_handle(handle: str) -> str:
    """Turn a URL handle like 'quencher-40oz-charcoal' into 'Quencher 40oz Charcoal'."""
    if not handle:
        return ""
    cleaned = handle.replace("-", " ").replace("_", " ").strip()
    # Title-case but preserve mixed-case tokens with digits like "40oz"
    parts = []
    for tok in cleaned.split():
        if any(ch.isdigit() for ch in tok):
            parts.append(tok)
        else:
            parts.append(tok[:1].upper() + tok[1:].lower())
    return " ".join(parts)


def _iter_url_entries(root: ET.Element):
    """Yield (loc, lastmod) tuples from a urlset root."""
    for url_el in root.findall(f"{SITEMAP_NS}url"):
        loc_el = url_el.find(f"{SITEMAP_NS}loc")
        if loc_el is None or not (loc_el.text or "").strip():
            continue
        lastmod_el = url_el.find(f"{SITEMAP_NS}lastmod")
        lastmod = (lastmod_el.text or "").strip() if lastmod_el is not None else ""
        yield loc_el.text.strip(), lastmod


def _iter_sitemap_refs(root: ET.Element):
    """Yield child sitemap URLs from a sitemapindex root."""
    for sm_el in root.findall(f"{SITEMAP_NS}sitemap"):
        loc_el = sm_el.find(f"{SITEMAP_NS}loc")
        if loc_el is None or not (loc_el.text or "").strip():
            continue
        yield loc_el.text.strip()


def _maybe_decompress(content: bytes, source_hint: str = "") -> bytes:
    """Decompress gzip if the bytes look gzipped or the source ends in .gz."""
    if content[:2] == b"\x1f\x8b" or source_hint.lower().endswith(".gz"):
        try:
            return gzip.decompress(content)
        except OSError:
            return content
    return content


def _build_sitemap_url(loc: str, lastmod: str) -> SitemapUrl:
    url_type, handle = _classify_url(loc)
    return SitemapUrl(
        url=loc,
        url_type=url_type,
        handle=handle,
        last_modified=lastmod,
        title_guess=_title_from_handle(handle),
    )


def _bucket(result: ParsedSitemap, entry: SitemapUrl) -> None:
    if entry.url_type == "product":
        result.products.append(entry)
    elif entry.url_type == "collection":
        result.collections.append(entry)
    elif entry.url_type == "blog":
        result.blog_posts.append(entry)
    elif entry.url_type == "page":
        result.pages.append(entry)
    else:
        result.other.append(entry)


def parse_sitemap_file(
    file_content: bytes,
    source_url: str = "",
    max_urls: int = DEFAULT_MAX_URLS,
) -> ParsedSitemap:
    """Parse already-fetched sitemap bytes. Handles urlset + sitemapindex + gzip.

    For a sitemapindex, child sitemaps are NOT recursively fetched here — that
    requires the network. Use ``fetch_sitemap`` for full traversal. When the
    input is a sitemapindex and no fetcher is wired, the child refs are
    surfaced as ``other`` entries so the user still sees something.
    """
    result = ParsedSitemap(
        source_url=source_url,
        fetched_at=_dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    )
    try:
        decoded = _maybe_decompress(file_content, source_url)
        root = ET.fromstring(decoded)
    except (ET.ParseError, ValueError) as e:
        result.error = f"Malformed XML: {e}"
        return result

    tag = root.tag.replace(SITEMAP_NS, "")
    if tag == "sitemapindex":
        # No fetcher in this path — record children as 'other' for visibility.
        for child in _iter_sitemap_refs(root):
            if result.total_urls >= max_urls:
                result.error = f"Truncated at {max_urls} URLs"
                break
            _bucket(result, _build_sitemap_url(child, ""))
        return result

    if tag != "urlset":
        result.error = f"Unexpected root element: <{tag}>"
        return result

    for loc, lastmod in _iter_url_entries(root):
        if result.total_urls >= max_urls:
            result.error = f"Truncated at {max_urls} URLs"
            break
        _bucket(result, _build_sitemap_url(loc, lastmod))

    return result


def fetch_sitemap(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    max_urls: int = DEFAULT_MAX_URLS,
    _session: Optional[requests.Session] = None,
    _depth: int = 0,
) -> ParsedSitemap:
    """Fetch and parse a sitemap, recursing one level into sitemap indexes.

    Never raises — network, decode, and parse errors are surfaced via the
    ``error`` field on the returned ``ParsedSitemap``.
    """
    result = ParsedSitemap(
        source_url=url,
        fetched_at=_dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    )

    if _depth > 1:
        # Safety: do not recurse beyond one level (Shopify's typical index depth).
        result.error = "Recursion depth exceeded"
        return result

    session = _session or requests
    try:
        resp = session.get(url, timeout=timeout, headers={"User-Agent": "sitemap-ingest/1.0"})
        resp.raise_for_status()
    except requests.RequestException as e:
        result.error = f"Fetch failed: {e}"
        return result

    content = _maybe_decompress(resp.content, url)
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        result.error = f"Malformed XML: {e}"
        return result

    tag = root.tag.replace(SITEMAP_NS, "")

    if tag == "sitemapindex":
        for child_url in _iter_sitemap_refs(root):
            if result.total_urls >= max_urls:
                result.error = f"Truncated at {max_urls} URLs"
                break
            child = fetch_sitemap(
                child_url,
                timeout=timeout,
                max_urls=max_urls - result.total_urls,
                _session=session,
                _depth=_depth + 1,
            )
            if child.error and not result.error:
                # Don't propagate child errors as fatal — store the first.
                result.error = f"Child {child_url}: {child.error}"
            result.products.extend(child.products)
            result.collections.extend(child.collections)
            result.blog_posts.extend(child.blog_posts)
            result.pages.extend(child.pages)
            result.other.extend(child.other)
        return result

    if tag != "urlset":
        result.error = f"Unexpected root element: <{tag}>"
        return result

    for loc, lastmod in _iter_url_entries(root):
        if result.total_urls >= max_urls:
            result.error = f"Truncated at {max_urls} URLs"
            break
        _bucket(result, _build_sitemap_url(loc, lastmod))

    return result


_NON_ALPHANUM = re.compile(r"[^a-z0-9 ]+")


def _normalise(text: str) -> str:
    return _NON_ALPHANUM.sub(" ", text.lower()).strip()


def _score_match(query: str, candidate: SitemapUrl) -> float:
    """Similarity score between a query string and a SitemapUrl."""
    hay = _normalise(candidate.title_guess) or _normalise(candidate.handle)
    if not hay:
        return 0.0
    q = _normalise(query)
    if not q:
        return 0.0
    # Boost when every query word appears in the candidate.
    base = SequenceMatcher(None, q, hay).ratio()
    q_words = [w for w in q.split() if len(w) > 2]
    if q_words and all(w in hay for w in q_words):
        base = max(base, 0.85)
    return base


def find_related_urls(
    primary_keyword: str,
    secondary_keywords: list[str],
    sitemap: ParsedSitemap,
    target_url: str = "",
    max_products: int = 6,
    max_collections: int = 3,
    max_blog_posts: int = 2,
) -> dict:
    """Pick the best-matching sitemap URLs for a collection brief.

    Matches by keyword-to-handle similarity. ``target_url`` is excluded so a
    page never links to itself. Returns ``{"products": [...], "collections":
    [...], "blog_posts": [...]}`` where each item is
    ``{"name", "url", "score"}``.
    """
    queries = [primary_keyword] + [k for k in secondary_keywords if k]
    queries = [q for q in queries if q]

    def _best(candidates: list[SitemapUrl], limit: int) -> list[dict]:
        if limit <= 0 or not candidates or not queries:
            return []
        scored: dict[str, dict] = {}
        for cand in candidates:
            if target_url and cand.url == target_url:
                continue
            best_score = max((_score_match(q, cand) for q in queries), default=0.0)
            if best_score <= 0:
                continue
            existing = scored.get(cand.url)
            if existing is None or existing["score"] < best_score:
                scored[cand.url] = {
                    "name": cand.title_guess or cand.handle or cand.url,
                    "url": cand.url,
                    "score": round(best_score, 4),
                }
        ranked = sorted(scored.values(), key=lambda d: d["score"], reverse=True)
        return ranked[:limit]

    return {
        "products": _best(sitemap.products, max_products),
        "collections": _best(sitemap.collections, max_collections),
        "blog_posts": _best(sitemap.blog_posts, max_blog_posts),
    }


__all__ = [
    "SitemapUrl",
    "ParsedSitemap",
    "fetch_sitemap",
    "parse_sitemap_file",
    "find_related_urls",
]
