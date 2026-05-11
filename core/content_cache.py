"""Cross-run content cache — keyed on (brand, URL, primary keyword).

When the same brand re-runs the pipeline with a slightly different keyword
file, this cache lets us recognise already-generated collections instead of
treating every entry as net-new. Per-cache-entry input hashes let us tell
the user "the inputs changed since last time" so cached content isn't
silently stale.

Cache files are plain JSON under ``data/content_cache/<safe_brand>/<hash>.json``.
Local disk only — they don't sync across deployments or users, and they're
gitignored so they never end up in the repo.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


_CACHE_DIR = Path(__file__).parent.parent / "data" / "content_cache"


def _safe_brand_name(brand_name: str) -> str:
    """Lossy but deterministic safe filename component for a brand name."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in brand_name)
    return (safe[:40] or "unnamed").strip("_") or "unnamed"


def _cache_path(brand_name: str, collection_url: str, primary_keyword: str) -> Path:
    """Compute a deterministic cache path for a (brand, URL, primary kw) tuple.

    The path components are SHA-256 hashed so unicode brand names and very
    long URLs still produce valid filesystem paths.
    """
    key = f"{brand_name}|{collection_url}|{primary_keyword.lower()}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return _CACHE_DIR / _safe_brand_name(brand_name) / f"{digest}.json"


def save_to_cache(
    brand_name: str,
    collection_url: str,
    primary_keyword: str,
    content: dict,
    inputs: dict,
) -> Path:
    """Save generated content to cache. Returns the cache file path.

    ``inputs`` captures the brief signal used to generate (secondary
    keyword hash, USPs hash, voice notes hash, past_feedback hash) so
    diff_inputs() can later detect when cached content was produced
    under different conditions.
    """
    path = _cache_path(brand_name, collection_url, primary_keyword)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "saved_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "brand_name": brand_name,
        "collection_url": collection_url,
        "primary_keyword": primary_keyword,
        "inputs": inputs,
        "content": content,
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def load_from_cache(
    brand_name: str,
    collection_url: str,
    primary_keyword: str,
) -> Optional[dict]:
    """Return the cached payload (full envelope) for the key, or None.

    The payload mirrors what save_to_cache wrote: a dict with ``saved_at``,
    ``inputs``, and ``content`` keys.
    """
    path = _cache_path(brand_name, collection_url, primary_keyword)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _hash_iter(values) -> str:
    joined = "|".join(sorted(str(v) for v in values))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def _hash_str(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()[:16]


def hash_inputs(brief) -> dict[str, str]:
    """Hash the inputs that meaningfully affect output.

    Used as the diff fingerprint stored alongside cached content so the UI
    can warn "the inputs differ from when content was last generated".
    Accepts any object with ``secondary_keywords``, ``brand_usps``,
    ``voice_notes``, ``past_feedback`` attributes (ContentBrief shape).
    """
    return {
        "secondary_kws_hash": _hash_iter(getattr(brief, "secondary_keywords", []) or []),
        "usps_hash": _hash_iter(getattr(brief, "brand_usps", []) or []),
        "voice_hash": _hash_str(getattr(brief, "voice_notes", "") or ""),
        "past_feedback_hash": _hash_str(getattr(brief, "past_feedback", "") or ""),
    }


_INPUT_LABELS = {
    "secondary_kws_hash": "secondary keywords",
    "usps_hash": "brand USPs",
    "voice_hash": "voice notes",
    "past_feedback_hash": "past feedback",
}


def diff_inputs(old: dict, new: dict) -> list[str]:
    """Return human-readable labels for inputs that changed between two hash dicts."""
    diffs: list[str] = []
    for key, label in _INPUT_LABELS.items():
        if old.get(key) != new.get(key):
            diffs.append(label)
    return diffs


__all__ = [
    "save_to_cache",
    "load_from_cache",
    "hash_inputs",
    "diff_inputs",
]
