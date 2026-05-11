"""Generation history — snapshot, append, restore.

Centralises the snapshot/restore semantics for generated content so the
Content Studio and Single URL Writer share one implementation.

History is stored on the same `content` dict that holds the current
generation under the key ``"history"``. Each entry is a dict with:

- ``timestamp`` (ISO UTC string)
- ``model_used``
- ``generation_type`` (``"full"``, ``"description"``, ``"faqs"``, etc.)
- ``humanized`` (bool)
- ``snapshot``: dict mirroring the top-level generation fields at the
  point of the snapshot. The ``history`` key itself is NEVER snapshotted
  to avoid recursion / unbounded growth.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional


MAX_HISTORY = 10

# Fields that count as "the generation" — captured into snapshots and
# restored as a unit. New top-level fields added to generated_content
# should be listed here so they round-trip through history.
SNAPSHOT_FIELDS = (
    "seo_title",
    "collection_title",
    "description",
    "meta_description",
    "faqs",
    "suggested_headings",
    "suggested_tags",
    "alt_text",
)


def append_snapshot(
    content: dict,
    *,
    generation_type: str,
    model_used: str = "",
    humanized: bool = False,
    timestamp: Optional[str] = None,
) -> None:
    """Append the current content state to ``content['history']``.

    Mutates ``content`` in place. Caps the history list at MAX_HISTORY
    entries, dropping the oldest when the cap is exceeded.

    Snapshots ONLY the SNAPSHOT_FIELDS keys — never recursively snapshots
    the history list itself.
    """
    if content is None:
        return

    snapshot = {key: content.get(key) for key in SNAPSHOT_FIELDS if key in content}
    entry = {
        "timestamp": timestamp or (datetime.utcnow().isoformat(timespec="seconds") + "Z"),
        "model_used": model_used,
        "generation_type": generation_type,
        "humanized": bool(humanized),
        "snapshot": snapshot,
    }

    history = content.get("history") or []
    history.append(entry)
    # Keep the most recent MAX_HISTORY entries.
    content["history"] = history[-MAX_HISTORY:]


def restore_snapshot(content: dict, snapshot: dict) -> None:
    """Restore generation fields from a snapshot dict.

    Mutates ``content`` in place. ``content['history']`` is preserved
    untouched so a restore action is itself reversible.
    """
    if not snapshot:
        return
    preserved_history = content.get("history") or []
    for key, value in snapshot.items():
        content[key] = value
    content["history"] = preserved_history


def has_meaningful_content(content: dict) -> bool:
    """Return True when ``content`` has at least one populated snapshot field.

    Used to decide whether to snapshot before overwriting — there's no
    point snapshotting an empty placeholder.
    """
    return any(content.get(key) for key in SNAPSHOT_FIELDS)


__all__ = [
    "MAX_HISTORY",
    "SNAPSHOT_FIELDS",
    "append_snapshot",
    "restore_snapshot",
    "has_meaningful_content",
]
