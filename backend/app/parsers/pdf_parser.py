"""
PDF parsing with PyMuPDF.

Extracts text while preserving structure: headings (via font-size heuristics),
paragraphs, tables, figure references, and equations.  Falls back to OCR when
the page yields too little extractable text.
"""

from __future__ import annotations

import logging
import re
import statistics

from app.config import settings
from app.models.enums import BlockType, ParseRoute
from app.models.schemas import DocumentIntelligenceResult, TextBlock

logger = logging.getLogger("gyantra.parser.pdf")

# Patterns that suggest a line is a mathematical expression rather than prose.
_EQUATION_HINTS = re.compile(
    r"(\\frac|\\sum|\\int|\\sqrt|[=≈≤≥±×÷∑∫√]|\^\d|_\{|\b\d+\s*/\s*\d+\b)"
)
_FIGURE_CAPTION = re.compile(
    r"^\s*(fig(?:ure)?\.?|table|chart|diagram|map|plate)\s*[\d.]+\s*[:.\-–]",
    re.IGNORECASE,
)


def _looks_like_equation(text: str) -> bool:
    """Heuristic: short line, math symbols, low alphabetic density."""
    stripped = text.strip()
    if not stripped or len(stripped) > 200:
        return False
    if not _EQUATION_HINTS.search(stripped):
        return False
    alpha = sum(c.isalpha() for c in stripped)
    return alpha / max(len(stripped), 1) < 0.6


def _classify_span_sizes(pages_spans: list[list[dict]]) -> tuple[float, list[float]]:
    """Return (body_size, heading_size_thresholds) from font size distribution."""
    sizes: list[float] = []
    for spans in pages_spans:
        for s in spans:
            if s.get("text", "").strip():
                sizes.append(round(s.get("size", 0), 1))
    if not sizes:
        return 10.0, []
    # The most common size is almost always body text.
    body = statistics.mode(sizes)
    distinct = sorted({s for s in sizes if s > body + 0.5}, reverse=True)
    return body, distinct[:3]  # up to 3 heading levels


def parse_pdf(
    file_path: str,
    route: ParseRoute = ParseRoute.LIGHTWEIGHT_TEXT,
) -> DocumentIntelligenceResult:
    """Parse a PDF into structured blocks.

    `route` tunes how much work we do:
      LIGHTWEIGHT_TEXT     — text + headings only (cheapest)
      STRUCTURED_TABLES    — also run table detection
      LAYOUT_AWARE         — also record figure blocks and bboxes
      EQUATION_PRESERVING  — also isolate equation lines
      OCR                  — handled by ocr_parser, not here
    """
    import fitz  # PyMuPDF

    doc = fitz.open(file_path)
    blocks: list[TextBlock] = []
    plain_parts: list[str] = []
    pages_spans: list[list[dict]] = []
    table_count = figure_count = equation_count = 0

    want_tables = route in (ParseRoute.STRUCTURED_TABLES, ParseRoute.LAYOUT_AWARE)
    want_figures = route in (ParseRoute.LAYOUT_AWARE, ParseRoute.STRUCTURED_TABLES)
    want_equations = route == ParseRoute.EQUATION_PRESERVING

    # First pass: collect spans so we can learn the font-size distribution.
    page_data = []
    for page_idx, page in enumerate(doc):
        d = page.get_text("dict")
        spans = [
            span
            for block in d.get("blocks", [])
            for line in block.get("lines", [])
            for span in line.get("spans", [])
        ]
        pages_spans.append(spans)
        page_data.append((page_idx, page, d))

    body_size, heading_sizes = _classify_span_sizes(pages_spans)
    logger.info("pdf font analysis: body=%.1f headings=%s", body_size, heading_sizes)

    def heading_level(size: float) -> int:
        """Map a font size to a heading depth (1 = largest)."""
        for i, hs in enumerate(heading_sizes):
            if size >= hs - 0.3:
                return i + 1
        return 0

    for page_idx, page, d in page_data:
        page_no = page_idx + 1

        # --- tables (PyMuPDF >= 1.23) ---
        table_bboxes = []
        if want_tables:
            try:
                for tbl in page.find_tables().tables:
                    rows = tbl.extract()
                    if not rows or len(rows) < 2:
                        continue
                    table_bboxes.append(tbl.bbox)
                    md = _rows_to_markdown(rows)
                    blocks.append(
                        TextBlock(
                            block_type=BlockType.TABLE,
                            content=md,
                            page=page_no,
                            bbox=list(tbl.bbox),
                        )
                    )
                    plain_parts.append(md)
                    table_count += 1
            except (AttributeError, RuntimeError, ValueError) as exc:
                logger.debug("table detection failed p%s: %s", page_no, exc)

        # --- figures ---
        if want_figures:
            try:
                images = page.get_images(full=True)
                for img in images:
                    figure_count += 1
                    blocks.append(
                        TextBlock(
                            block_type=BlockType.FIGURE,
                            content=f"[Figure on page {page_no}]",
                            page=page_no,
                        )
                    )
            except (AttributeError, RuntimeError) as exc:
                logger.debug("image listing failed p%s: %s", page_no, exc)

        # --- text blocks ---
        for blk in d.get("blocks", []):
            if blk.get("type") != 0:  # 0 = text
                continue
            bbox = blk.get("bbox")
            # Skip text that lives inside a detected table (already captured).
            if table_bboxes and bbox and _inside_any(bbox, table_bboxes):
                continue

            for line in blk.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                text = "".join(s.get("text", "") for s in spans).strip()
                if not text:
                    continue

                max_size = max(s.get("size", body_size) for s in spans)
                is_bold = any("bold" in (s.get("font", "").lower()) for s in spans)
                lvl = heading_level(max_size)

                if _FIGURE_CAPTION.match(text):
                    btype, level = BlockType.CAPTION, 0
                elif want_equations and _looks_like_equation(text):
                    btype, level = BlockType.EQUATION, 0
                    equation_count += 1
                elif lvl > 0 and len(text) < 160:
                    btype, level = BlockType.HEADING, lvl
                elif is_bold and len(text) < 90 and text[-1:] not in ".,;":
                    btype, level = BlockType.HEADING, len(heading_sizes) + 1
                else:
                    btype, level = BlockType.PARAGRAPH, 0
                    if not want_equations and _looks_like_equation(text):
                        equation_count += 1

                blocks.append(
                    TextBlock(
                        block_type=btype,
                        content=text,
                        level=level,
                        page=page_no,
                        bbox=list(bbox) if bbox else None,
                    )
                )
                plain_parts.append(text)

    page_count = doc.page_count
    doc.close()

    plain_text = "\n".join(plain_parts)
    merged = _merge_paragraph_runs(blocks)

    return DocumentIntelligenceResult(
        blocks=merged,
        plain_text=plain_text,
        page_count=page_count,
        file_type="pdf",
        parse_route=route,
        table_count=table_count,
        figure_count=figure_count,
        equation_count=equation_count,
        metadata={
            "body_font_size": body_size,
            "heading_font_sizes": heading_sizes,
            "block_count": len(merged),
        },
    )


