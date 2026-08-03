"""OCR fallback for scanned PDFs and images."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from app.config import settings
from app.models.enums import BlockType, ParseRoute
from app.models.schemas import DocumentIntelligenceResult, TextBlock

logger = logging.getLogger("gyantra.parser.ocr")


def parse_via_ocr(file_path: str) -> DocumentIntelligenceResult:
    """Run Tesseract OCR on each page of a scanned PDF.

    Falls back to a plain "[scanned - OCR unavailable]" block if tesseract is not
    installed, so the pipeline can at least report the problem to the user.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(file_path)
    blocks: list[TextBlock] = []
    plain_parts: list[str] = []
    page_count = doc.page_count
    succeeded = False

    # Check if tesseract is callable once, not once per page.
    try:
        import subprocess as sp
        sp.run(["tesseract", "--version"], capture_output=True, timeout=5)
        tesseract_ok = True
    except (FileNotFoundError, OSError, sp.TimeoutExpired):
        tesseract_ok = False
        logger.warning("tesseract not found. OCR will return raw image references.")

    for idx, page in enumerate(doc):
        page_no = idx + 1
        if page_no > settings.ocr_max_pages:
            blocks.append(
                TextBlock(
                    block_type=BlockType.PARAGRAPH,
                    content=f"[Page {page_no} skipped — exceeds OCR max pages]",
                    page=page_no,
                )
            )
            plain_parts.append(f"[Page {page_no} skipped]")
            continue

        if not tesseract_ok:
            blocks.append(
                TextBlock(
                    block_type=BlockType.FIGURE,
                    content=f"[Scanned page {page_no} — OCR unavailable. Install tesseract-ocr.]",
                    page=page_no,
                )
            )
            continue

        # Render page to image, then OCR.
        try:
            pix = page.get_pixmap(dpi=200)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                pix.save(tmp.name)
                tmp_path = tmp.name

            import subprocess as sp
            result = sp.run(
                ["tesseract", tmp_path, "stdout", "-l", settings.ocr_language],
                capture_output=True, text=True, timeout=60,
            )
            Path(tmp_path).unlink(missing_ok=True)

            text = result.stdout.strip()
            if text:
                succeeded = True
                blocks.append(
                    TextBlock(block_type=BlockType.PARAGRAPH, content=text, page=page_no)
                )
                plain_parts.append(text)
            else:
                blocks.append(
                    TextBlock(
                        block_type=BlockType.FIGURE,
                        content=f"[Scanned page {page_no} — OCR produced no text]",
                        page=page_no,
                    )
                )
        except (RuntimeError, OSError, sp.TimeoutExpired) as exc:
            logger.warning("OCR failed on page %s: %s", page_no, exc)
            blocks.append(
                TextBlock(
                    block_type=BlockType.PARAGRAPH,
                    content=f"[OCR error on page {page_no}]",
                    page=page_no,
                )
            )

    doc.close()

    return DocumentIntelligenceResult(
        blocks=blocks,
        plain_text="\n".join(plain_parts),
        page_count=page_count,
        file_type="pdf",
        parse_route=ParseRoute.OCR,
        ocr_used=True,
        table_count=0,
        figure_count=0,
        equation_count=0,
        metadata={"ocr_success": succeeded},
    )
