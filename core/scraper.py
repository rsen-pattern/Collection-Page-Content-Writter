"""Page scraper for collection audit data and Shopify product data.

Two separate scraping concerns live in this module:

1. Audit scraper (ScrapedPageData / scrape_with_fallback) — fetches existing
   SEO metadata from a collection page for the audit flow.  Always existed.

2. Shopify product scraper (CollectionPageData / fetch_collection_data) — uses
   Shopify's JSON endpoints first, HTML selectors as fallback.  Feeds real
   product names + URLs into content briefs so generated copy references real
   items rather than placeholders.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field as PydanticField


USER_AGENT = "Mozilla/5.0 (compatible; CollectionSEOEngine/1.0)"

# Ordered selector list for collection description.
# Tries each in order and uses the first that returns >20 chars of text.
# Verified against Shopify themes including New Era Cap Australia.
DESCRIPTION_SELECTORS = [
    ".rte",
    ".collection-footer__description",
    ".collection-description",
    ".collection__description",
    "[data-collection-description]",
    ".collection-footer .rte",
    "#CollectionDescription",
    ".collection-hero__description",
]


@dataclass
class ScrapedPageData:
    """Result of scraping a single collection page."""

    url: str
    seo_title: str = ""
    h1: str = ""
    meta_description: str = ""
    description: str = ""
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None

    @property
    def fields_found(self) -> int:
        """Count how many of the four key fields were extracted."""
        return sum([
            bool(self.seo_title),
            bool(self.h1),
            bool(self.meta_description),
            bool(self.description),
        ])


@dataclass
class FallbackScrapeResult:
    """Result of scrape_with_fallback() — includes which tier succeeded."""

    data: ScrapedPageData
    tier_used: str          # 'direct' | 'webscraping_ai' | 'scraperapi' | 'failed'
    tiers_attempted: list = field(default_factory=list)


def _parse_html_to_scraped_data(url: str, html: str) -> ScrapedPageData:
    """Parse raw HTML into ScrapedPageData. Shared by all three scraping tiers."""
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    seo_title = title_tag.text.strip() if title_tag else ""

    h1_tag = soup.find("h1")
    h1 = " ".join(h1_tag.get_text(separator=" ", strip=True).split()) if h1_tag else ""

    meta_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = meta_tag.get("content", "").strip() if meta_tag else ""

    description = ""
    for selector in DESCRIPTION_SELECTORS:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 20:
                description = text
                break

    return ScrapedPageData(
        url=url,
        seo_title=seo_title,
        h1=h1,
        meta_description=meta_description,
        description=description,
    )


def scrape_collection_page(
    url: str,
    timeout: int = 10,
) -> ScrapedPageData:
    """Fetch a collection page and extract SEO audit fields.

    Extracts:
      - seo_title:        <title> tag text
      - h1:               First <h1> inner text (stripped)
      - meta_description: <meta name="description"> content attribute
      - description:      Collection description div text (multiple selectors tried)

    Returns ScrapedPageData with error set if the request fails,
    returns a non-200 status, or if the page appears to require auth.
    """
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
    except requests.exceptions.Timeout:
        return ScrapedPageData(url=url, error=f"Timeout after {timeout}s")
    except requests.exceptions.ConnectionError:
        return ScrapedPageData(
            url=url, error="Connection failed — check the store URL is correct"
        )
    except Exception as e:
        return ScrapedPageData(url=url, error=f"Request error: {e}")

    if response.status_code == 404:
        return ScrapedPageData(url=url, error="Page not found (404)")
    if response.status_code in (401, 403):
        return ScrapedPageData(
            url=url, error="Page requires authentication — use manual entry"
        )
    if response.status_code != 200:
        return ScrapedPageData(url=url, error=f"HTTP {response.status_code}")

    return _parse_html_to_scraped_data(url, response.text)


def scrape_via_webscraping_ai(
    url: str,
    api_key: str,
    timeout: int = 15,
) -> ScrapedPageData:
    """Scrape via WebScraping.AI (Tier 2).

    Endpoint: GET https://api.webscraping.ai/html
    Parameters: api_key, url, js=true
    Returns raw HTML parsed with _parse_html_to_scraped_data().
    """
    try:
        response = requests.get(
            "https://api.webscraping.ai/html",
            params={"api_key": api_key, "url": url, "js": "true"},
            timeout=timeout,
        )
    except requests.exceptions.Timeout:
        return ScrapedPageData(url=url, error="WebScraping.AI: timeout")
    except requests.exceptions.ConnectionError:
        return ScrapedPageData(url=url, error="WebScraping.AI: connection failed")
    except Exception as e:
        return ScrapedPageData(url=url, error=f"WebScraping.AI: {e}")

    if response.status_code == 401:
        return ScrapedPageData(url=url, error="WebScraping.AI: invalid API key")
    if response.status_code == 402:
        return ScrapedPageData(url=url, error="WebScraping.AI: credits exhausted")
    if response.status_code != 200:
        return ScrapedPageData(url=url, error=f"WebScraping.AI: HTTP {response.status_code}")

    return _parse_html_to_scraped_data(url, response.text)


def scrape_via_scraperapi(
    url: str,
    api_key: str,
    timeout: int = 15,
) -> ScrapedPageData:
    """Scrape via ScraperAPI (Tier 3).

    Endpoint: GET https://api.scraperapi.com/
    Parameters: api_key, url
    Returns raw HTML parsed with _parse_html_to_scraped_data().
    """
    try:
        response = requests.get(
            "https://api.scraperapi.com/",
            params={"api_key": api_key, "url": url},
            timeout=timeout,
        )
    except requests.exceptions.Timeout:
        return ScrapedPageData(url=url, error="ScraperAPI: timeout")
    except requests.exceptions.ConnectionError:
        return ScrapedPageData(url=url, error="ScraperAPI: connection failed")
    except Exception as e:
        return ScrapedPageData(url=url, error=f"ScraperAPI: {e}")

    if response.status_code == 401:
        return ScrapedPageData(url=url, error="ScraperAPI: invalid API key")
    if response.status_code == 403:
        return ScrapedPageData(url=url, error="ScraperAPI: credits exhausted or plan limit")
    if response.status_code != 200:
        return ScrapedPageData(url=url, error=f"ScraperAPI: HTTP {response.status_code}")

    return _parse_html_to_scraped_data(url, response.text)


def scrape_with_fallback(
    url: str,
    webscraping_ai_key: str = "",
    scraperapi_key: str = "",
    timeout: int = 10,
) -> FallbackScrapeResult:
    """Try each scraping tier in order, return first result with >= 2 fields.

    Tier 1: Direct requests — always tried, no API key needed.
    Tier 2: WebScraping.AI — tried if Tier 1 fails and key is set.
    Tier 3: ScraperAPI — tried if Tier 2 fails and key is set.

    Escalation triggers when Tier 1 causes fallback:
    - HTTP 403, 401, or 429 / connection error (blocked)
    - fields_found < 2 (JS rendering needed or selectors missed)

    A tier with an empty key is skipped silently.
    """
    attempted: list[str] = []

    # ── Tier 1: Direct requests ──────────────────────────────────────────
    attempted.append("direct")
    t1 = scrape_collection_page(url, timeout=timeout)

    if t1.success and t1.fields_found >= 2:
        return FallbackScrapeResult(data=t1, tier_used="direct", tiers_attempted=attempted)

    blocked = not t1.success and t1.error and any(
        x in str(t1.error) for x in ["403", "401", "429", "blocked", "Connection"]
    )
    low_fields = t1.fields_found < 2

    if not (blocked or low_fields):
        return FallbackScrapeResult(data=t1, tier_used="direct", tiers_attempted=attempted)

    t2 = t3 = None

    # ── Tier 2: WebScraping.AI ───────────────────────────────────────────
    if webscraping_ai_key:
        attempted.append("webscraping_ai")
        t2 = scrape_via_webscraping_ai(url, webscraping_ai_key, timeout=timeout + 5)
        if t2.success and t2.fields_found >= 2:
            return FallbackScrapeResult(data=t2, tier_used="webscraping_ai", tiers_attempted=attempted)

    # ── Tier 3: ScraperAPI ────────────────────────────────────────────────
    if scraperapi_key:
        attempted.append("scraperapi")
        t3 = scrape_via_scraperapi(url, scraperapi_key, timeout=timeout + 5)
        if t3.success and t3.fields_found >= 2:
            return FallbackScrapeResult(data=t3, tier_used="scraperapi", tiers_attempted=attempted)

    # ── All tiers failed — return best partial result ─────────────────────
    candidates = [r for r in [t1, t2, t3] if r is not None]
    best = max(candidates, key=lambda r: r.fields_found)
    return FallbackScrapeResult(data=best, tier_used="failed", tiers_attempted=attempted)


# ═══════════════════════════════════════════════════════════════════════════
# Shopify product scraper (JSON-first, HTML fallback)
# ═══════════════════════════════════════════════════════════════════════════

_SHOPIFY_USER_AGENT = (
    "Mozilla/5.0 (compatible; CollectionSEOEngine/1.0; "
    "+https://github.com/pattern-agency/seo-engine)"
)
_SHOPIFY_TIMEOUT = 8


class ScrapedProduct(BaseModel):
    name: str
    url: str
    image: str = ""
    image_alt: str = ""
    price: str = ""
    currency: str = ""
    handle: str = ""
    product_type: str = ""
    vendor: str = ""


class CollectionPageData(BaseModel):
    url: str
    handle: str = ""
    h1: str = ""
    meta_title: str = ""
    meta_description: str = ""
    existing_top_copy: str = ""
    existing_bottom_copy: str = ""
    products: list[ScrapedProduct] = PydanticField(default_factory=list)
    source: Literal["json", "html", "mixed", "failed"] = "failed"
    error: str = ""


def _shopify_get(url: str, *, accept_json: bool = False) -> Optional[requests.Response]:
    headers = {
        "User-Agent": _SHOPIFY_USER_AGENT,
        "Accept": "application/json" if accept_json else "text/html,application/xhtml+xml",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=_SHOPIFY_TIMEOUT, allow_redirects=True)
        return resp if resp.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None


def _shopify_extract_handle(url: str) -> str:
    m = re.search(r"/collections/([^/?#]+)", url)
    return m.group(1) if m else ""


def _shopify_origin(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _fetch_products_json(url: str, limit: int = 50) -> Optional[list[dict]]:
    products_url = url.split("?")[0].rstrip("/") + f"/products.json?limit={limit}"
    resp = _shopify_get(products_url, accept_json=True)
    if resp is None:
        return None
    try:
        return resp.json().get("products", [])
    except (ValueError, AttributeError):
        return None


def _products_from_json(raw_products: list[dict], origin: str) -> list[ScrapedProduct]:
    products: list[ScrapedProduct] = []
    for p in raw_products:
        handle = p.get("handle", "")
        relative_url = f"/products/{handle}" if handle else ""
        absolute_url = urljoin(origin, relative_url) if origin else relative_url
        variants = p.get("variants") or []
        first_variant = variants[0] if variants else {}
        images = p.get("images") or []
        first_image = images[0] if images else {}
        products.append(ScrapedProduct(
            name=p.get("title", ""),
            url=absolute_url,
            handle=handle,
            image=first_image.get("src", "") if isinstance(first_image, dict) else "",
            image_alt=first_image.get("alt", "") if isinstance(first_image, dict) else "",
            price=str(first_variant.get("price", "")),
            currency="",
            product_type=p.get("product_type", ""),
            vendor=p.get("vendor", ""),
        ))
    return products


_EXISTING_TOP_SELECTORS = [
    ".collection-description",
    ".collection__description",
    ".collection-hero__description",
    ".collection-banner__description",
]
_EXISTING_BOTTOM_SELECTORS = [
    ".collection-footer__content",
    ".collection__footer-content",
    ".collection-footer .rte",
    ".rte",
]
_PRODUCT_CARD_SELECTORS = [
    ".product-card",
    ".grid-product",
    ".product-item",
    ".grid__item .product",
    "[class*='product-card']",
]


def _extract_existing_copy(soup: BeautifulSoup) -> tuple[str, str]:
    def first_text(selectors: list) -> str:
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                text = el.get_text("\n", strip=True)
                if len(text) > 20:
                    return text
        return ""

    return first_text(_EXISTING_TOP_SELECTORS), first_text(_EXISTING_BOTTOM_SELECTORS)


def _products_from_html(soup: BeautifulSoup, origin: str) -> list[ScrapedProduct]:
    products: list[ScrapedProduct] = []
    seen_urls: set[str] = set()

    for selector in _PRODUCT_CARD_SELECTORS:
        cards = soup.select(selector)
        if not cards:
            continue
        for card in cards:
            link = card.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            if "/products/" not in href:
                continue
            absolute_url = urljoin(origin, href) if origin else href
            if absolute_url in seen_urls:
                continue
            seen_urls.add(absolute_url)

            name = ""
            for name_sel in (".product-card__title", ".product-title", ".product__title", "h2", "h3"):
                el = card.select_one(name_sel)
                if el and el.get_text(strip=True):
                    name = el.get_text(strip=True)
                    break
            if not name:
                name = link.get_text(strip=True) or link.get("title", "")
            if not name:
                continue

            img = card.find("img")
            image = image_alt = ""
            if img:
                image = img.get("src") or img.get("data-src") or ""
                image_alt = img.get("alt", "")

            handle = href.rstrip("/").split("/")[-1].split("?")[0]
            products.append(ScrapedProduct(
                name=name,
                url=absolute_url,
                image=image,
                image_alt=image_alt,
                handle=handle,
            ))
        if products:
            break
    return products


def fetch_collection_data(url: str) -> CollectionPageData:
    """Fetch real product data + existing copy from a Shopify collection URL.

    Returns a CollectionPageData with `source` set to:
      - "json"   when products came from products.json (best case)
      - "html"   when products came from HTML scraping
      - "mixed"  when JSON gave products and HTML gave existing copy
      - "failed" when neither path produced anything usable
    """
    if not url or "/collections/" not in url:
        return CollectionPageData(url=url, source="failed", error="Not a Shopify collection URL")

    origin = _shopify_origin(url)
    handle = _shopify_extract_handle(url)
    data = CollectionPageData(url=url, handle=handle)

    page_resp = _shopify_get(url, accept_json=False)
    soup: Optional[BeautifulSoup] = None
    if page_resp is not None:
        soup = BeautifulSoup(page_resp.text, "lxml")
        title_tag = soup.find("title")
        meta_tag = soup.find("meta", attrs={"name": "description"})
        h1_tag = soup.find("h1")
        data.h1 = h1_tag.get_text(strip=True) if h1_tag else ""
        data.meta_title = title_tag.get_text(strip=True) if title_tag else ""
        data.meta_description = meta_tag.get("content", "").strip() if meta_tag else ""
        top, bottom = _extract_existing_copy(soup)
        data.existing_top_copy = top
        data.existing_bottom_copy = bottom

    raw_products = _fetch_products_json(url)
    if raw_products is not None and raw_products:
        data.products = _products_from_json(raw_products, origin)
        data.source = "mixed" if soup is not None else "json"
        return data

    if soup is not None:
        data.products = _products_from_html(soup, origin)
        if data.products:
            data.source = "html"
            return data

    if soup is not None:
        data.source = "html"
        data.error = "Page fetched but no products extracted (theme may use JS rendering)"
        return data

    data.source = "failed"
    data.error = "Could not fetch collection page"
    return data
