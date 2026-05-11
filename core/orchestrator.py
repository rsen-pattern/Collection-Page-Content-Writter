"""Batch generation orchestrator — pure Python, no Streamlit dependency.

Sits between the page-level UI in ``pages/4_Content_Studio.py`` and the
LLM wrappers in ``core.content_generator``. Same orchestration drives
both the existing Streamlit flow and any future CLI / API entry point.

UI feedback flows through optional callbacks (``on_start``, ``on_progress``,
``on_throttle``, ``cancel_check``) so the orchestrator stays headless.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from core.brief_builder import ContentBrief


@dataclass
class GenerationConfig:
    """All settings needed to run a batch generation, decoupled from Streamlit."""

    api_key: str
    base_url: str = "https://bifrost.pattern.com"
    model: str = "anthropic/claude-sonnet-4-6"
    humanize_enabled: bool = False
    brand_name: str = ""
    voice_notes: str = ""
    force_regenerate: bool = False
    batch_faq_topics: list[str] = field(default_factory=list)


@dataclass
class GenerationResult:
    """Output of generating content for a single collection."""

    brief: ContentBrief
    content: dict
    success: bool
    error: str = ""
    model_used: str = ""
    duration_seconds: float = 0.0
    skipped: bool = False
    cancelled: bool = False


def _generate_one(
    brief: ContentBrief,
    config: GenerationConfig,
    on_throttle: Optional[Callable[[float], None]] = None,
) -> GenerationResult:
    """Generate full content for a single brief. Raises nothing — packs errors
    into the returned GenerationResult."""
    # Lazy import so importing core.orchestrator doesn't drag in openai.
    from core.content_generator import generate_content, humanize_content

    start = time.monotonic()
    try:
        gen_content, used_model = generate_content(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
            brief=brief,
            generation_type="full",
            batch_faq_topics=config.batch_faq_topics,
            on_wait=on_throttle,
        )
        content = {
            "seo_title": gen_content.seo_title,
            "collection_title": gen_content.collection_title,
            "description": gen_content.description,
            "meta_description": gen_content.meta_description,
            "faqs": gen_content.faqs,
            "suggested_headings": gen_content.suggested_headings,
            "suggested_tags": gen_content.suggested_tags,
            "approved": False,
        }
        if config.humanize_enabled and content["description"]:
            humanized, _ = humanize_content(
                api_key=config.api_key,
                base_url=config.base_url,
                model=config.model,
                content_text=content["description"],
                brand_name=config.brand_name,
                voice_notes=config.voice_notes,
                on_wait=on_throttle,
            )
            content["description"] = humanized

        return GenerationResult(
            brief=brief,
            content=content,
            success=True,
            model_used=used_model,
            duration_seconds=time.monotonic() - start,
        )
    except Exception as e:
        return GenerationResult(
            brief=brief,
            content={},
            success=False,
            error=str(e),
            duration_seconds=time.monotonic() - start,
        )


def generate_for_batch(
    briefs: list[ContentBrief],
    config: GenerationConfig,
    already_generated: Optional[dict[str, dict]] = None,
    on_start: Optional[Callable[[ContentBrief, int, int], None]] = None,
    on_progress: Optional[Callable[[GenerationResult, int, int], None]] = None,
    on_throttle: Optional[Callable[[float], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> list[GenerationResult]:
    """Generate content for a batch of briefs.

    Callbacks (all optional):

    - ``on_start(brief, idx, total)`` — fired before each generation starts.
    - ``on_progress(result, idx, total)`` — fired after each generation completes.
    - ``on_throttle(seconds)`` — fired when the rate limiter throttles a request.
    - ``cancel_check() -> bool`` — polled between collections; True stops early.

    Already-generated collections (keyed by ``brief.collection_url``) are
    skipped unless ``config.force_regenerate`` is True. Cancelled collections
    have ``cancelled=True`` and ``success=False``.

    Returns one ``GenerationResult`` per input brief, in the same order.
    """
    already_generated = already_generated or {}
    total = len(briefs)
    results: list[GenerationResult] = []

    for idx, brief in enumerate(briefs):
        if cancel_check is not None:
            try:
                cancelled = bool(cancel_check())
            except Exception:
                cancelled = False
            if cancelled:
                # Mark this brief + every brief after as cancelled, in order.
                for remaining in briefs[idx:]:
                    results.append(GenerationResult(
                        brief=remaining,
                        content={},
                        success=False,
                        cancelled=True,
                        error="cancelled",
                    ))
                return results

        if on_start is not None:
            try:
                on_start(brief, idx, total)
            except Exception:
                pass

        existing = already_generated.get(brief.collection_url)
        if existing and not config.force_regenerate:
            result = GenerationResult(
                brief=brief,
                content=existing,
                success=True,
                skipped=True,
            )
        else:
            result = _generate_one(brief, config, on_throttle=on_throttle)

        results.append(result)
        if on_progress is not None:
            try:
                on_progress(result, idx, total)
            except Exception:
                pass

    return results


__all__ = ["GenerationConfig", "GenerationResult", "generate_for_batch"]
