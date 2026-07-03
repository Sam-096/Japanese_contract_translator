"""Translation controller targeting a vLLM OpenAI-compatible endpoint
serving Qwen2.5-72B-Instruct.

`Qwen-2.5-72B-Instruct` needs ~140GB+ VRAM to serve (or heavy multi-GPU
quantization) — nothing in this project's environment can host it. This
module is written against vLLM's OpenAI-compatible `/v1/chat/completions`
API shape so it's a drop-in once a real endpoint exists (self-hosted or a
provider fronting the model with that API), but ships with a
`MockVLLMBackend` so the controller — prompt construction, response
parsing, token-preservation verification — is exercised and testable today
without a live model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from .masking import find_all_tokens

_SYSTEM_PROMPT = """You are a professional Japanese-to-English legal translator.

Translate the user's text to natural, formal legal English.

CRITICAL RULE: The text contains placeholder tokens in the exact form
[__TYPE_ENTITY_N__] (for example [__ORG_ENTITY_0__] or [__DATE_ENTITY_2__]).
These represent redacted proper nouns, addresses, and dates. You MUST:
- Copy every token into your output EXACTLY as it appears — same brackets,
  same underscores, same type name, same number.
- Never translate, reword, reorder, drop, duplicate, or invent a token.
- Never guess what a token might stand for. Treat it as an opaque, atomic
  unit of the sentence, like a variable name.

Translate only the surrounding legal language around the tokens."""


class TranslationBackend(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


class MockVLLMBackend:
    """Deterministic stand-in for a real vLLM server — echoes recognizable
    placeholder structure back so the controller's verification logic has
    something real to check without a network call. Not a translator.
    """

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return user_prompt


@dataclass
class HTTPVLLMBackend:
    """Real backend: calls a vLLM server's OpenAI-compatible chat endpoint.

    `base_url` should point at the server root (e.g.
    "http://localhost:8000/v1"); this appends "/chat/completions" itself,
    matching vLLM's `--served-model-name` + OpenAI SDK-compatible routes.
    """

    base_url: str
    model: str = "Qwen2.5-72B-Instruct"
    timeout_s: float = 60.0
    temperature: float = 0.0

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        import httpx

        resp = httpx.post(
            f"{self.base_url.rstrip('/')}/chat/completions",
            json={
                "model": self.model,
                "temperature": self.temperature,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=self.timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


@dataclass
class TranslationResult:
    translated_text: str
    ok: bool
    missing_tokens: list[str]
    modified_tokens: list[str]
    duplicated_tokens: list[str]

    @property
    def structural_failure(self) -> bool:
        return not self.ok


# A token that's present but subtly mangled (bracket dropped, whitespace
# inserted, digit altered) won't literal-match the original and so won't be
# caught by `find_all_tokens` on its own — this loosened pattern finds
# "token-shaped" text so a near-miss can be reported as "modified" rather
# than silently vanishing into "missing".
_LOOSE_TOKEN_PATTERN = re.compile(r"\[?_{1,2}\s*(FAC|GPE|ORG|DATE)\s*_?\s*ENTITY\s*_?\s*(\d+)\s*_{0,2}\]?")


def verify_tokens_preserved(source_masked_text: str, translated_text: str) -> TranslationResult:
    """Structural post-check: every token in the masked source must appear,
    unmodified and exactly once, in the model's output. Flags the block for
    escalation/re-translation rather than silently shipping a corrupted or
    dropped placeholder (which — once unmasked — becomes a wrong or missing
    entity in the final document).
    """
    expected = find_all_tokens(source_masked_text)
    expected_counts: dict[str, int] = {}
    for t in expected:
        expected_counts[t] = expected_counts.get(t, 0) + 1

    found_exact = find_all_tokens(translated_text)
    found_counts: dict[str, int] = {}
    for t in found_exact:
        found_counts[t] = found_counts.get(t, 0) + 1

    missing = [t for t, n in expected_counts.items() if found_counts.get(t, 0) < n]
    duplicated = [t for t, n in expected_counts.items() if found_counts.get(t, 0) > n]

    # "Modified" = something token-shaped survives in the output that isn't
    # an exact match for any expected token (e.g. "[__ORG_ENTITY_0_]" with a
    # dropped underscore, or "[__ORG ENTITY 0__]" with the format loosened).
    loose_matches = {m.group(0) for m in _LOOSE_TOKEN_PATTERN.finditer(translated_text)}
    modified = sorted(loose_matches - set(found_exact))

    ok = not missing and not duplicated and not modified
    return TranslationResult(
        translated_text=translated_text,
        ok=ok,
        missing_tokens=missing,
        modified_tokens=modified,
        duplicated_tokens=duplicated,
    )


class SemanticPipelineController:
    """Ties backend + prompt + verification together for one masked block."""

    def __init__(self, backend: TranslationBackend):
        self._backend = backend

    def translate_masked_block(self, masked_text: str) -> TranslationResult:
        if not masked_text.strip():
            return TranslationResult(
                translated_text=masked_text, ok=True,
                missing_tokens=[], modified_tokens=[], duplicated_tokens=[],
            )
        raw = self._backend.complete(_SYSTEM_PROMPT, masked_text)
        return verify_tokens_preserved(masked_text, raw)
