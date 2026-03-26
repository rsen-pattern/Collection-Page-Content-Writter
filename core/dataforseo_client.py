"""DataForSEO API wrapper for keyword data and on-page audit.

Phase 2 implementation — provides the client interface with
placeholder methods that will be fully implemented when
DataForSEO integration is prioritized.
"""

import base64
from typing import Optional

import httpx
from pydantic import BaseModel, Field


class DataForSEOCredentials(BaseModel):
    """DataForSEO API credentials."""

    login: str
    password: str

    @property
    def auth_header(self) -> str:
        encoded = base64.b64encode(f"{self.login}:{self.password}".encode()).decode()
        return f"Basic {encoded}"


class DataForSEOClient:
    """Client for DataForSEO REST API."""

    BASE_URL = "https://api.dataforseo.com"

    def __init__(self, login: str, password: str):
        self.credentials = DataForSEOCredentials(login=login, password=password)
        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={
                "Authorization": self.credentials.auth_header,
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
        self._cached_results: dict = {}

    def _post(self, endpoint: str, data: list[dict]) -> dict:
        """Make a POST request to DataForSEO API."""
        response = self._client.post(endpoint, json=data)

        if response.status_code == 401:
            raise PermissionError("Invalid DataForSEO credentials")
        if response.status_code == 429:
            raise RuntimeError("DataForSEO rate limit exceeded. Please wait and retry.")
        response.raise_for_status()

        result = response.json()
        if result.get("status_code") != 20000:
            msg = result.get("status_message", "Unknown error")
            raise RuntimeError(f"DataForSEO API error: {msg}")

        return result

    def credits_remaining(self) -> Optional[float]:
        """Check remaining API credits."""
        try:
            response = self._client.get("/v3/appendix/user_data")
            if response.status_code == 200:
                data = response.json()
                money = data.get("tasks", [{}])[0].get("result", [{}])[0]
                return money.get("money", {}).get("balance")
        except Exception:
            return None

    def get_ranked_keywords(
        self,
        domain: str,
        location_code: int = 2826,  # UK
        language_code: str = "en",
        url_filter: str = "/collections/",
        limit: int = 1000,
    ) -> list[dict]:
        """Pull all keywords a domain ranks for, filtered to collection URLs.

        Uses: /v3/dataforseo_labs/google/ranked_keywords/live
        """
        cache_key = f"ranked_{domain}_{url_filter}"
        if cache_key in self._cached_results:
            return self._cached_results[cache_key]

        data = [
            {
                "target": domain,
                "location_code": location_code,
                "language_code": language_code,
                "filters": [
                    ["ranked_serp_element.serp_item.relative_url", "contains", url_filter]
                ],
                "limit": limit,
                "order_by": ["keyword_data.keyword_info.search_volume,desc"],
            }
        ]

        result = self._post("/v3/dataforseo_labs/google/ranked_keywords/live", data)
        items = result.get("tasks", [{}])[0].get("result", [{}])[0].get("items", [])

        self._cached_results[cache_key] = items
        return items

    def get_keyword_suggestions(
        self,
        keyword: str,
        location_code: int = 2826,
        language_code: str = "en",
        limit: int = 50,
    ) -> list[dict]:
        """Get related keyword suggestions.

        Uses: /v3/dataforseo_labs/google/keyword_suggestions/live
        """
        cache_key = f"suggestions_{keyword}"
        if cache_key in self._cached_results:
            return self._cached_results[cache_key]

        data = [
            {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
                "limit": limit,
            }
        ]

        result = self._post(
            "/v3/dataforseo_labs/google/keyword_suggestions/live", data
        )
        items = result.get("tasks", [{}])[0].get("result", [{}])[0].get("items", [])

        self._cached_results[cache_key] = items
        return items

    def get_people_also_ask(
        self,
        keyword: str,
        location_code: int = 2826,
        language_code: str = "en",
    ) -> list[str]:
        """Extract People Also Ask questions for a keyword.

        Uses: /v3/serp/google/organic/live/regular
        """
        cache_key = f"paa_{keyword}"
        if cache_key in self._cached_results:
            return self._cached_results[cache_key]

        data = [
            {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
                "device": "desktop",
                "os": "windows",
            }
        ]

        result = self._post("/v3/serp/google/organic/live/regular", data)
        items = result.get("tasks", [{}])[0].get("result", [{}])[0].get("items", [])

        paa = [
            item["title"]
            for item in items
            if item.get("type") == "people_also_ask" and "title" in item
        ]

        self._cached_results[cache_key] = paa
        return paa

    def crawl_page(
        self,
        url: str,
    ) -> dict:
        """Crawl a page and extract SEO elements.

        Uses: /v3/on_page/ endpoints

        Returns dict with: title, h1, meta_description, word_count,
        internal_links_count, structured_data
        """
        cache_key = f"crawl_{url}"
        if cache_key in self._cached_results:
            return self._cached_results[cache_key]

        # Start crawl task
        task_data = [
            {
                "target": url,
                "max_crawl_pages": 1,
            }
        ]

        task_result = self._post("/v3/on_page/task_post", task_data)
        task_id = task_result.get("tasks", [{}])[0].get("id")

        if not task_id:
            return {}

        # Get pages data
        pages_data = [{"id": task_id, "limit": 1}]
        pages_result = self._post("/v3/on_page/pages", pages_data)
        pages = (
            pages_result.get("tasks", [{}])[0].get("result", [{}])[0].get("items", [])
        )

        if not pages:
            return {}

        page = pages[0]
        extracted = {
            "title": page.get("meta", {}).get("title", ""),
            "h1": page.get("meta", {}).get("htags", {}).get("h1", [""])[0]
            if page.get("meta", {}).get("htags", {}).get("h1")
            else "",
            "meta_description": page.get("meta", {}).get("description", ""),
            "word_count": page.get("meta", {}).get("content", {}).get("plain_text_word_count", 0),
            "internal_links_count": page.get("meta", {}).get("internal_links_count", 0),
            "structured_data": bool(page.get("meta", {}).get("schemas")),
        }

        self._cached_results[cache_key] = extracted
        return extracted

    def close(self):
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
