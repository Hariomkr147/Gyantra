"""Chunker, validation engine, and schema tests."""

from __future__ import annotations

from app.models.enums import BlockType, Origin
from app.models.schemas import (
    Concept,
    KnowledgeExtractionResult,
    PeriodPlan,
    TeachingPlan,
    TeacherKnowledgePackage,
    TextBlock,
    ValidationRecord,
)
from app.services import chunker, validation


class TestChunker:
    def _blocks(self, spec: list[tuple[str, int, str]]) -> list[TextBlock]:
        """spec: [(kind, level, text)] where kind is 'h' or 'p'."""
        out = []
        for kind, level, text in spec:
            out.append(
                TextBlock(
                    block_type=BlockType.HEADING if kind == "h" else BlockType.PARAGRAPH,
                    content=text,
                    level=level,
                )
            )
        return out

    def test_splits_at_heading_boundaries(self):
        """Each substantive section gets its own chunk, even when the whole
        document would fit in one. Section-scoped extraction depends on this."""
        blocks = self._blocks(
            [
                ("h", 1, "Chapter 1"),
                ("h", 2, "Section A"),
                ("p", 0, "Alpha content. " * 40),
                ("h", 2, "Section B"),
                ("p", 0, "Beta content. " * 40),
                ("h", 2, "Section C"),
                ("p", 0, "Gamma content. " * 40),
            ]
        )
        chunks = chunker.chunk_by_headings(blocks, target_tokens=700)

        assert len(chunks) == 3
        assert "Section A" in chunks[0].heading_path
        assert "Section B" in chunks[1].heading_path
        assert "Section C" in chunks[2].heading_path
        # The bare chapter title should ride along with the first real section.
        assert "Chapter 1" in chunks[0].heading_path

    def test_heading_path_is_hierarchical(self):
        blocks = self._blocks(
            [
                ("h", 1, "Physics"),
                ("h", 2, "Motion"),
                ("h", 3, "Velocity"),
                ("p", 0, "Velocity content. " * 40),
            ]
        )
        chunks = chunker.chunk_by_headings(blocks)
        assert chunks[0].heading_path == "Physics > Motion > Velocity"

    def test_oversized_section_is_split(self):
        blocks = self._blocks(
            [
                ("h", 1, "Long Section"),
                ("p", 0, "word " * 4000),  # ~5000 tokens, far over target
            ]
        )
        chunks = chunker.chunk_by_headings(blocks, target_tokens=300)

        assert len(chunks) > 1
        for c in chunks:
            # Allow modest overshoot from overlap, but nothing pathological.
            assert c.token_estimate < 300 * 2
            assert c.heading_path == "Long Section"

    def test_stub_sections_merge(self):
        """A heading with almost no body should not consume its own LLM call."""
        blocks = self._blocks(
            [
                ("h", 1, "Title"),
                ("h", 2, "A"),
                ("p", 0, "short"),
                ("h", 2, "B"),
                ("p", 0, "also short"),
                ("h", 2, "C"),
                ("p", 0, "Real content here. " * 50),
            ]
        )
        chunks = chunker.chunk_by_headings(blocks)
        assert len(chunks) < 4

    def test_chunk_count_is_capped(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "max_chunks", 5)
        spec = []
        for i in range(30):
            spec.append(("h", 2, f"Section {i}"))
            spec.append(("p", 0, f"Content for section {i}. " * 30))

        chunks = chunker.chunk_by_headings(self._blocks(spec))
        assert len(chunks) <= 5

    def test_block_ids_and_pages_preserved(self):
        blocks = [
            TextBlock(block_type=BlockType.HEADING, content="S1", level=1, page=3),
            TextBlock(block_type=BlockType.PARAGRAPH, content="body " * 60, page=3),
            TextBlock(block_type=BlockType.PARAGRAPH, content="more " * 60, page=4),
        ]
        chunks = chunker.chunk_by_headings(blocks)
        assert chunks[0].pages == [3, 4]
        assert len(chunks[0].block_ids) == 3

    def test_preamble_before_first_heading_is_kept(self):
        blocks = self._blocks(
            [
                ("p", 0, "Preamble text before any heading. " * 30),
                ("h", 1, "First Heading"),
                ("p", 0, "Body content. " * 30),
            ]
        )
        chunks = chunker.chunk_by_headings(blocks)
        assert any("Preamble" in c.text for c in chunks)

    def test_no_headings_returns_single_chunk(self):
        blocks = self._blocks([("p", 0, "Just prose. " * 50)])
        chunks = chunker.chunk_by_headings(blocks)
        assert len(chunks) == 1
        assert chunks[0].heading_path == ""

    def test_empty_input(self):
        assert chunker.chunk_by_headings([]) == []

    def test_flat_chunking_fallback(self):
        text = (
            "First section.\n\n" + "Lorem ipsum " * 300
            + "\n\nSecond section.\n\n" + "Dolor sit " * 300
        )
        chunks = chunker.chunk_flat(text, target_tokens=60)
        assert len(chunks) >= 2

    def test_section_index_search(self):
        c1 = chunker.Chunk(id="c1", text="Force is a push or pull", heading_path="Physics > Force")
        c2 = chunker.Chunk(id="c2", text="Velocity is the rate of change of displacement", heading_path="Physics > Motion")
        c3 = chunker.Chunk(id="c3", text="Newton's laws govern motion", heading_path="Physics")

        idx = chunker.SectionIndex([c1, c2, c3])
        assert idx.search(["force"])[0].id == "c1"
        assert len(idx.search(["motion"])) >= 2

    def test_section_index_empty(self):
        idx = chunker.SectionIndex([])
        assert idx.search(["anything"]) == []


