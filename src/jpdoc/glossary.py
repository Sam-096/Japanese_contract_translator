"""Legal glossary — injected as a cached system preamble on every translation call.

Keeping this as a plain dict (not a vector store) is deliberate: the glossary is
small, deterministic, and must override the model rather than merely suggest. We
format it once per process and reuse the string (efficiency: zero extra tokens
per clause beyond the first call).

Add domain-specific terms here as you encounter them in real documents.
"""
from __future__ import annotations

# JP term -> English rendering, locked (model must not paraphrase these)
LEGAL_TERMS: dict[str, str] = {
    # Parties
    "甲": "Party A",
    "乙": "Party B",
    "甲方": "Party A",
    "乙方": "Party B",
    "丙": "Party C",
    # Execution
    "印鑑": "registered seal (hanko)",
    "実印": "official registered seal",
    "認印": "personal seal",
    "署名": "signature",
    "記名押印": "name and seal",
    # Common contract clauses
    "連帯保証": "joint and several guarantee",
    "連帯保証人": "joint and several guarantor",
    "自動更新": "automatic renewal",
    "中途解約": "mid-term termination",
    "解約予告": "termination notice",
    "違約金": "penalty / liquidated damages",
    "損害賠償": "damages / compensation",
    "免責": "indemnification / exemption from liability",
    "不可抗力": "force majeure",
    "善管注意義務": "duty of care (good manager standard)",
    # Real-estate / tenancy
    "賃料": "rent",
    "賃貸借契約": "lease agreement",
    "敷金": "security deposit",
    "礼金": "key money (non-refundable)",
    "管理費": "management fee",
    "原状回復": "restoration to original condition",
    "明け渡し": "vacation / surrender of premises",
    # Employment / wages — 賃金 (wages) vs 賃料 (rent) share 賃 and are
    # frequently confused by the model without an explicit lock.
    "賃金": "wages",
    "割増賃金率": "premium wage rate",
    "諸手当": "allowances",
    "有給休暇": "paid leave",
    "所定外労働": "overtime work",
    "退職金": "severance pay",
    # Corporate / general
    "覚書": "memorandum of understanding (MOU)",
    "念書": "written pledge / letter of undertaking",
    "委任状": "power of attorney",
    "業務委託契約": "service agreement / outsourcing agreement",
    "秘密保持契約": "non-disclosure agreement (NDA)",
    "期間": "term / period",
    "有効期間": "term of validity",
    "甲乙": "Party A and Party B",
}

_PREAMBLE: str | None = None


def preamble() -> str:
    """Return the glossary formatted as a system-prompt preamble (built once, cached)."""
    global _PREAMBLE
    if _PREAMBLE is None:
        lines = ["You are a professional Japanese-to-English legal translator.",
                 "Always use these exact English renderings for the terms below — never paraphrase them:",
                 ""]
        for jp, en in LEGAL_TERMS.items():
            lines.append(f"  {jp} -> {en}")
        lines += [
            "",
            "Rules:",
            "- Translate the Japanese text to natural, formal English.",
            "- Preserve document structure: headings stay headings, lists stay lists, tables stay tables.",
            "- Where text is marked [?] or [UNREADABLE_KANJI], carry the marker into the English output unchanged.",
            "- Never invent a [?] or [UNREADABLE_KANJI] marker yourself — only carry through ones "
            "that already appear in the source text. For a blank fill-in field (e.g. an empty "
            "underscored space, or a date template like 年 月 日 with no digits filled in), "
            "translate it as a bracketed placeholder naming what belongs there instead — "
            "e.g. 年 月 日 -> [Year] [Month] [Day], a blank hour/minute -> [Hour] [Minute].",
            "- Output ONLY the English translation — no commentary, no explanations.",
        ]
        _PREAMBLE = "\n".join(lines)
    return _PREAMBLE
