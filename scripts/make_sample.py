"""Generate a test contract PDF with a CJK-capable font so text extracts cleanly.

Uses the Noto Sans JP font if present, otherwise writes a plain-text .txt file
the pipeline can't process (and tells you what to do). This is a dev helper only.
"""
import sys
from pathlib import Path

# Try reportlab for proper Unicode PDF generation.
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas as rl_canvas

    # Look for any CJK font on the system.
    candidates = [
        Path("C:/Windows/Fonts/NotoSansCJK-Regular.ttc"),
        Path("C:/Windows/Fonts/meiryo.ttc"),
        Path("C:/Windows/Fonts/msgothic.ttc"),
        Path("C:/Windows/Fonts/YuGothR.ttc"),
    ]
    font_path = next((p for p in candidates if p.exists()), None)
    if font_path is None:
        print("No CJK font found. Writing plain-text sample instead.")
        Path("keiyaku_sample.txt").write_text(
            "第一条 本契約は甲と乙の間で締結される。\n第二条 賃料は毎月末日までに支払うものとする。\n",
            encoding="utf-8",
        )
        print("Written: keiyaku_sample.txt")
        sys.exit(0)

    pdfmetrics.registerFont(TTFont("CJK", str(font_path)))
    c = rl_canvas.Canvas("keiyaku.pdf", pagesize=A4)
    c.setFont("CJK", 14)
    c.drawString(72, 750, "第一条　本契約は甲と乙の間で締結される。")
    c.drawString(72, 720, "第二条　賃料は毎月末日までに支払うものとする。")
    c.drawString(72, 690, "第三条　連帯保証人は乙の債務を連帯保証する。")
    c.drawString(72, 660, "第四条　本契約は自動更新とする。")
    c.save()
    print("Written: keiyaku.pdf (with CJK font)")

except ImportError:
    # Fallback: write a UTF-8 text file as a plain input.
    print("reportlab not installed — writing .txt sample")
    Path("keiyaku_sample.txt").write_text(
        "第一条 本契約は甲と乙の間で締結される。\n第二条 賃料は毎月末日までに支払うものとする。\n",
        encoding="utf-8",
    )
    print("Written: keiyaku_sample.txt  (install reportlab to get a PDF)")
