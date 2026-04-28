"""Page scraper for collection audit data."""

from dataclasses import dataclass
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

    soup = BeautifulSoup(response.text, "html.parser")

    # SEO Title
    title_tag = soup.find("title")
    seo_title = title_tag.text.strip() if title_tag else ""

    # H1 — get_text() handles nested tags (e.g. <h1><span>text</span></h1>)
    h1_tag = soup.find("h1")
    h1 = h1_tag.get_text(separator=" ", strip=True) if h1_tag else ""
    h1 = " ".join(h1.split())  # collapse internal whitespace

    # Meta description
    meta_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = meta_tag.get("content", "").strip() if meta_tag else ""

    # Collection description — try selectors in priority order
    description = ""
    for selector in DESCRIPTION_SELECTORS:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 20:  # skip nav/breadcrumb noise
                description = text
                break

    return ScrapedPageData(
        url=url,
        seo_title=seo_title,
        h1=h1,
        meta_description=meta_description,
        description=description,
    )
