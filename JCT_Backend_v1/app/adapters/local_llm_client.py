"""Adapter over the existing jpdoc.translate module (local Ollama, qwen2.5:3b-instruct).

This does not reimplement translation — it wraps the already-working Tier-A pipeline
in src/jpdoc/translate.py so both the CLI and the API share one translation path.
"""
from __future__ import annotations

from jpdoc.schema import Block, BlockType, Document


class LocalOllamaTranslator:
    name = "local_ollama"

    def translate_document(self, doc: Document) -> Document:
        from jpdoc.translate import translate_document as _translate

        return _translate(doc)

    def translate_blocks(self, blocks: list[Block]) -> None:
        from jpdoc.glossary import preamble
        from jpdoc.translate import _translate_block, _translate_table

        sys_prompt = preamble()
        for b in blocks:
            if b.type == BlockType.TABLE:
                _translate_table(b, sys_prompt)
            else:
                _translate_block(b, sys_prompt)
