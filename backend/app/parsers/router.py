"""
Cost-aware parser routing (FAQ Q7).

Routing inputs, in priority order:
  1. File extension          — hard constraint on which parser can run at all.
  2. User's document hint    — the lightweight clarification step.
  3. Automatic probe results — page count, text density, images, equations.

The router always picks the *cheapest viable* path and escalates only when the
probe shows it's necessary.  OCR is the most expensive path and is entered only
when the document genuinely has no extractable text.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import settings
from app.models.enums import DocumentHint, ParseRoute
from app.models.schemas import DocumentIntelligenceResult
from app.parsers import (
    docling_parser,
    docx_parser,
    ocr_fallback,
    pdf_parser,
    pptx_parser,
    text_parser,
)

logger = logging.getLogger("gyantra.parser.router")

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".txt", ".md", ".markdown",
}

# What each user hint maps to when the file is a PDF.
_HINT_ROUTE = {
    DocumentHint.MOSTLY_TEXT: ParseRoute.LIGHTWEIGHT_TEXT,
    DocumentHint.TEXT_WITH_TABLES: ParseRoute.STRUCTURED_TABLES,
    DocumentHint.TEXT_WITH_DIAGRAMS: ParseRoute.LAYOUT_AWARE,
    DocumentHint.TEXT_WITH_EQUATIONS: ParseRoute.EQUATION_PRESERVING,
    DocumentHint.SCANNED_PDF: ParseRoute.OCR,
}


class UnsupportedFileError(ValueError):
    """Raised for file types we cannot parse."""


def decide_route(
    file_path: str,
    hint: DocumentHint = DocumentHint.NOT_SURE,
) -> tuple[ParseRoute, dict]:
    """Choose a parse route.  Returns (route, probe_info)."""
    ext = Path(file_path).suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileError(
            f"Unsupported file type '{ext}'. Supported: "
            + ", ".join(sorted(SUPPORTED_EXTENSIONS))
        )

    # Non-PDF formats have exactly one sensible parser; no probing needed.
    if ext in (".txt", ".md", ".markdown"):
        return ParseRoute.LIGHTWEIGHT_TEXT, {"reason": "plain text file"}
    if ext in (".docx", ".doc"):
        route = (
            ParseRoute.STRUCTURED_TABLES
            if hint == DocumentHint.TEXT_WITH_TABLES
            else ParseRoute.LIGHTWEIGHT_TEXT
        )
        return route, {"reason": "docx parser handles structure natively"}
    if ext in (".pptx", ".ppt"):
        return ParseRoute.LAYOUT_AWARE, {"reason": "slide decks are layout-driven"}

    # --- PDF: probe before deciding ---
    probe = pdf_parser.quick_probe(file_path)

    # A genuinely scanned PDF must go to OCR regardless of the hint.
    if probe["is_scanned"]:
        if not settings.ocr_enabled:
            logger.warning("scanned PDF detected but OCR is disabled")
            return ParseRoute.LIGHTWEIGHT_TEXT, {
                **probe,
                "reason": "scanned, but OCR disabled — expect sparse text",
            }
        return ParseRoute.OCR, {**probe, "reason": "text density below threshold"}

    # Respect an explicit user hint when the document is not scanned.
    if hint in _HINT_ROUTE and hint != DocumentHint.SCANNED_PDF:
        return _HINT_ROUTE[hint], {**probe, "reason": f"user hint: {hint.value}"}

    if hint == DocumentHint.SCANNED_PDF:
        # User said scanned but probe found text — trust the probe, it's cheaper.
        return ParseRoute.LIGHTWEIGHT_TEXT, {
            **probe,
            "reason": "user said scanned but text layer exists — using text path",
        }

    # NOT_SURE: derive from the probe.
    if probe["equation_hits"] > 12:
        return ParseRoute.EQUATION_PRESERVING, {**probe, "reason": "equation density"}
    if probe["table_hits"] > 0:
        return ParseRoute.STRUCTURED_TABLES, {**probe, "reason": "tables detected"}
    if probe["image_count"] > 3:
        return ParseRoute.LAYOUT_AWARE, {**probe, "reason": "multiple figures"}
    return ParseRoute.LIGHTWEIGHT_TEXT, {**probe, "reason": "text-dominant document"}


#: Formats docling handles well. Plain text and markdown are already structured,
#: so sending them through docling's ML pipeline buys nothing.
_DOCLING_FORMATS = {".pdf", ".docx", ".pptx", ".doc", ".ppt"}


def parse_document(
    file_path: str,
    hint: DocumentHint = DocumentHint.NOT_SURE,
    original_name: str | None = None,
) -> DocumentIntelligenceResult:
    """Route and parse.

    Docling is tried first for rich formats; the built-in parsers handle plain
    text and act as the fallback whenever docling is unavailable or fails.
    """
    route, probe = decide_route(file_path, hint)
    ext = Path(file_path).suffix.lower()
    logger.info(
        "routing %s -> %s (%s)", Path(file_path).name, route.value, probe.get("reason")
    )

    result: DocumentIntelligenceResult | None = None
    fallback_reason = ""

    # --- primary: docling ---
    if ext in _DOCLING_FORMATS and route != ParseRoute.OCR:
        if docling_parser.is_available():
            try:
                result = docling_parser.parse_with_docling(file_path, route)
            except docling_parser.DoclingUnavailable as exc:
                fallback_reason = str(exc)
                logger.warning("docling unusable, falling back: %s", exc)
            except Exception as exc:  # noqa: BLE001 - never let the parser kill the job
                fallback_reason = f"docling raised {type(exc).__name__}: {exc}"
                logger.warning("docling failed unexpectedly, falling back: %s", exc)
        else:
            fallback_reason = (
                "docling not installed"
                if settings.docling_enabled
                else "docling disabled by config"
            )
            logger.info("using built-in parser (%s)", fallback_reason)

    # --- fallback: built-in parsers ---
    if result is None:
        result = _parse_builtin(file_path, ext, route)
        if fallback_reason:
            result.metadata["docling_fallback_reason"] = fallback_reason

    result.file_name = original_name or Path(file_path).name
    result.detected_hint = hint
    result.metadata.update({"routing": probe, "route_chosen": route.value})
    result.metadata.setdefault("parser", "builtin")
    result.language_hint = _detect_language(result.plain_text)
    return result


def _parse_builtin(
    file_path: str, ext: str, route: ParseRoute
) -> DocumentIntelligenceResult:
    """The original parser set, used for plain text and as docling's fallback."""
    if ext == ".pdf":
        result = (
            ocr_fallback.parse_via_ocr(file_path)
            if route == ParseRoute.OCR
            else pdf_parser.parse_pdf(file_path, route)
        )
        # Escalation: a text path that produced almost nothing means the probe
        # was wrong. Retry with OCR once.
        if (
            route != ParseRoute.OCR
            and settings.ocr_enabled
            and len(result.plain_text.strip()) < 200
        ):
            logger.warning("text path yielded %s chars — escalating to OCR", len(result.plain_text))
            result = ocr_fallback.parse_via_ocr(file_path)
    elif ext in (".docx", ".doc"):
        result = docx_parser.parse_docx(file_path, route)
    elif ext in (".pptx", ".ppt"):
        result = pptx_parser.parse_pptx(file_path, route)
    else:
        result = text_parser.parse_text(file_path)

    return result


def _detect_language(text: str) -> str:
    """Very cheap script-based language hint.

    Full language detection isn't worth a dependency here; we only need enough
    to tell the classifier which script it's looking at.
    """
    if not text:
        return "en"
    sample = text[:4000]
    devanagari = sum(1 for c in sample if "ऀ" <= c <= "ॿ")
    if devanagari > len(sample) * 0.15:
        return "hi"
    bengali = sum(1 for c in sample if "ঀ" <= c <= "৿")
    if bengali > len(sample) * 0.15:
        return "bn"
    tamil = sum(1 for c in sample if "஀" <= c <= "௿")
    if tamil > len(sample) * 0.15:
        return "ta"
    telugu = sum(1 for c in sample if "ఀ" <= c <= "౿")
    if telugu > len(sample) * 0.15:
        return "te"
    return "en"
