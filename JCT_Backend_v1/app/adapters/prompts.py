"""Shared batch-translation prompt fragments for the Groq and Gemini adapters
(groq_client.py / gemini_client.py). Kept in one place so both providers see
identical structural-preservation instructions.

Why this exists: LLMs given a batch of short, fragmented table-cell strings
sometimes "heal" the input into more natural prose — merging two adjacent
cells' meaning together, or dropping the layout-carrying characters (pipes,
underscores used as blank-fill, parenthesized alternatives like '有・無') that
the row/column reconstruction in render_service.py depends on. The batch
instruction below explicitly forbids that; both adapters already reduce the
chance of it further by requesting strict JSON-mode output
(`response_format`/`response_mime_type`), which constrains the model to a
flat key->string mapping rather than free-form text where cross-value
bleeding is easy.
"""
from __future__ import annotations

LEGAL_GUARDRAILS = (
    "LIABILITY RECIPROCITY: If the source text states both parties (甲/Party A, "
    "乙/Party B) are mutually liable for damages, the translation must preserve "
    "that mutual liability — do not shift or unbalance which party bears "
    "responsibility.\n"
    "NEGATIVE VERB INTEGRITY: Negative/prohibitive conditional verbs (e.g. "
    "'してはならない', 'することはできない') must be translated as a complete "
    "clause — never drop the negation or translate only part of the verb phrase."
)

CELL_INSTRUCTION = (
    "The text below is one field from a form/table — a short label or value, "
    "not prose. Translate it as a short label or value of similar length to "
    "the source; do not expand it into a full sentence or list multiple synonyms."
)

BATCH_INSTRUCTION = (
    "The JSON object below maps an id to a short field from a form/table (a "
    "label or value, not prose). Translate every value to English.\n"
    "STRUCTURAL ALIGNMENT RULES:\n"
    "1. NO ROW BLEEDING: treat every key-value pair as a completely isolated "
    "micro-document. Never merge data or meaning from one key into another, "
    "even if two keys look like they belong to the same sentence or clause.\n"
    "2. GRID SYMBOL PRESERVATION: preserve structural layout characters "
    "(vertical dividers '|', hyphens, underscores used as blank-fill, "
    "parentheses) exactly, in the same position within the string.\n"
    "3. FORM MARKERS: translate alternatives cleanly while keeping the "
    "marker structure, e.g. '(有・無)' -> '(Yes/No)'.\n"
    "4. Keep each translation a short label/value of similar length to its "
    "source — do not expand any of them into a full sentence or list synonyms.\n"
    "Respond with ONLY a JSON object mapping the SAME ids to their English "
    "translations. Preserve every id exactly; do not add, drop, or rename any. "
    "Do not wrap the JSON in markdown code fences."
)


def strip_json_fences(raw: str) -> str:
    """Defensive unwrap for a response that ignored 'no markdown fences' and
    wrapped the JSON in a ```json ... ``` block anyway. A no-op if there's no
    fence — safe to call unconditionally before json.loads().
    """
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:]
    return text.strip()


def is_capacity_error(exc: Exception) -> bool:
    """True for a provider capacity/availability failure — 429 rate limit,
    503 unavailable/overloaded, or an SDK exception whose type name says as
    much. Both adapters raise their own *RateLimitedError (see
    core/exceptions.py) when this is true, which translate_service.py
    catches to retry with the other configured provider.
    """
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    text = str(exc).lower()
    type_name = type(exc).__name__.lower()
    return (
        status in (429, 503)
        or "rate limit" in text
        or "unavailable" in text
        or "overloaded" in text
        or "resourceexhausted" in type_name
        or "serviceunavailable" in type_name
    )
