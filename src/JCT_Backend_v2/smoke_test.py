"""Exercises all five JCT_Backend_v2 components together against a synthetic
example (no real PDF needed). Run directly:

    .venv/Scripts/python.exe -m JCT_Backend_v2.smoke_test

Not a pytest suite — a runnable narrative check that the components compose
correctly end-to-end, per each stage:
  1. Spatial sort correctly un-interlaces a synthetic two-column layout.
  2. DeterministicMasker masks real entities out of real contract sentences.
  3. negative_verb_guard finds and protects a real prohibitive clause.
  4. SemanticPipelineController: identity mock (should PASS verification)
     and a corrupted-token mock (should FAIL verification) — proves the
     structural-failure check actually discriminates good from bad output.
  5. render_html compiles a small DocumentCanvas to a real PDF via
     WeasyPrint and confirms the file was written.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .masking import DeterministicMasker
from .negative_verb_guard import find_protected_spans
from .render_html import compile_html_to_pdf, render_canvas_to_html
from .schema import BoundingBox, DocumentCanvas, TextBlock
from .spatial_sort import spatial_sort
from .translate_client import MockVLLMBackend, SemanticPipelineController


def _check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        _FAILURES.append(label)


_FAILURES: list[str] = []


def test_spatial_sort() -> None:
    print("\n-- 1. spatial_sort: two-column un-interlacing --")
    # Column A (left, x 0.05-0.40): 3 rows. Column B (right, x 0.60-0.95): 3 rows.
    # Interleaved input order simulates raw PDF word extraction order.
    items = [
        ("A1", BoundingBox(x0=0.05, y0=0.10, x1=0.40, y1=0.15)),
        ("B1", BoundingBox(x0=0.60, y0=0.10, x1=0.95, y1=0.15)),
        ("A2", BoundingBox(x0=0.05, y0=0.20, x1=0.40, y1=0.25)),
        ("B2", BoundingBox(x0=0.60, y0=0.20, x1=0.95, y1=0.25)),
        ("A3", BoundingBox(x0=0.05, y0=0.30, x1=0.40, y1=0.35)),
        ("B3", BoundingBox(x0=0.60, y0=0.30, x1=0.95, y1=0.35)),
    ]
    result = spatial_sort(items, box_getter=lambda item: item[1])
    order = [label for label, _ in result]
    expected = ["A1", "A2", "A3", "B1", "B2", "B3"]
    _check("column A fully precedes column B", order == expected, f"got {order}")


def test_masking() -> None:
    print("\n-- 2. DeterministicMasker: NER masking --")
    masker = DeterministicMasker()
    text = "株式会社山田商事は、2024年4月1日付で東京都千代田区の事務所を賃貸する。"
    result = masker.mask(text)
    print(f"  raw:    {text}")
    print(f"  masked: {result.masked_text}")
    print(f"  tokens: {result.token_map}")

    _check("at least one entity masked", len(result.token_map) > 0, f"{len(result.token_map)} tokens")
    _check(
        "company name replaced with ORG token",
        "株式会社山田商事" not in result.masked_text,
        result.masked_text,
    )
    roundtrip = result.unmask(result.masked_text)
    _check("unmask restores original text exactly", roundtrip == text, roundtrip)


def test_negative_verb_guard() -> None:
    print("\n-- 3. negative_verb_guard: clause protection --")
    text = "従業員は業務上知り得た秘密を第三者に開示してはならない。ただし法令に基づく場合はこの限りではない。"
    spans = find_protected_spans(text)
    print(f"  text: {text}")
    print(f"  protected spans: {spans}")
    _check("prohibitive clause detected", len(spans) >= 1)
    if spans:
        start, end = spans[0]
        _check(
            "protected span covers 'してはならない'",
            "してはならない" in text[start:end],
            text[start:end],
        )


def test_translation_controller() -> None:
    print("\n-- 4. SemanticPipelineController: token verification --")
    masked_text = "The [__ORG_ENTITY_0__] shall not disclose confidential information obtained on [__DATE_ENTITY_1__]."

    identity_controller = SemanticPipelineController(MockVLLMBackend())
    good_result = identity_controller.translate_masked_block(masked_text)
    _check("identity backend: verification passes", good_result.ok, str(good_result))

    class CorruptingMockBackend:
        def complete(self, system_prompt: str, user_prompt: str) -> str:
            return user_prompt.replace("[__DATE_ENTITY_1__]", "[__DATE_ENTITY_1_]")  # dropped underscore

    corrupt_controller = SemanticPipelineController(CorruptingMockBackend())
    bad_result = corrupt_controller.translate_masked_block(masked_text)
    _check(
        "corrupting backend: verification correctly FAILS",
        bad_result.structural_failure,
        f"missing={bad_result.missing_tokens} modified={bad_result.modified_tokens}",
    )


def test_render_html() -> None:
    print("\n-- 5. render_html: WeasyPrint compilation --")
    canvas = DocumentCanvas(
        page_number=1,
        width_pt=595.0,   # A4
        height_pt=842.0,
        blocks=[
            TextBlock(
                id="b0",
                raw_text="株式会社山田商事は、本契約に基づき業務を委託する。",
                translated_text="[__ORG_ENTITY_0__] hereby entrusts the business under this Agreement, and the parties agree that all obligations herein shall survive termination of this Agreement in perpetuity unless otherwise stated.",
                bounding_box=BoundingBox(x0=0.1, y0=0.1, x1=0.5, y1=0.15),
                font_size=11.0,
            ),
        ],
    )
    html_str = render_canvas_to_html(canvas)
    _check("HTML contains translated text", "hereby entrusts" in html_str)
    _check("HTML contains absolute positioning", "position: absolute" in html_str)

    out_dir = Path(__file__).resolve().parent.parent.parent / "scratchpad_v2_render_test"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "smoke_test.pdf"
    compile_html_to_pdf(html_str, str(out_path))
    _check("PDF file written", out_path.exists() and out_path.stat().st_size > 0, str(out_path))


def main() -> int:
    test_spatial_sort()
    test_masking()
    test_negative_verb_guard()
    test_translation_controller()
    test_render_html()

    print(f"\n{'='*50}")
    if _FAILURES:
        print(f"{len(_FAILURES)} FAILURE(S): {_FAILURES}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
