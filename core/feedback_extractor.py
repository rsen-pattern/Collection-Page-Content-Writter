"""Extract banned phrases from freeform feedback text.

Uses Haiku via Bifrost to identify specific phrases the user has marked as
rejected. Returns a list of strings — empty list when no clear bans are found.

Parses a simple line-per-phrase format rather than JSON mode to reduce friction.
"""

from __future__ import annotations

from openai import OpenAI


_EXTRACTION_PROMPT = """You are a content reviewer. The text below is a freeform feedback log from a content review process. Some entries explicitly call out specific phrases that should never be used again.

Extract ONLY exact phrases that are being explicitly banned, rejected, or flagged as filler. Do not extract:
- General feedback ("be more concise") — that's not a phrase ban
- Descriptions of problems ("the copy is too formal") — that's not a phrase ban
- Topics to avoid ("don't mention shipping") — that's a topic, not a phrase
- Words from the feedback itself that aren't being banned

Output rules:
- One phrase per line, no quotes, no bullets, no numbering
- Use the exact wording from the feedback (lowercase, exact spelling)
- If no specific banned phrases are found, output the single word: NONE
- Do NOT invent or paraphrase — if it's not literally written in the feedback as a banned phrase, skip it

FEEDBACK:
{feedback}

EXTRACTED BANNED PHRASES:"""


def extract_banned_phrases(
    api_key: str,
    feedback: str,
    model: str = "anthropic/claude-haiku-4-5",
    base_url: str = "https://bifrost.pattern.com",
) -> list[str]:
    """Extract explicitly-banned phrases from freeform feedback.

    Returns empty list when nothing extractable is found.
    """
    if not feedback.strip():
        return []

    if not base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"

    client = OpenAI(api_key=api_key, base_url=base_url)

    prompt = _EXTRACTION_PROMPT.format(feedback=feedback.strip())

    response = client.chat.completions.create(
        model=model,
        max_tokens=500,
        messages=[
            {"role": "system", "content": "You extract structured data from text. Be precise. Do not invent."},
            {"role": "user", "content": prompt},
        ],
    )

    raw = (response.choices[0].message.content or "").strip()

    if raw.upper() == "NONE" or not raw:
        return []

    phrases = []
    for line in raw.split("\n"):
        line = line.strip().strip("\"'`-•* ")
        if not line or line.upper() == "NONE":
            continue
        word_count = len(line.split())
        if 1 <= word_count <= 12:
            phrases.append(line)

    return phrases