def _inside_any(bbox: list[float] | tuple, boxes: list) -> bool:
    """True if bbox's centre falls inside any of the given boxes."""
    cx = (bbox[0] + bbox[2]) / 2
    cy = (bbox[1] + bbox[3]) / 2
    for b in boxes:
        if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
            return True
    return False


def _rows_to_markdown(rows: list[list]) -> str:
    """Render an extracted table as markdown so the LLM can read its structure."""
    clean = [[(c or "").replace("\n", " ").strip() for c in row] for row in rows]
    if not clean:
        return ""
    width = max(len(r) for r in clean)
    clean = [r + [""] * (width - len(r)) for r in clean]
    header, *body = clean
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def _merge_paragraph_runs(blocks: list[TextBlock]) -> list[TextBlock]:
    """Join consecutive paragraph lines into real paragraphs.

    PDF extraction yields one block per visual line; merging them back gives the
    LLM coherent prose instead of fragments.
    """
    merged: list[TextBlock] = []
    for blk in blocks:
        if (
            blk.block_type == BlockType.PARAGRAPH
            and merged
            and merged[-1].block_type == BlockType.PARAGRAPH
            and merged[-1].page == blk.page
        ):
            prev = merged[-1]
            # A line ending mid-sentence continues the same paragraph.
            joiner = " " if prev.content[-1:] not in ".!?:;" else "\n"
            prev.content = f"{prev.content}{joiner}{blk.content}"
        else:
            merged.append(blk)
    return merged


def quick_probe(file_path: str) -> dict:
    """Cheap inspection used by the router before committing to a strategy.

    Returns page count, extractable text density, image count and equation hints
    without doing a full structured parse.
    """
    import fitz

    doc = fitz.open(file_path)
    page_count = doc.page_count
    sample_pages = min(page_count, 5)
    text_chars = 0
    image_count = 0
    equation_hits = 0
    table_hits = 0

    for i in range(sample_pages):
        page = doc[i]
        text = page.get_text("text")
        text_chars += len(text.strip())
        image_count += len(page.get_images(full=True))
        equation_hits += len(_EQUATION_HINTS.findall(text))
        try:
            table_hits += len(page.find_tables().tables)
        except (AttributeError, RuntimeError, ValueError):
            pass

    doc.close()
    chars_per_page = text_chars / max(sample_pages, 1)
    return {
        "page_count": page_count,
        "chars_per_page": chars_per_page,
        "is_scanned": chars_per_page < settings.scanned_text_threshold,
        "image_count": image_count,
        "equation_hits": equation_hits,
        "table_hits": table_hits,
    }
