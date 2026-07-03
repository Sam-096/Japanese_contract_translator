"""Deterministic entity masking — prevents proper-noun/date hallucination by
never letting the translation model see (or reproduce from memory) a real
company name, address, or date. It sees an opaque token instead and the
original string is spliced back in verbatim afterward.

GiNZA label mapping
--------------------
`ja_ginza`/`ja_ginza_electra` tag entities with the ~200-label Extended
Named Entity (ENE) hierarchy (Sekine et al.), not spaCy's ~18-label OntoNotes
set — so there is no `nlp.get_pipe("ner").labels` value literally called
"ORG" or "GPE" to filter on. `_ENE_TO_BUCKET` maps the ENE labels actually
relevant to legal/contract text (companies, addresses, facilities, dates)
into the four buckets this pipeline cares about. Anything not in the map is
left unmasked deliberately — over-masking (e.g. masking common nouns tagged
with an unrelated ENE label) would strip real information out of the text
the translator needs to see.

Known environment issue: loading `ja_ginza` under spacy>=3.8 raises
`ConfigValidationError: compound_splitter -> split_mode: None is not <class
'str'>` — the model's shipped default config has `split_mode: null`, which
newer spaCy's stricter config validation rejects outright instead of
falling back to a default. `load_ginza_nlp()` below works around this by
passing `split_mode: "C"` (GiNZA's coarsest segmentation) explicitly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

_ENE_TO_BUCKET: dict[str, str] = {
    # ORG — companies and other organizations. Japanese corporate suffixes
    # (株式会社/合同会社/有限会社 etc.) are part of the entity span GiNZA
    # returns for "Company", so no separate suffix regex is needed.
    "Company": "ORG",
    "Company_Group": "ORG",
    "Organization": "ORG",
    "Organization_Other": "ORG",
    "Government": "ORG",
    "Political_Organization": "ORG",
    "Political_Organization_Other": "ORG",
    "Public_Institution": "ORG",
    "International_Organization": "ORG",
    "Law_School": "ORG",
    "Court": "ORG",
    # GPE — countries, prefectures/provinces, cities, addresses.
    "Country": "GPE",
    "Province": "GPE",
    "City": "GPE",
    "County": "GPE",
    "Domestic_Region": "GPE",
    "GPE_Other": "GPE",
    "Address": "GPE",
    "Address_Other": "GPE",
    # FAC — named buildings, offices, physical facilities.
    "Facility": "FAC",
    "Facility_Part": "FAC",
    "Facility_Other": "FAC",
    "Line": "FAC",
    "Station": "FAC",
    "Airport": "FAC",
    # DATE — anything date/period/era shaped.
    "Date": "DATE",
    "Date_Era": "DATE",
    "Period_Time": "DATE",
    "Period_Day": "DATE",
    "Period_Month": "DATE",
    "Period_Year": "DATE",
}


def load_ginza_nlp():
    """Load `ja_ginza`, working around the split_mode config bug described
    in this module's docstring. Imports spaCy lazily so importing this
    module doesn't require spaCy to be installed unless masking is used.
    """
    import spacy

    return spacy.load(
        "ja_ginza",
        config={"components": {"compound_splitter": {"split_mode": "C"}}},
    )


@dataclass
class MaskResult:
    masked_text: str
    token_map: dict[str, str] = field(default_factory=dict)

    def unmask(self, translated_text: str) -> str:
        """Splice original strings back in for every token found in
        `translated_text`. Tokens the model dropped or altered are simply
        not replaced — callers should run `verify_tokens_preserved` (see
        translate_client.py) before trusting the output as complete.
        """
        result = translated_text
        for token, original in self.token_map.items():
            result = result.replace(token, original)
        return result


class DeterministicMasker:
    """Runs GiNZA NER over raw Japanese text and swaps FAC/GPE/ORG/DATE
    entities for unique placeholder tokens, keeping an isolated map back to
    the original strings so they can be restored verbatim post-translation
    (never re-translated, never paraphrased, never hallucinated).
    """

    def __init__(self, nlp=None):
        self._nlp = nlp if nlp is not None else load_ginza_nlp()
        self._counters: dict[str, int] = {"FAC": 0, "GPE": 0, "ORG": 0, "DATE": 0}

    def reset_counters(self) -> None:
        self._counters = {"FAC": 0, "GPE": 0, "ORG": 0, "DATE": 0}

    def mask(self, text: str) -> MaskResult:
        if not text.strip():
            return MaskResult(masked_text=text, token_map={})

        doc = self._nlp(text)
        spans: list[tuple[int, int, str]] = []
        for ent in doc.ents:
            bucket = _ENE_TO_BUCKET.get(ent.label_)
            if bucket is None:
                continue
            spans.append((ent.start_char, ent.end_char, bucket))

        # Guard against masking into the middle of a negative-verb clause
        # (see negative_verb_guard.py) — an entity span itself should never
        # collide with one of these (NER doesn't tag verbs), but a
        # defensively-widened future entity type might; check explicitly
        # rather than assuming.
        from .negative_verb_guard import find_protected_spans

        protected = find_protected_spans(text)
        spans = [s for s in spans if not _overlaps_any(s[0], s[1], protected)]

        # Process right-to-left so earlier offsets stay valid as we splice.
        spans.sort(key=lambda s: s[0], reverse=True)

        token_map: dict[str, str] = {}
        masked = text
        for start, end, bucket in spans:
            original = text[start:end]
            self._counters[bucket] += 1
            token = f"[__{bucket}_ENTITY_{self._counters[bucket] - 1}__]"
            token_map[token] = original
            masked = masked[:start] + token + masked[end:]

        return MaskResult(masked_text=masked, token_map=token_map)


def _overlaps_any(start: int, end: int, spans: Iterable[tuple[int, int]]) -> bool:
    return any(start < s_end and end > s_start for s_start, s_end in spans)


_TOKEN_PATTERN = re.compile(r"\[__(?:FAC|GPE|ORG|DATE)_ENTITY_\d+__\]")


def find_all_tokens(text: str) -> list[str]:
    """All placeholder tokens present in `text`, in order of appearance."""
    return _TOKEN_PATTERN.findall(text)
