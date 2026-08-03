"""Plain text and Markdown parsing — heading detection via markdown syntax."""

from __future__ import annotations

import re
from pathlib import Path

from app.models.enums import BlockType, ParseRoute
from app.models.schemas import DocumentIntelligenceResult, TextBlock

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_MD_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_SETEXT_H1 = re.compile(r"^={3,}\s*$")
_SETEXT_H2 = re.compile(r"^-{3,}\s*$")
_NUMBERED_HEADING = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+([A-Z][^.!?]{3,80})$")
_LIST_ITEM = re.compile(r"^\s*[-*+•]\s+|^\s*\d+[.)]\s+")


def parse_text(file_path: str) -> DocumentIntelligenceResult:
    raw = Path(file_path).read_text(encoding="utf-8", errors="replace")
    lines = raw.split("\n")

    blocks: list[TextBlock] = []
    table_count = 0
    para_buffer: list[str] = []
    table_buffer: list[str] = []

    def flush_para() -> None:
        if para_buffer:
            blocks.append(
                TextBlock(
                    block_type=BlockType.PARAGRAPH,
                    content=" ".join(para_buffer).strip(),
                )
            )
            para_buffer.clear()

    def flush_table() -> None:
        nonlocal table_count
        if table_buffer:
            blocks.append(
                TextBlock(block_type=BlockType.TABLE, content="\n".join(table_buffer))
            )
            table_buffer.clear()
            table_count += 1

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Markdown table
        if _MD_TABLE_ROW.match(line):
            flush_para()
            table_buffer.append(stripped)
            continue
        flush_table()

        if not stripped:
            flush_para()
            continue

        # ATX heading (# Title)
        m = _MD_HEADING.match(stripped)
        if m:
            flush_para()
            blocks.append(
                TextBlock(
                    block_type=BlockType.HEADING,
                    content=m.group(2).strip(),
                    level=len(m.group(1)),
                )
            )
            continue

        # Setext heading (Title\n=====)
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if _SETEXT_H1.match(next_line):
            flush_para()
            blocks.append(TextBlock(block_type=BlockType.HEADING, content=stripped, level=1))
            continue
        if _SETEXT_H2.match(next_line) and len(stripped) < 100:
            flush_para()
            blocks.append(TextBlock(block_type=BlockType.HEADING, content=stripped, level=2))
            continue
        if _SETEXT_H1.match(stripped) or _SETEXT_H2.match(stripped):
            continue  # underline consumed above

        # Numbered section heading (1.2 Some Title)
        nm = _NUMBERED_HEADING.match(stripped)
        if nm and len(stripped) < 90:
            flush_para()
            depth = nm.group(1).count(".") + 1
            blocks.append(
                TextBlock(block_type=BlockType.HEADING, content=stripped, level=depth)
            )
            continue

        # List item
        if _LIST_ITEM.match(line):
            flush_para()
            blocks.append(TextBlock(block_type=BlockType.LIST, content=stripped))
            continue

        para_buffer.append(stripped)

    flush_para()
    flush_table()

    return DocumentIntelligenceResult(
        blocks=blocks,
        plain_text=raw,
        page_count=max(1, len(raw) // 3000),
        file_type=Path(file_path).suffix.lstrip(".") or "txt",
        parse_route=ParseRoute.LIGHTWEIGHT_TEXT,
        table_count=table_count,
        figure_count=0,
        equation_count=0,
        metadata={"line_count": len(lines), "block_count": len(blocks)},
    )
