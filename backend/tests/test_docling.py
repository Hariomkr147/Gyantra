"""
Docling parser tests.

The parse-quality tests are skipped when docling is not installed; the fallback
tests always run, because the fallback path is what protects the pipeline when
docling is missing or broken.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models.enums import BlockType, DocumentHint, ParseRoute
from app.parsers import docling_parser, router


@pytest.fixture
def structured_pdf(tmp_path: Path) -> Path:
    """A small PDF with a chapter title, numbered sections and a formula."""
    fitz = pytest.importorskip("fitz")

    doc = fitz.open()
    page = doc.new_page()
    y = 60

    def write(text, size, bold=False, gap=None):
        nonlocal y
        page.insert_text(
            (60, y), text, fontsize=size, fontname="hebo" if bold else "helv"
        )
        y += gap if gap else size + 8

    write("Chapter 8: Force and Laws of Motion", 20, True, 34)
    write("8.1 Balanced and Unbalanced Forces", 14, True, 26)
    write("A force can be a push or a pull acting on a body at rest.", 10)
    write("Balanced forces cancel one another out completely.", 10, gap=24)
    write("8.2 Second Law of Motion", 14, True, 26)
    write("The rate of change of momentum is proportional to the force.", 10)
    write("F = m * a", 11, gap=22)
    write("8.2.1 Worked Example", 12, True, 22)
    write("A force of 5 N on a 2 kg mass produces 2.5 m/s squared.", 10)

    path = tmp_path / "structured.pdf"
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def substantial_pdf(tmp_path: Path) -> Path:
    """A PDF whose sections are long enough to survive stub-merging.

    The chunker deliberately folds negligible sections into a neighbour, so a
    document needs realistic section lengths before per-section chunking is
    observable.
    """
    fitz = pytest.importorskip("fitz")

    doc = fitz.open()
    page = doc.new_page()
    y = 60

    def write(text, size=10, bold=False, gap=None):
        nonlocal y
        page.insert_text(
            (60, y), text, fontsize=size, fontname="hebo" if bold else "helv"
        )
        y += gap if gap else size + 4

    sections = [
        (
            "8.1 Balanced and Unbalanced Forces",
            "Balanced forces cancel one another out and the net force on the "
            "body is zero, so its state of motion does not change.",
        ),
        (
            "8.2 First Law of Motion",
            "An object remains at rest or in uniform motion in a straight line "
            "unless acted upon by an unbalanced force, a property called inertia.",
        ),
        (
            "8.3 Second Law of Motion",
            "The rate of change of momentum of a body is proportional to the "
            "applied unbalanced force and acts in the direction of that force.",
        ),
    ]

    write("Chapter 8: Force and Laws of Motion", 20, True, 34)
    for heading, body in sections:
        write(heading, 14, True, 24)
        for _ in range(12):
            write(body, 10, gap=13)
        y += 8

    path = tmp_path / "substantial.pdf"
    doc.save(str(path))
    doc.close()
    return path


class TestHeadingLevels:
    """Depth derivation. Docling labels headings but flattens their level."""

    def test_chapter_is_level_one(self):
        assert docling_parser._heading_level(None, "title", "Chapter 8: Force") == 1
        assert docling_parser._heading_level(None, "section_header", "Unit 3 Motion") == 1

    def test_numbering_drives_depth(self):
        lvl = docling_parser._heading_level
        assert lvl(None, "section_header", "8.1 Balanced Forces") == 2
        assert lvl(None, "section_header", "8.2.1 Worked Example") == 3
        assert lvl(None, "section_header", "1.2.3.4 Deep Section") == 4

    def test_unnumbered_section_sits_below_title(self):
        assert (
            docling_parser._heading_level(None, "section_header", "Introduction") == 2
        )

    def test_title_label_wins_without_numbering(self):
        assert docling_parser._heading_level(None, "title", "Nationalism in India") == 1

    def test_depth_is_capped(self):
        deep = "1.1.1.1.1.1.1.1 Very Deep"
        assert docling_parser._heading_level(None, "section_header", deep) <= 6


class TestFallback:
    """Docling must never be able to break the pipeline."""

    def test_router_falls_back_when_docling_disabled(self, monkeypatch, structured_pdf):
        from app.config import settings

        monkeypatch.setattr(settings, "docling_enabled", False)
        result = router.parse_document(str(structured_pdf), original_name="s.pdf")

        assert result.metadata["parser"] == "builtin"
        assert "disabled" in result.metadata.get("docling_fallback_reason", "")
        assert result.plain_text.strip()

    def test_router_falls_back_when_docling_raises(self, monkeypatch, structured_pdf):
        """A docling crash degrades to the built-in parser, it does not propagate."""
        from app.config import settings

        monkeypatch.setattr(settings, "docling_enabled", True)
        monkeypatch.setattr(docling_parser, "is_available", lambda: True)

        def boom(*args, **kwargs):
            raise RuntimeError("simulated docling explosion")

        monkeypatch.setattr(docling_parser, "parse_with_docling", boom)

        result = router.parse_document(str(structured_pdf), original_name="s.pdf")

        assert result.metadata["parser"] == "builtin"
        assert "simulated docling explosion" in result.metadata["docling_fallback_reason"]
        assert len(result.blocks) > 0

    def test_unavailable_error_also_falls_back(self, monkeypatch, structured_pdf):
        from app.config import settings

        monkeypatch.setattr(settings, "docling_enabled", True)
        monkeypatch.setattr(docling_parser, "is_available", lambda: True)

        def unavailable(*args, **kwargs):
            raise docling_parser.DoclingUnavailable("models not downloaded")

        monkeypatch.setattr(docling_parser, "parse_with_docling", unavailable)

        result = router.parse_document(str(structured_pdf), original_name="s.pdf")
        assert result.metadata["parser"] == "builtin"
        assert "models not downloaded" in result.metadata["docling_fallback_reason"]

    def test_plain_text_skips_docling_entirely(self, monkeypatch, tmp_path):
        """Markdown is already structured; docling would add cost for nothing."""
        from app.config import settings

        monkeypatch.setattr(settings, "docling_enabled", True)

        called = False

        def spy(*args, **kwargs):
            nonlocal called
            called = True
            raise AssertionError("docling should not run on .md")

        monkeypatch.setattr(docling_parser, "parse_with_docling", spy)

        path = tmp_path / "notes.md"
        path.write_text("# Heading\n\nSome body text here.\n", encoding="utf-8")

        result = router.parse_document(str(path), original_name="notes.md")
        assert not called
        assert result.metadata["parser"] == "builtin"

    def test_ocr_route_bypasses_docling(self, monkeypatch, structured_pdf):
        """A scanned document goes to the dedicated OCR path, not docling."""
        from app.config import settings

        monkeypatch.setattr(settings, "docling_enabled", True)
        monkeypatch.setattr(docling_parser, "is_available", lambda: True)
        monkeypatch.setattr(
            router, "decide_route", lambda *a, **k: (ParseRoute.OCR, {"reason": "test"})
        )

        called = False

        def spy(*args, **kwargs):
            nonlocal called
            called = True
            raise AssertionError("docling should not run for OCR route")

        monkeypatch.setattr(docling_parser, "parse_with_docling", spy)
        monkeypatch.setattr(settings, "ocr_enabled", False)

        router.parse_document(str(structured_pdf), original_name="s.pdf")
        assert not called


def _docling_can_run() -> tuple[bool, str]:
    """Whether a real docling conversion is feasible here.

    Docling's layout models need ~1.5 GB of headroom. On a memory-constrained
    machine the native layer dies with std::bad_alloc, which says nothing about
    the code under test — so these tests skip rather than fail.
    """
    try:
        import docling  # noqa: F401
    except ImportError:
        return False, "docling is not installed"

    free = docling_parser.available_memory_mb()
    if free is not None and free < 1500:
        return False, f"insufficient memory for docling models ({free:.0f} MB free)"
    return True, ""


@pytest.fixture
def require_docling():
    """Skip at call time, not import time.

    Free memory moves while the suite runs, so a decision made at collection can
    be stale by the time the test executes.
    """
    ok, reason = _docling_can_run()
    if not ok:
        pytest.skip(reason)


class TestResourceHandling:
    """Memory pressure must degrade to the fallback, not crash the pipeline."""

    def test_bad_alloc_is_classified_as_resource_error(self):
        assert docling_parser._is_resource_error(RuntimeError("std::bad_alloc"))
        assert docling_parser._is_resource_error(MemoryError("out of memory"))
        assert docling_parser._is_resource_error(
            RuntimeError("Conversion failed. Errors: std::bad_alloc")
        )

    def test_ordinary_error_is_not_a_resource_error(self):
        assert not docling_parser._is_resource_error(ValueError("bad page index"))
        assert not docling_parser._is_resource_error(KeyError("missing label"))

    def test_low_memory_disables_docling(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "docling_enabled", True)
        monkeypatch.setattr(settings, "docling_min_memory_mb", 1500)
        monkeypatch.setattr(docling_parser, "available_memory_mb", lambda: 400.0)

        assert docling_parser.is_available() is False

    def test_sufficient_memory_allows_docling(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "docling_enabled", True)
        monkeypatch.setattr(settings, "docling_min_memory_mb", 1500)
        monkeypatch.setattr(docling_parser, "available_memory_mb", lambda: 4096.0)

        # Only meaningful when docling is actually installed.
        try:
            import docling  # noqa: F401
        except ImportError:
            pytest.skip("docling is not installed")
        assert docling_parser.is_available() is True

    def test_memory_probe_returns_a_number(self):
        free = docling_parser.available_memory_mb()
        assert free is None or free > 0

    def test_oom_during_parse_falls_back(self, monkeypatch, structured_pdf):
        """A mid-parse OOM produces a clear message and the built-in result."""
        from app.config import settings

        monkeypatch.setattr(settings, "docling_enabled", True)
        monkeypatch.setattr(docling_parser, "is_available", lambda: True)

        def oom(*args, **kwargs):
            raise docling_parser.DoclingUnavailable(
                "docling ran out of memory (400 MB free); "
                "falling back to the built-in parser"
            )

        monkeypatch.setattr(docling_parser, "parse_with_docling", oom)

        result = router.parse_document(str(structured_pdf), original_name="s.pdf")
        assert result.metadata["parser"] == "builtin"
        assert "out of memory" in result.metadata["docling_fallback_reason"]
        assert result.plain_text.strip(), "fallback must still produce text"


class TestDoclingParse:
    """Real docling conversion. Slow on first run (downloads models)."""

    def test_extracts_hierarchy_and_reading_order(self, structured_pdf, require_docling):
        result = docling_parser.parse_with_docling(str(structured_pdf))

        assert result.metadata["parser"] == "docling"
        assert result.page_count >= 1
        assert result.plain_text.strip()

        headings = result.heading_blocks
        assert len(headings) >= 3

        levels = {h.content[:12]: h.level for h in headings}
        chapter = next(v for k, v in levels.items() if k.startswith("Chapter"))
        section = next(v for k, v in levels.items() if k.startswith("8.1"))
        assert chapter == 1
        assert section == 2
        assert section > chapter, "section must nest under the chapter"

    def test_router_prefers_docling_for_pdf(self, monkeypatch, structured_pdf, require_docling):
        from app.config import settings

        monkeypatch.setattr(settings, "docling_enabled", True)
        result = router.parse_document(str(structured_pdf), original_name="s.pdf")

        assert result.metadata["parser"] == "docling"
        assert "docling_fallback_reason" not in result.metadata
        assert result.file_name == "s.pdf"
        assert result.language_hint == "en"

    def test_output_chunks_by_heading(self, substantial_pdf, require_docling):
        """The point of better parsing: chunks inherit a real breadcrumb path.

        Uses a document with realistic section lengths — a fixture with two-line
        sections is correctly merged into one chunk by the stub-merging pass, so
        it cannot demonstrate nesting.
        """
        from app.services.chunker import chunk_by_headings

        result = docling_parser.parse_with_docling(str(substantial_pdf))
        chunks = chunk_by_headings(result.blocks)

        assert len(chunks) >= 3, f"expected one chunk per section, got {len(chunks)}"
        assert all(">" in c.heading_path for c in chunks), (
            f"expected nested heading paths, got {[c.heading_path for c in chunks]}"
        )
        # Every section should be reachable by its own breadcrumb.
        paths = " ".join(c.heading_path for c in chunks)
        for section in ("8.1", "8.2", "8.3"):
            assert section in paths
