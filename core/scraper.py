"""Page scraper for collection audit data."""

from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup


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
