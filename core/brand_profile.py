"""Persistent brand profile storage and retrieval.

Profiles are stored as JSON files under data/brand_profiles/.  They carry
per-client defaults (FAQ count, voice notes) and prompt override fragments
that get injected into generation prompts via {brand_custom_rules}.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class BrandPromptOverrides:
    """Per-brand prompt fragment overrides injected at generation time."""

    brand_custom_rules: str = ""
    voice_examples: str = ""
    alt_text_rules: str = ""
    alt_text_examples: str = ""

    def to_dict(self) -> dict:
        return {
            "brand_custom_rules": self.brand_custom_rules,
            "voice_examples": self.voice_examples,
            "alt_text_rules": self.alt_text_rules,
            "alt_text_examples": self.alt_text_examples,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BrandPromptOverrides":
        return cls(
            brand_custom_rules=data.get("brand_custom_rules", ""),
            voice_examples=data.get("voice_examples", ""),
            alt_text_rules=data.get("alt_text_rules", ""),
            alt_text_examples=data.get("alt_text_examples", ""),
        )


@dataclass
class BrandProfile:
    """Full brand profile for a single client."""

    brand_name: str = ""
    store_url: str = ""
    brand_usps: list = field(default_factory=list)
    voice_notes: str = ""
    target_market: str = "UK"
    faq_count: int = 4
    prompt_overrides: BrandPromptOverrides = field(default_factory=BrandPromptOverrides)

    def to_dict(self) -> dict:
        return {
            "brand_name": self.brand_name,
            "store_url": self.store_url,
            "brand_usps": self.brand_usps,
            "voice_notes": self.voice_notes,
            "target_market": self.target_market,
            "faq_count": self.faq_count,
            "prompt_overrides": self.prompt_overrides.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BrandProfile":
        overrides_data = data.get("prompt_overrides", {})
        overrides = BrandPromptOverrides.from_dict(overrides_data) if overrides_data else BrandPromptOverrides()
        return cls(
            brand_name=data.get("brand_name", ""),
            store_url=data.get("store_url", ""),
            brand_usps=data.get("brand_usps", []),
            voice_notes=data.get("voice_notes", ""),
            target_market=data.get("target_market", "UK"),
            faq_count=int(data.get("faq_count", 4)),
            prompt_overrides=overrides,
        )


_PROFILES_DIR = Path(__file__).parent.parent / "data" / "brand_profiles"


def _safe_name(brand_name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in brand_name).strip("_") or "unnamed"


def save_profile(profile: BrandProfile) -> Path:
    """Save brand profile to disk as JSON. Returns the saved path."""
    _PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    path = _PROFILES_DIR / f"{_safe_name(profile.brand_name)}.json"
    with open(path, "w") as f:
        json.dump(profile.to_dict(), f, indent=2)
    return path


def load_profile(brand_name: str) -> Optional[BrandProfile]:
    """Load a brand profile from disk. Returns None if not found."""
    path = _PROFILES_DIR / f"{_safe_name(brand_name)}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return BrandProfile.from_dict(json.load(f))


def list_profiles() -> list[str]:
    """Return a list of saved brand profile names (raw filenames without .json)."""
    if not _PROFILES_DIR.exists():
        return []
    return [p.stem for p in sorted(_PROFILES_DIR.glob("*.json"))]


def build_custom_rules_block(overrides: BrandPromptOverrides, element: str) -> str:
    """Build the {brand_custom_rules} block to inject into a prompt.

    For alt_text: uses alt_text_rules + alt_text_examples.
    For all others: uses brand_custom_rules + voice_examples.
    """
    if element == "alt_text":
        parts = []
        if overrides.alt_text_rules:
            parts.append(f"CUSTOM ALT TEXT RULES:\n{overrides.alt_text_rules}")
        if overrides.alt_text_examples:
            parts.append(f"APPROVED EXAMPLES:\n{overrides.alt_text_examples}")
        return "\n\n".join(parts)

    parts = []
    if overrides.brand_custom_rules:
        parts.append(f"BRAND-SPECIFIC RULES:\n{overrides.brand_custom_rules}")
    if overrides.voice_examples:
        parts.append(f"APPROVED VOICE EXAMPLES:\n{overrides.voice_examples}")
    return "\n\n".join(parts)
