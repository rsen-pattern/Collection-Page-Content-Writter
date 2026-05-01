"""LLM Access Checker — audit logic for all 6 pillars.

Pillar weights in compute_overall: JS=25, Robots=25, Schema=35, LLM=15.
Semantic and Security are full diagnostic pillars displayed in the UI
but do not contribute to compute_overall (display-only diagnostics).

Hard caps enforced:
  robots_missing  -> overall capped at 40
  CF/403 >= 2 pages -> robots score capped at 50 (caller enforces)
  JS gap > 50%    -> JS score capped at 40 (enforced inside check_js_rendering)
  zero schema     -> schema score capped at 20 (enforced inside check_schema_markup)
"""

from __future__ import annotations

import json
import re
import time
import urllib.robotparser
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

AI_BOTS: list[str] = [
    "GPTBot",
    "CCBot",
    "anthropic-ai",
    "ClaudeBot",
    "Google-Extended",
    "PerplexityBot",
    "cohere-ai",
    "Bytespider",
    "Applebot-Extended",
    "Meta-ExternalAgent",
    "YouBot",
    "ia_archiver",
]

WELL_KNOWN_FILES: list[tuple[str, str]] = [
    ("llms.txt", "LLM manifest"),
    ("llms-full.txt", "LLM full manifest"),
    (".well-known/ucp.json", "Universal Crawl Policy"),
    (".well-known/webmcp.json", "WebMCP"),
    (".well-known/tdmrep.json", "TDM Rep"),
    (".well-known/ai-plugin.json", "AI Plugin (deprecated — use WebMCP)"),
]

SCHEMA_REQUIRED_FIELDS: dict[str, list[str]] = {
    "Product": ["name", "description", "offers"],
    "Offer": ["price", "priceCurrency", "availability"],
    "Article": ["headline", "author", "datePublished"],
    "BlogPosting": ["headline", "author", "datePublished"],
    "FAQPage": ["mainEntity"],
    "Organization": ["name", "url"],
    "WebSite": ["name", "url"],
    "LocalBusiness": ["name", "address"],
    "BreadcrumbList": ["itemListElement"],
    "CollectionPage": ["name", "description"],
}

SENSITIVE_PATHS: list[str] = [
    "/admin",
    "/wp-admin",
    "/wp-login.php",
    "/.env",
    "/phpinfo.php",
    "/.git/HEAD",
    "/backup",
    "/dump.sql",
    "/server-status",
    "/api/users",
    "/api/admin",
    "/config.php",
]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def fetch(url: str, timeout: int = 15, verify_ssl: bool = True) -> requests.Response | None:
    """GET with browser UA; returns None on any error."""
    try:
        return requests.get(
            url,
            headers={"User-Agent": BROWSER_UA},
            timeout=timeout,
            allow_redirects=True,
            verify=verify_ssl,
        )
    except requests.exceptions.SSLError:
        try:
            return requests.get(
                url,
                headers={"User-Agent": BROWSER_UA},
                timeout=timeout,
                allow_redirects=True,
                verify=False,  # noqa: S501
            )
        except Exception:
            return None
    except Exception:
        return None


def _extract_visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    return " ".join(soup.get_text().split())


# ---------------------------------------------------------------------------
# Pillar 1 — JS Rendering
# ---------------------------------------------------------------------------