class TestValidation:
    def _minimal_package(self) -> TeacherKnowledgePackage:
        ke = KnowledgeExtractionResult(
            learning_objectives=["Understand force"],
            concepts=[Concept(name="Force", description="A push or pull")],
        )
        plan = TeachingPlan(
            total_periods=1,
            periods=[
                PeriodPlan(
                    number=1,
                    title="Force",
                    estimated_minutes=40,
                    key_concepts=[ke.concepts[0].id],
                )
            ],
        )
        from app.models.schemas import (
            ClassroomContent,
            DocumentIntelligenceResult,
            DocumentProfile,
        )

        doc = DocumentIntelligenceResult(
            plain_text="Force is a push or a pull. F = m * a is Newton's second law.",
            blocks=[
                TextBlock(
                    block_type=BlockType.PARAGRAPH,
                    content="Force is a push or a pull.",
                ),
            ],
            page_count=1,
        )

        return TeacherKnowledgePackage(
            document_intelligence=doc,
            document_profile=DocumentProfile(subject="Physics", grade="Class 9", topic="Force"),
            knowledge_extraction=ke,
            teaching_plan=plan,
            classroom_content=[
                ClassroomContent(
                    period_id=plan.periods[0].id,
                    teacher_script="Today we will learn about force.",
                    blackboard_notes="Force = push or pull",
                )
            ],
        )

    def test_schema_check_missing_activities_triggers_warn(self):
        pkg = self._minimal_package()
        result = validation.check_schema(pkg)
        assert result.status in ("warn", "fail")

    def test_consistency_check_detects_orphan_concepts(self):
        pkg = self._minimal_package()
        # Add a concept that is not in any period's key_concepts.
        pkg.knowledge_extraction.concepts.append(Concept(name="Orphan", description="No one teaches this", source_ref=None, origin=Origin.SOURCE))
        result = validation.check_consistency(pkg)
        assert any("orphan" in i.lower() for i in result.issues)

    def test_consistency_all_ok(self):
        pkg = self._minimal_package()
        result = validation.check_consistency(pkg)
        assert result.status == "pass"

    def test_grounding_lexical_finds_drift(self):
        pkg = self._minimal_package()
        claims = [
            "Force is a push or a pull.",  # in source vocabulary
            "The mitochondria are the powerhouse of the cell.",  # unrelated
        ]
        suspicious, risk = validation.check_grounding_lexical(pkg, claims)
        assert len(suspicious) >= 1
        # The mitochondria claim should have high unseen-word ratio.
        assert any("mitochondria" in s.lower() for s in suspicious)

    def test_grounding_lexical_all_grounded(self):
        pkg = self._minimal_package()
        claims = ["Force is a push or a pull.", "F equals m times a.", "Force is measured in newtons."]
        suspicious, risk = validation.check_grounding_lexical(pkg, claims)
        assert risk == 0.0 or risk < 0.2


class TestPipelineHeuristic:
    """Verify the deterministic fallback planner produces a reasonable plan."""

    def test_heuristic_plan_adapts_count(self):
        from app.services.stages_pedagogy import _heuristic_plan
        from app.models.schemas import DocumentProfile

        profile = DocumentProfile(subject="Physics", grade="Class 9", topic="Force")
        knowledge = KnowledgeExtractionResult(
            concepts=[
                Concept(id="c1", name="Force", description="Desc"),
                Concept(id="c2", name="Inertia", description="Desc"),
                Concept(id="c3", name="Newton's First Law", description="Desc"),
                Concept(id="c4", name="Second Law", description="Desc"),
                Concept(id="c5", name="Third Law", description="Desc"),
                Concept(id="c6", name="Momentum", description="Desc"),
                Concept(id="c7", name="Friction", description="Desc"),
            ],
        )
        plan = _heuristic_plan(profile, knowledge, {})

        # 7 concepts should produce 2-3 periods, not a fixed 5.
        assert plan.total_periods >= 2
        assert plan.total_periods <= 7  # worst case all advanced
        assert len(plan.periods) == plan.total_periods
