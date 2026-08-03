"""
Docling parser adapter.

Docling is the primary parser: it produces a proper document model with reading
order, real table structure, heading hierarchy and equation handling — all of
which the heuristic PyMuPDF path can only approximate from font sizes.

It is an optional dependency. If the import fails or conversion errors out, the
router falls back to the built-in parsers, so the pipeline never depends on it
being installed.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path

from app.config import settings
from app.models.enums import BlockType, ParseRoute
from app.models.schemas import DocumentIntelligenceResult, TextBlock

logger = logging.getLogger("gyantra.parser.docling")

# Resolved once — importing docling pulls in torch and is slow.
_CONVERTER = None
_IMPORT_FAILED: str | None = None


class DoclingUnavailable(RuntimeError):
    """Docling is not installed, could not initialise, or ran out of resources."""


def _is_resource_error(exc: Exception) -> bool:
    """True when a docling failure is a memory/resource problem, not a bug.

    Docling's layout and table models need roughly 1-2 GB of headroom. On a
    machine that does not have it, conversion dies with std::bad_alloc from the
    native layer. That is a capacity signal, not a defect: the caller should
    fall back to the built-in parser and say so plainly.
    """
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(
        marker in text
        for marker in (
            "bad_alloc",
            "out of memory",
            "outofmemory",
            "cannot allocate",
            "memoryerror",
            "insufficient memory",
        )
    )


def available_memory_mb() -> float | None:
    """Free physical memory in MB, or None if it cannot be determined."""
    try:
        import ctypes

        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        if hasattr(ctypes, "windll"):
            status = MemoryStatusEx()
            status.dwLength = ctypes.sizeof(MemoryStatusEx)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return status.ullAvailPhys / (1024 * 1024)

        # POSIX
        page_size = os.sysconf("SC_PAGE_SIZE")
        avail_pages = os.sysconf("SC_AVPHYS_PAGES")
        return (page_size * avail_pages) / (1024 * 1024)
    except (AttributeError, ValueError, OSError):
        return None


def is_available() -> bool:
    """True when docling can actually be used.

    Checks both the install and available memory: on a machine that cannot
    allocate enough for the layout models, calling it would just fail mid-parse
    and waste the job's time.
    """
    if not settings.docling_enabled:
        return False

    free = available_memory_mb()
    if free is not None and free < settings.docling_min_memory_mb:
        logger.warning(
            "docling skipped: only %.0f MB free (needs >= %d MB)",
            free, settings.docling_min_memory_mb,
        )
        return False

    try:
        import docling  # noqa: F401
        return True
    except ImportError:
        return False


def _get_converter():
    """Build (once) a DocumentConverter tuned for educational PDFs."""
    global _CONVERTER, _IMPORT_FAILED

    if _CONVERTER is not None:
        return _CONVERTER
    if _IMPORT_FAILED:
        raise DoclingUnavailable(_IMPORT_FAILED)

    # Windows blocks symlink creation for non-elevated users, and the
    # huggingface cache uses symlinks by default. Without this, docling's first
    # model download dies with WinError 1314. Must be set before any hf import.
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        pipeline_options = PdfPipelineOptions()
        # Table structure is the main reason to prefer docling; keep it on.
        pipeline_options.do_table_structure = True
        pipeline_options.table_structure_options.do_cell_matching = True
        # Docling's OCR stage loads a second heavyweight model and is a major
        # memory cost — it has been observed to die with std::bad_alloc on
        # modest machines. Gyantra has a dedicated OCR fallback path, so let
        # docling handle text and tables and leave OCR to that path.
        pipeline_options.do_ocr = False

        # Keep only the models this doc needs loaded, so docling can run in
        # parallel with the rest of the pipeline without exhausting memory.
        from docling.datamodel.pipeline_options import AcceleratorOptions
        from docling.utils.accelerator_utils import AcceleratorDevice

        accelerator_options = AcceleratorOptions(
            num_threads=settings.docling_threads, device=AcceleratorDevice.AUTO
        )
        pipeline_options.accelerator_options = accelerator_options

        _CONVERTER = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
        logger.info("docling converter initialised (ocr=%s)", False)
        return _CONVERTER

    except ImportError as exc:
        _IMPORT_FAILED = f"docling is not installed: {exc}"
        raise DoclingUnavailable(_IMPORT_FAILED) from exc
    except Exception as exc:  # noqa: BLE001 - any init failure means unusable
        _IMPORT_FAILED = f"docling failed to initialise: {exc}"
        raise DoclingUnavailable(_IMPORT_FAILED) from exc


def warmup() -> tuple[bool, str]:
    """Initialise docling and pull its models ahead of first use.

    Called at API startup. Docling downloads several hundred MB of layout and
    table models on first run; doing that lazily inside a job makes the first
    upload look like a four-minute hang. Returns (ok, detail).
    """
    if not settings.docling_enabled:
        return False, "disabled by config"
    if not is_available():
        return False, "not installed"

    try:
        started = time.monotonic()
        _get_converter()
        return True, f"ready in {time.monotonic() - started:.1f}s"
    except DoclingUnavailable as exc:
        return False, str(exc)


# Docling label → our block type. Labels vary slightly across versions, so
# unknown labels degrade to PARAGRAPH rather than being dropped.
_LABEL_MAP = {
    "title": (BlockType.HEADING, 1),
    "section_header": (BlockType.HEADING, 2),
    "subtitle": (BlockType.HEADING, 2),
    "paragraph": (BlockType.PARAGRAPH, 0),
    "text": (BlockType.PARAGRAPH, 0),
    "list_item": (BlockType.LIST, 0),
    "caption": (BlockType.CAPTION, 0),
    "formula": (BlockType.EQUATION, 0),
    "equation": (BlockType.EQUATION, 0),
    "code": (BlockType.PARAGRAPH, 0),
    "footnote": (BlockType.PARAGRAPH, 0),
}


def _label_of(item) -> str:
    label = getattr(item, "label", None)
    if label is None:
        return ""
    return str(getattr(label, "value", label)).lower()


def _page_of(item) -> int | None:
    """First page number a docling item appears on."""
    prov = getattr(item, "prov", None) or []
    for p in prov:
        page = getattr(p, "page_no", None)
        if page:
            return int(page)
    return None


# "8.1", "2.3.4", "IV.", "Chapter 8" — numbering is the most reliable depth
# signal in textbook content.
_NUMBERED_HEADING = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*[.):]?\s+\S")
_CHAPTER_HEADING = re.compile(
    r"^\s*(chapter|unit|part|module|lesson)\b", re.IGNORECASE
)


def _heading_level(item, label: str, text: str) -> int:
    """Heading depth for a docling item.

    Docling labels headings but assigns every `section_header` level 1, which
    would flatten a chapter's structure and break heading-aligned chunking.
    Section numbering is a far better signal, so it takes priority:
      "Chapter 8"  -> 1
      "8.1 ..."    -> 2   (one dot  = second level)
      "8.1.2 ..."  -> 3
    Docling's own level is used only when there is no numbering to read.
    """
    if _CHAPTER_HEADING.match(text):
        return 1

    match = _NUMBERED_HEADING.match(text)
    if match:
        return min(match.group(1).count(".") + 1, 6)

    if label == "title":
        return 1

    level = getattr(item, "level", None)
    if isinstance(level, int) and level > 1:
        return min(level, 6)

    # An unnumbered section header sits one below the document title.
    return 2


def _table_to_markdown(table_item, doc) -> str:
    """Render a docling table as markdown so the LLM sees its structure."""
    # Newer versions expose export_to_markdown directly on the item.
    for attempt in (
        lambda: table_item.export_to_markdown(doc=doc),
        lambda: table_item.export_to_markdown(),
    ):
        try:
            md = attempt()
            if md and md.strip():
                return md.strip()
        except (AttributeError, TypeError, ValueError):
            continue

    # Fall back to walking the cell grid.
    try:
        data = table_item.data
        grid = getattr(data, "grid", None)
        if not grid:
            return ""
        rows = [
            [str(getattr(cell, "text", "") or "").replace("\n", " ").strip() for cell in row]
            for row in grid
        ]
        if not rows:
            return ""
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        header, *body = rows
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(["---"] * width) + " |",
        ]
        lines += ["| " + " | ".join(r) + " |" for r in body]
        return "\n".join(lines)
    except (AttributeError, TypeError, ValueError) as exc:
        logger.debug("table export failed: %s", exc)
        return ""


def parse_with_docling(
    file_path: str,
    route: ParseRoute = ParseRoute.LAYOUT_AWARE,
) -> DocumentIntelligenceResult:
    """Parse a document with Docling into our block model.

    Raises DoclingUnavailable if docling cannot be used, so the router can fall
    back cleanly.
    """
    converter = _get_converter()
    started = time.monotonic()

    try:
        result = converter.convert(file_path)
    except Exception as exc:  # noqa: BLE001 - conversion failure must be catchable
        if _is_resource_error(exc):
            free = available_memory_mb()
            detail = f"{free:.0f} MB free" if free is not None else "memory unknown"
            raise DoclingUnavailable(
                f"docling ran out of memory ({detail}); "
                f"falling back to the built-in parser"
            ) from exc
        raise DoclingUnavailable(f"docling conversion failed: {exc}") from exc

    doc = result.document
    blocks: list[TextBlock] = []
    plain_parts: list[str] = []
    table_count = figure_count = equation_count = 0
    pages_seen: set[int] = set()

    # iterate_items walks the document in reading order, which is the main
    # advantage over font-size heuristics on multi-column layouts.
    try:
        items = list(doc.iterate_items())
    except AttributeError:
        items = [(item, 0) for item in getattr(doc, "texts", [])]

    for entry in items:
        item = entry[0] if isinstance(entry, tuple) else entry
        label = _label_of(item)
        page = _page_of(item)
        if page:
            pages_seen.add(page)

        cls_name = type(item).__name__

        # --- tables ---
        if "Table" in cls_name or label == "table":
            md = _table_to_markdown(item, doc)
            if md:
                blocks.append(
                    TextBlock(block_type=BlockType.TABLE, content=md, page=page)
                )
                plain_parts.append(md)
                table_count += 1
            continue

        # --- figures / pictures ---
        if "Picture" in cls_name or label in ("picture", "figure", "image"):
            figure_count += 1
            caption = ""
            try:
                caption = (item.caption_text(doc) or "").strip()
            except (AttributeError, TypeError):
                pass
            blocks.append(
                TextBlock(
                    block_type=BlockType.FIGURE,
                    content=caption or f"[Figure on page {page or '?'}]",
                    caption=caption or None,
                    page=page,
                )
            )
            if caption:
                plain_parts.append(caption)
            continue

        # --- text-bearing items ---
        text = (getattr(item, "text", "") or "").strip()
        if not text:
            continue

        block_type, default_level = _LABEL_MAP.get(label, (BlockType.PARAGRAPH, 0))
        level = (
            _heading_level(item, label, text)
            if block_type == BlockType.HEADING
            else 0
        )

        if block_type == BlockType.EQUATION:
            equation_count += 1

        blocks.append(
            TextBlock(
                block_type=block_type,
                content=text,
                level=level,
                page=page,
            )
        )
        plain_parts.append(text)

    # Prefer docling's own markdown for plain_text — it preserves structure
    # better than our concatenation and is what grounding checks read.
    try:
        markdown = doc.export_to_markdown()
    except (AttributeError, TypeError, ValueError):
        markdown = "\n".join(plain_parts)

    page_count = 0
    try:
        page_count = len(doc.pages)
    except (AttributeError, TypeError):
        page_count = max(pages_seen) if pages_seen else 0

    elapsed = time.monotonic() - started
    logger.info(
        "docling parsed %s in %.1fs: %s blocks, %s pages, %s tables, %s figures",
        Path(file_path).name, elapsed, len(blocks), page_count, table_count, figure_count,
    )

    if not blocks:
        raise DoclingUnavailable("docling returned no content blocks")

    return DocumentIntelligenceResult(
        blocks=blocks,
        plain_text=markdown or "\n".join(plain_parts),
        page_count=page_count or 1,
        file_type=Path(file_path).suffix.lstrip(".").lower(),
        parse_route=route,
        table_count=table_count,
        figure_count=figure_count,
        equation_count=equation_count,
        metadata={
            "parser": "docling",
            "block_count": len(blocks),
            "parse_seconds": round(elapsed, 2),
        },
    )
