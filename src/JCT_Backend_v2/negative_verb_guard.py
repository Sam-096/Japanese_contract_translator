"""Protects negative/prohibitive verb phrases from being severed from their
parent clause by chunk-boundary splitting.

Why this matters: a chunker that splits Japanese text on generic boundaries
(commas, newlines, a max-length cutoff) can land a cut point between a verb
stem and its negative-prohibitive ending — e.g. splitting "...をしては
＼ならない" mid-phrase. Once the two halves are translated as separate
chunks, the negation is easily lost or misattributed (the classic failure
mode described in the module's callers: "It is not possible" instead of
"[X] must not be done"). The fix is not smarter translation — it's never
creating that split point.

This module does not itself chunk anything; `find_protected_spans` reports
character ranges a caller's chunker must treat as atomic, and `safe_split`
is a small helper for callers who just need "give me legal split points for
this text."
"""
from __future__ import annotations

import re

# Ordered roughly most-specific first; a prohibitive/negative-ability verb
# ending, anchored to the (Japanese-only) stem that precedes it so the whole
# clause is captured, not just the ending itself.
_NEGATIVE_VERB_PATTERNS: list[re.Pattern[str]] = [re.compile(p) for p in [
    r"[^\s。、][\w぀-ヿ一-鿿]*してはならない",
    r"[^\s。、][\w぀-ヿ一-鿿]*してはいけない",
    r"[^\s。、][\w぀-ヿ一-鿿]*することはできない",
    r"[^\s。、][\w぀-ヿ一-鿿]*することができない",
    r"[^\s。、][\w぀-ヿ一-鿿]*してはならず",
    r"[^\s。、][\w぀-ヿ一-鿿]*(?<!ない)ないものとする",
]]


def find_protected_spans(text: str) -> list[tuple[int, int]]:
    """Character (start, end) ranges — each one a full negative/prohibitive
    verb clause — that a chunker must not split inside of.
    """
    spans: list[tuple[int, int]] = []
    for pattern in _NEGATIVE_VERB_PATTERNS:
        for m in pattern.finditer(text):
            spans.append((m.start(), m.end()))
    spans.sort()
    return _merge_overlapping(spans)


def _merge_overlapping(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    merged = [spans[0]]
    for start, end in spans[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def is_safe_split_point(index: int, protected_spans: list[tuple[int, int]]) -> bool:
    """False if splitting `text` at `index` would land strictly inside one
    of `protected_spans` (splitting exactly at a span's start/end boundary
    is fine — only an interior cut severs the clause).
    """
    return not any(start < index < end for start, end in protected_spans)


def safe_split(text: str, candidate_breaks: list[int]) -> list[int]:
    """Filter `candidate_breaks` (character indices into `text`) down to
    only those that don't cut through a protected negative-verb clause.
    """
    protected = find_protected_spans(text)
    return [i for i in candidate_breaks if is_safe_split_point(i, protected)]
