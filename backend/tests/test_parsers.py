"""Parser and routing tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models.enums import BlockType, DocumentHint, ParseRoute
from app.parsers import router, text_parser


class TestTextParser:
    def test_extracts_headings(self, sample_text_file: Path):
        result = text_parser.parse_text(str(sample_text_file))
        headings = [b for b in result.blocks if b.block_type == BlockType.HEADING]

        assert len(headings) == 5  # 1 chapter title + 4 sections
        assert headings[0].content == "Chapter 8: Force and Laws of Motion"
        assert headings[0].level == 1
        assert headings[1].level == 2

    def test_extracts_table(self, sample_text_file: Path):
        result = text_parser.parse_text(str(sample_text_file))
        tables = [b for b in result.blocks if b.block_type == BlockType.TABLE]

        assert result.table_count == 1
        assert len(tables) == 1
        assert "First" in tables[0].content

    def test_merges_paragraph_lines(self, sample_text_file: Path):
        result = text_parser.parse_text(str(sample_text_file))
        paras = [b for b in result.blocks if b.block_type == BlockType.PARAGRAPH]

        # Wrapped source lines should become whole paragraphs, not fragments.
        assert any("balanced\nforces" not in p.content for p in paras)
        assert any(len(p.content) > 150 for p in paras)

    def test_numbered_heading_detection(self, tmp_path: Path):
        path = tmp_path / "notes.txt"
        path.write_text(
            "1. Introduction\n\nSome text here that is long enough to be a paragraph.\n\n"
            "1.1 Background Details\n\nMore explanatory text follows in this section.\n",
            encoding="utf-8",
        )
        result = text_parser.parse_text(str(path))
        headings = [b for b in result.blocks if b.block_type == BlockType.HEADING]

        assert len(headings) == 2
        assert headings[0].level == 1
        assert headings[1].level == 2


class TestRouting:
    def test_rejects_unsupported_extension(self, tmp_path: Path):
        path = tmp_path / "image.png"
        path.write_bytes(b"\x89PNG")

        with pytest.raises(router.UnsupportedFileError, match="Unsupported file type"):
            router.decide_route(str(path))

    def test_text_file_routes_lightweight(self, sample_text_file: Path):
        route, info = router.decide_route(str(sample_text_file))
        assert route == ParseRoute.LIGHTWEIGHT_TEXT

    def test_docx_hint_selects_table_route(self, tmp_path: Path):
        path = tmp_path / "doc.docx"
        path.write_bytes(b"stub")
        route, _ = router.decide_route(str(path), DocumentHint.TEXT_WITH_TABLES)
        assert route == ParseRoute.STRUCTURED_TABLES

    def test_pptx_routes_layout_aware(self, tmp_path: Path):
        path = tmp_path / "deck.pptx"
        path.write_bytes(b"stub")
        route, _ = router.decide_route(str(path))
        assert route == ParseRoute.LAYOUT_AWARE

    def test_parse_document_sets_metadata(self, sample_text_file: Path):
        result = router.parse_document(
            str(sample_text_file), DocumentHint.MOSTLY_TEXT, "force_and_motion.md"
        )
        assert result.file_name == "force_and_motion.md"
        assert result.detected_hint == DocumentHint.MOSTLY_TEXT
        assert "routing" in result.metadata
        assert result.language_hint == "en"


class TestLanguageDetection:
    def test_english(self):
        assert router._detect_language("The quick brown fox jumps over the dog.") == "en"

    def test_hindi(self):
        assert router._detect_language("गति के नियम और बल की अवधारणा एक महत्वपूर्ण विषय है।") == "hi"

    def test_empty_defaults_english(self):
        assert router._detect_language("") == "en"
