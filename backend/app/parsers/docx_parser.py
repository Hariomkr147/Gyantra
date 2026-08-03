"""DOCX parsing with python-docx — headings, paragraphs, tables, inline math."""

from __future__ import annotations

import logging
import re

from app.models.enums import BlockType, ParseRoute
from app.models.schemas import DocumentIntelligenceResult, TextBlock

logger = logging.getLogger("gyantra.parser.docx")

_HEADING_STYLE = re.compile(r"heading\s*(\d)", re.IGNORECASE)
_EQUATION_HINTS = re.compile(r"[=≈≤≥±×÷∑∫√]|\\frac|\\sum|\^\d")


def parse_docx(file_path: str, route: ParseRoute = ParseRoute.LIGHTWEIGHT_TEXT) -> DocumentIntelligenceResult:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(file_path)
    blocks: list[TextBlock] = []
    plain_parts: list[str] = []
    table_count = equation_count = figure_count = 0

    # Walk body elements in document order so tables stay in position.
    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]

        if tag == "p":
            para = Paragraph(child, doc)
            text = para.text.strip()
            if not text:
                continue

            style_name = (para.style.name if para.style else "") or ""
            m = _HEADING_STYLE.search(style_name)

            if m:
                blocks.append(
                    TextBlock(
                        block_type=BlockType.HEADING,
                        content=text,
                        level=int(m.group(1)),
                    )
                )
            elif style_name.lower() in ("title", "subtitle"):
                blocks.append(
                    TextBlock(block_type=BlockType.HEADING, content=text, level=1)
                )
            elif style_name.lower().startswith("list"):
                blocks.append(TextBlock(block_type=BlockType.LIST, content=text))
            elif _EQUATION_HINTS.search(text) and len(text) < 200:
                equation_count += 1
                blocks.append(TextBlock(block_type=BlockType.EQUATION, content=text))
            else:
                blocks.append(TextBlock(block_type=BlockType.PARAGRAPH, content=text))
            plain_parts.append(text)

        elif tag == "tbl":
            table = Table(child, doc)
            rows = [[cell.text.replace("\n", " ").strip() for cell in row.cells] for row in table.rows]
            if not rows:
                continue
            md = _rows_to_markdown(rows)
            blocks.append(TextBlock(block_type=BlockType.TABLE, content=md))
            plain_parts.append(md)
            table_count += 1

    # Embedded images
    try:
        figure_count = sum(
            1 for rel in doc.part.rels.values() if "image" in rel.reltype
        )
    except AttributeError:
        figure_count = 0

    return DocumentIntelligenceResult(
        blocks=blocks,
        plain_text="\n".join(plain_parts),
        page_count=max(1, len(plain_parts) // 40),  # rough estimate; DOCX has no pages
        file_type="docx",
        parse_route=route,
        table_count=table_count,
        figure_count=figure_count,
        equation_count=equation_count,
        metadata={"block_count": len(blocks), "paragraph_count": len(plain_parts)},
    )


def _rows_to_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    padded = [r + [""] * (width - len(r)) for r in rows]
    header, *body = padded
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)
