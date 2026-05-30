from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer


def build_styles():
    styles = getSampleStyleSheet()
    base = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        spaceAfter=6,
    )
    h1 = ParagraphStyle(
        "H1",
        parent=base,
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        spaceBefore=8,
        spaceAfter=10,
    )
    h2 = ParagraphStyle(
        "H2",
        parent=base,
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        spaceBefore=8,
        spaceAfter=6,
    )
    h3 = ParagraphStyle(
        "H3",
        parent=base,
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        spaceBefore=6,
        spaceAfter=4,
    )
    bullet = ParagraphStyle(
        "Bullet",
        parent=base,
        leftIndent=14,
        firstLineIndent=0,
        spaceAfter=4,
    )
    code = ParagraphStyle(
        "Code",
        parent=base,
        fontName="Courier",
        fontSize=9,
        leading=12,
        backColor=colors.whitesmoke,
        borderWidth=0.5,
        borderColor=colors.lightgrey,
        borderPadding=4,
        leftIndent=6,
        rightIndent=6,
        spaceBefore=4,
        spaceAfter=8,
    )
    return base, h1, h2, h3, bullet, code


def inline_md_to_rl(text: str) -> str:
    text = html.escape(text.strip())
    text = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    return text


def md_to_story(md_text: str):
    base, h1, h2, h3, bullet, code = build_styles()
    story = []
    lines = md_text.splitlines()
    in_code = False
    code_buf: list[str] = []

    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                story.append(Preformatted("\n".join(code_buf), code))
                code_buf = []
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_buf.append(line)
            continue

        if not stripped:
            story.append(Spacer(1, 4))
            continue

        if stripped.startswith("# "):
            story.append(Paragraph(inline_md_to_rl(stripped[2:]), h1))
            continue
        if stripped.startswith("## "):
            story.append(Paragraph(inline_md_to_rl(stripped[3:]), h2))
            continue
        if stripped.startswith("### "):
            story.append(Paragraph(inline_md_to_rl(stripped[4:]), h3))
            continue

        if stripped.startswith("- "):
            story.append(Paragraph(inline_md_to_rl(stripped[2:]), bullet, bulletText="•"))
            continue

        num_match = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if num_match:
            story.append(
                Paragraph(
                    inline_md_to_rl(num_match.group(2)),
                    bullet,
                    bulletText=f"{num_match.group(1)}.",
                )
            )
            continue

        story.append(Paragraph(inline_md_to_rl(stripped), base))

    if code_buf:
        story.append(Preformatted("\n".join(code_buf), code))
    return story


def generate_pdf(md_path: Path, pdf_path: Path):
    text = md_path.read_text(encoding="utf-8")
    story = md_to_story(text)
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="SOP Segmentacion Clientes DPO",
        author="DashboardDiasPico",
    )
    doc.build(story)


def main():
    parser = argparse.ArgumentParser(description="Genera PDF desde SOP markdown.")
    parser.add_argument(
        "--input",
        default="docs/SOP_Segmentacion_Clientes_DPO.md",
        help="Ruta del markdown de entrada.",
    )
    parser.add_argument(
        "--output",
        default="docs/SOP_Segmentacion_Clientes_DPO.pdf",
        help="Ruta del PDF de salida.",
    )
    args = parser.parse_args()

    md_path = Path(args.input).resolve()
    pdf_path = Path(args.output).resolve()

    if not md_path.exists():
        raise SystemExit(f"No existe archivo markdown: {md_path}")

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    generate_pdf(md_path, pdf_path)
    print(f"PDF generado: {pdf_path}")


if __name__ == "__main__":
    main()