def check_js_rendering(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare HTML vs JS-rendered content per page.

    Each item in *pages* must have:
      label, url, html_content, js_content (str), status_code (int)
    """
    page_results: list[dict] = []
    scores: list[int] = []

    for p in pages:
        html_text = _extract_visible_text(p.get("html_content", ""))
        js_text = _extract_visible_text(p.get("js_content", ""))

        html_chars = len(html_text)
        js_chars = len(js_text)

        if js_chars == 0:
            visibility_pct = 0.0
        else:
            visibility_pct = round(min(html_chars / js_chars * 100, 100), 1)

        html_words = set(html_text.lower().split())
        js_words = set(js_text.lower().split())
        js_only = js_words - html_words
        js_gap_pct = round(len(js_only) / max(len(js_words), 1) * 100, 1)

        # Framework detection
        raw = p.get("html_content", "")
        frameworks: list[str] = []
        if re.search(r"react|__REACT|_reactRootContainer", raw, re.I):
            frameworks.append("React")
        if re.search(r"vue\.js|Vue\.version|__vue", raw, re.I):
            frameworks.append("Vue")
        if re.search(r"angular|ng-version", raw, re.I):
            frameworks.append("Angular")
        if re.search(r"__next|next\.js|_NEXT_DATA", raw, re.I):
            frameworks.append("Next.js")
        if re.search(r"__nuxt|nuxt\.js", raw, re.I):
            frameworks.append("Nuxt")
        if re.search(r"gatsby|Gatsby", raw):
            frameworks.append("Gatsby")
        if re.search(r"svelte", raw, re.I):
            frameworks.append("Svelte")

        page_score = round(
            visibility_pct * 0.6 + max(0.0, 100 - js_gap_pct) * 0.4
        )
        page_score = max(0, page_score)
        if js_gap_pct > 50:
            page_score = min(page_score, 40)

        scores.append(page_score)
        page_results.append({
            "label": p.get("label", "Page"),
            "url": p.get("url", ""),
            "html_chars": html_chars,
            "js_chars": js_chars,
            "visibility_pct": visibility_pct,
            "js_gap_pct": js_gap_pct,
            "frameworks": frameworks,
            "page_score": page_score,
        })

    overall = round(sum(scores) / len(scores)) if scores else 0
    return {
        "pages": page_results,
        "score": overall,
        "score_items": [
            {"label": "HTML/JS content visibility", "pts": round(overall * 0.6)},
            {"label": "Low JS-only content gap", "pts": round(overall * 0.4)},
        ],
    }


# ---------------------------------------------------------------------------
# Pillar 2 — Robots
# ---------------------------------------------------------------------------

def check_robots_crawlability(domain: str) -> dict[str, Any]:
    """Fetch robots.txt and check AI bot permissions."""
    url = f"https://{domain}/robots.txt"
    r = fetch(url)

    if not r or r.status_code != 200:
        return {
            "found": False,
            "raw": "",
            "score": 0,
            "missing": True,
            "bot_rules": {},
            "blocked_count": len(AI_BOTS),
            "total_bots": len(AI_BOTS),
            "crawl_delay": None,
            "score_items": [{"label": "robots.txt missing — overall capped at 40", "pts": 0}],
        }

    raw = r.text
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(raw.splitlines())

    bot_rules: dict[str, str] = {}
    blocked_count = 0
    for bot in AI_BOTS:
        allowed = rp.can_fetch(bot, "/")
        bot_rules[bot] = "allowed" if allowed else "blocked"
        if not allowed:
            blocked_count += 1

    crawl_delay: int | None = None
    for line in raw.splitlines():
        if line.lower().startswith("crawl-delay:"):
            try:
                crawl_delay = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass

    if blocked_count >= len(AI_BOTS):
        score = 10
    elif blocked_count > len(AI_BOTS) // 2:
        score = 40
    elif blocked_count > 0:
        score = max(50, 100 - blocked_count * 8)
    else:
        score = 100

    allowed_count = len(AI_BOTS) - blocked_count
    return {
        "found": True,
        "raw": raw,
        "score": score,
        "missing": False,
        "bot_rules": bot_rules,
        "blocked_count": blocked_count,
        "total_bots": len(AI_BOTS),
        "crawl_delay": crawl_delay,
        "score_items": [
            {"label": "robots.txt found", "pts": 20},
            {"label": f"AI bots allowed ({allowed_count}/{len(AI_BOTS)})", "pts": max(0, 80 - blocked_count * 7)},
        ],
    }


# ---------------------------------------------------------------------------
# Pillar 3 — Schema Markup
# ---------------------------------------------------------------------------

def _extract_schemas(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    schemas: list[dict] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            if isinstance(data, list):
                schemas.extend(data)
            elif isinstance(data, dict):
                if data.get("@graph"):
                    schemas.extend(data["@graph"])
                else:
                    schemas.append(data)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return schemas


def check_schema_markup(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract JSON-LD schema and validate field completeness per page."""
    page_results: list[dict] = []
    scores: list[int] = []

    for p in pages:
        html = p.get("html_content", "")
        schemas = _extract_schemas(html)

        types_found = [s.get("@type", "Unknown") for s in schemas if isinstance(s, dict)]

        # Field-completeness validation per schema type
        missing_fields: dict[str, list[str]] = {}
        for schema in schemas:
            if not isinstance(schema, dict):
                continue
            stype = schema.get("@type", "")
            required = SCHEMA_REQUIRED_FIELDS.get(stype, [])
            missing = [f for f in required if f not in schema]
            if missing:
                missing_fields[stype] = missing

        # Ecommerce-specific fields
        ecommerce: dict[str, bool] = {}
        for schema in schemas:
            if not isinstance(schema, dict):
                continue
            if schema.get("@type") == "Product":
                offers = schema.get("offers", {})
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                if not isinstance(offers, dict):
                    offers = {}
                ecommerce["gtin"] = bool(
                    schema.get("gtin") or schema.get("gtin13") or schema.get("gtin8")
                )
                ecommerce["mpn"] = bool(schema.get("mpn"))
                ecommerce["review"] = bool(
                    schema.get("review") or schema.get("aggregateRating")
                )
                ecommerce["price"] = bool(offers.get("price"))
                ecommerce["return_policy"] = bool(
                    offers.get("hasMerchantReturnPolicy")
                    or schema.get("hasMerchantReturnPolicy")
                )

        if not schemas:
            page_score = 0
        else:
            page_score = 60
            page_score += min(30, len(set(types_found)) * 10)
            penalty = sum(len(v) for v in missing_fields.values()) * 5
            page_score = max(20, page_score - penalty)

        scores.append(page_score)
        page_results.append({
            "label": p.get("label", "Page"),
            "url": p.get("url", ""),
            "types_found": types_found,
            "schemas": schemas,
            "missing_fields": missing_fields,
            "ecommerce": ecommerce,
            "page_score": page_score,
        })

    overall = round(sum(scores) / len(scores)) if scores else 0
    if overall == 0:
        overall = max(overall, 0)

    return {
        "pages": page_results,
        "score": overall,
        "score_items": [
            {"label": "Schema markup present", "pts": 60},
            {"label": "Schema type variety", "pts": 30},
            {"label": "Field completeness", "pts": 10},
        ],
    }


# ---------------------------------------------------------------------------
# Pillar 4 — LLM.txt + AI Info Page
# ---------------------------------------------------------------------------

def check_llm_txt(domain: str) -> dict[str, Any]:
    """Check llms.txt / llm.txt presence and quality metrics."""
    candidates = [
        f"https://{domain}/llms.txt",
        f"https://{domain}/llms-full.txt",
        f"https://{domain}/llm.txt",
    ]

    found_url: str | None = None
    content = ""
    for url in candidates:
        r = fetch(url)
        if r and r.status_code == 200 and len(r.text.strip()) > 50:
            found_url = url
            content = r.text
            break

    if not content:
        return {
            "found": False,
            "url": None,
            "content": "",
            "score": 10,
            "lines": 0,
            "chars": 0,
            "has_links": False,
            "has_sections": False,
            "score_items": [{"label": "llm.txt not found", "pts": 10}],
        }

    lines = content.splitlines()
    has_links = bool(re.search(r"https?://", content))
    has_sections = bool(re.search(r"^#+\s", content, re.MULTILINE))

    score = 40
    if has_links:
        score += 20
    if has_sections:
        score += 20
    if len(content) > 500:
        score += 10
    if len(content) > 2000:
        score += 10
    score = min(score, 100)

    return {
        "found": True,
        "url": found_url,
        "content": content,
        "score": score,
        "lines": len(lines),
        "chars": len(content),
        "has_links": has_links,
        "has_sections": has_sections,
        "score_items": [
            {"label": "llm.txt found", "pts": 40},
            {"label": "Contains hyperlinks", "pts": 20 if has_links else 0},
            {"label": "Has section headers", "pts": 20 if has_sections else 0},
            {"label": "Content depth", "pts": min(20, len(content) // 200)},
        ],
    }


def check_ai_info_page(domain: str) -> dict[str, Any]:
    """Detect a dedicated AI information page and assess its quality."""
    candidates = [
        "/ai", "/for-ai", "/llm-info", "/ai-info",
        "/machine-readable", "/data-access", "/ai-access",
    ]

    found_url: str | None = None
    indexable = False
    has_updated_date = False
    simple_html = False
    linked_from_footer = False

    for path in candidates:
        url = f"https://{domain}{path}"
        r = fetch(url)
        if r and r.status_code == 200:
            soup = BeautifulSoup(r.text, "lxml")
            found_url = url

            robots_meta = soup.find("meta", attrs={"name": "robots"})
            if robots_meta:
                indexable = "noindex" not in (robots_meta.get("content") or "").lower()
            else:
                indexable = True

            has_updated_date = bool(
                soup.find(attrs={"itemprop": "dateModified"})
                or re.search(r"last[- ]?updated|updated:\s*\d{4}", r.text, re.I)
            )
            simple_html = len(soup.find_all("script")) < 5
            break

    if not found_url:
        return {
            "found": False,
            "url": None,
            "indexable": False,
            "has_updated_date": False,
            "simple_html": False,
            "linked_from_footer": False,
            "score": 0,
        }

    score = 30
    if indexable:
        score += 20
    if has_updated_date:
        score += 20
    if simple_html:
        score += 15
    if linked_from_footer:
        score += 15

    return {
        "found": True,
        "url": found_url,
        "indexable": indexable,
        "has_updated_date": has_updated_date,
        "simple_html": simple_html,
        "linked_from_footer": linked_from_footer,
        "score": score,
    }


# ---------------------------------------------------------------------------
# Pillar 4 — Well-known files
# ---------------------------------------------------------------------------

def check_well_known_files(domain: str) -> list[dict[str, Any]]:
    results: list[dict] = []
    for path, label in WELL_KNOWN_FILES:
        url = f"https://{domain}/{path}"
        r = fetch(url)
        status = "found" if (r and r.status_code == 200) else "missing"
        note = "Deprecated — replace with WebMCP" if "ai-plugin" in path else ""
        results.append({"path": path, "label": label, "url": url, "status": status, "note": note})
    return results


# ---------------------------------------------------------------------------
# Pillar 5 — Semantic Hierarchy
# ---------------------------------------------------------------------------

def check_semantic_hierarchy(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyse heading structure, semantic elements, meta directives per page."""
    page_results: list[dict] = []
    scores: list[int] = []

    for p in pages:
        html = p.get("html_content", "")
        soup = BeautifulSoup(html, "lxml")

        headings: list[dict] = []
        for level in range(1, 7):
            for tag in soup.find_all(f"h{level}"):
                headings.append({"level": level, "text": tag.get_text(strip=True)[:120]})

        # Hierarchy validity — no skipped levels
        valid_hierarchy = True
        prev = 0
        for h in headings:
            if h["level"] > prev + 1 and prev > 0:
                valid_hierarchy = False
                break
            prev = h["level"]

        semantic_tags = [
            "article", "section", "nav", "aside", "header",
            "footer", "main", "figure", "figcaption", "time",
        ]
        semantic_found = [t for t in semantic_tags if soup.find(t)]

        robots_meta = soup.find("meta", attrs={"name": "robots"})
        meta_directives = (robots_meta.get("content") or "") if robots_meta else ""

        text_len = len(soup.get_text())
        html_len = max(len(html), 1)
        text_to_html_ratio = round(text_len / html_len * 100, 1)

        score = 0
        if headings:
            score += 20
        if valid_hierarchy:
            score += 20
        score += min(20, len(semantic_found) * 3)
        score += min(20, int(text_to_html_ratio))
        if "noindex" not in meta_directives.lower():
            score += 10
        if soup.find("h1"):
            score += 10
        score = min(score, 100)

        scores.append(score)
        page_results.append({
            "label": p.get("label", "Page"),
            "url": p.get("url", ""),
            "headings": headings,
            "valid_hierarchy": valid_hierarchy,
            "semantic_found": semantic_found,
            "meta_directives": meta_directives,
            "text_to_html_ratio": text_to_html_ratio,
            "page_score": score,
        })

    overall = round(sum(scores) / len(scores)) if scores else 0
    return {
        "pages": page_results,
        "score": overall,
        "score_items": [
            {"label": "Heading structure present", "pts": 20},
            {"label": "Heading hierarchy valid (no skips)", "pts": 20},
            {"label": "Semantic HTML elements", "pts": 20},
            {"label": "Text-to-HTML ratio", "pts": 20},
            {"label": "Indexable + H1 present", "pts": 20},
        ],
    }


# ---------------------------------------------------------------------------
# Pillar 6 — Security Exposure
# ---------------------------------------------------------------------------

def check_security_exposure(
    domain: str, pages: list[dict[str, Any]]
) -> dict[str, Any]:
    """Probe sensitive paths; check HTML for backend info leakage."""
    critical: list[dict] = []
    backend: list[dict] = []
    customer: list[dict] = []
    html_exposure: list[dict] = []
    robots_allowlist: list[dict] = []

    critical_keywords = {"admin", "wp-admin", "wp-login"}
    backend_keywords = {".env", "phpinfo", ".git", "dump.sql", "server-status", "config.php"}

    for path in SENSITIVE_PATHS:
        url = f"https://{domain}{path}"
        r = fetch(url)
        if r and r.status_code == 200:
            entry = {"path": path, "url": url, "status": r.status_code}
            if any(k in path for k in critical_keywords):
                critical.append(entry)
            elif any(k in path for k in backend_keywords):
                backend.append(entry)
            else:
                customer.append(entry)

    for p in pages[:3]:
        html = p.get("html_content", "")
        if re.search(
            r"(Fatal error|stack.?trace|DEBUG.*=.*true|mysqli_|laravel|sqlstate)",
            html, re.I,
        ):
            html_exposure.append({
                "page": p.get("label", "Page"),
                "pattern": "Backend debug/error info visible in HTML",
            })

    score = 100
    score -= len(critical) * 30
    score -= len(backend) * 15
    score -= len(html_exposure) * 10
    score = max(0, min(score, 100))

    return {
        "score": score,
        "critical": critical,
        "backend": backend,
        "customer": customer,
        "html_exposure": html_exposure,
        "robots_allowlist": robots_allowlist,
        "score_items": [
            {"label": "No critical admin paths exposed", "pts": max(0, 40 - len(critical) * 30)},
            {"label": "No backend/config files exposed", "pts": max(0, 40 - len(backend) * 15)},
            {"label": "No HTML debug leakage", "pts": max(0, 20 - len(html_exposure) * 10)},
        ],
    }


# ---------------------------------------------------------------------------
# Bot protection detection
# ---------------------------------------------------------------------------

def check_bot_protection(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Detect Cloudflare / WAF protection that would block AI crawlers."""
    blocked_pages: list[str] = []
    protection_type: str | None = None

    for p in pages:
        html = p.get("html_content", "")
        status = p.get("status_code", 200)

        if status == 403:
            blocked_pages.append(p.get("label", "Page"))
            protection_type = protection_type or "403 Forbidden"
        elif re.search(r"cloudflare|cf-ray|checking your browser", html, re.I):
            blocked_pages.append(p.get("label", "Page"))
            protection_type = "Cloudflare"
        elif re.search(r"ddos.?guard|distil\.networks|akamai|bot.?protection", html, re.I):
            blocked_pages.append(p.get("label", "Page"))
            protection_type = protection_type or "WAF / Bot protection"

    return {
        "detected": len(blocked_pages) > 0,
        "protection_type": protection_type,
        "blocked_pages": blocked_pages,
        "robots_score_cap": 50 if len(blocked_pages) >= 2 else None,
    }


# ---------------------------------------------------------------------------
# Overall score
# ---------------------------------------------------------------------------

def compute_overall(
    js: int,
    robots: int,
    schema: int,
    llm: int,
    robots_missing: bool = False,
) -> int:
    """Weighted overall across 4 primary pillars (Semantic + Security are display-only)."""
    overall = round(js * 0.25 + robots * 0.25 + schema * 0.35 + llm * 0.15)
    if robots_missing:
        overall = min(overall, 40)
    return overall
