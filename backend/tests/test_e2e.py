"""
End-to-end pipeline test using the offline stub LLM.

This verifies orchestration, not content quality: every stage runs, progress is
emitted in order, the package validates, and all four exports are written.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.enums import STAGE_PROGRESS, DocumentHint, JobStatus, StageName


@pytest.fixture
def demo_env(monkeypatch, tmp_path: Path):
    """Point storage at tmp_path and force demo mode for this test."""
    from app.config import settings

    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "export_dir", tmp_path / "exports")
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(settings, "cache_dir", tmp_path / "cache")
    monkeypatch.setattr(settings, "llm_cache_enabled", False)
    settings.ensure_dirs()
    return settings


class RecordingStore:
    """Minimal JobStore stand-in that records published events."""

    def __init__(self):
        self.events: list[dict] = []
        self.stage_statuses: dict[str, str] = {}
        self.fields: dict = {}

    async def publish(self, job_id: str, event: dict) -> None:
        self.events.append(event)

    async def update(self, job_id: str, **fields) -> None:
        self.fields.update(fields)

    async def set_stage_status(self, job_id, stage, status, message="", started=False, finished=False):
        self.stage_statuses[stage.value] = status.value


@pytest.mark.asyncio
async def test_full_pipeline_demo_mode(demo_env, sample_text_file: Path):
    from app.services.pipeline import run_pipeline
    from app.services.progress import ProgressReporter

    store = RecordingStore()
    reporter = ProgressReporter("testjob", store)

    package = await run_pipeline(
        job_id="testjob",
        file_path=str(sample_text_file),
        original_name="force_and_motion.md",
        document_hint=DocumentHint.MOSTLY_TEXT,
        user_context={"grade": "Class 9", "period_minutes": 40},
        reporter=reporter,
    )

    # --- every stage completed ---
    for stage in StageName:
        assert store.stage_statuses.get(stage.value) == JobStatus.COMPLETED.value, (
            f"{stage.value} did not complete"
        )

    # --- stage 1: parsing ---
    di = package.document_intelligence
    assert di is not None
    assert di.page_count >= 1
    assert di.table_count == 1
    assert len(di.heading_blocks) == 5

    # --- stage 2: classification ---
    profile = package.document_profile
    assert profile is not None
    assert profile.subject == "Physics"  # stub keyword scoring should find it
    assert profile.grade == "Class 9"    # user context must win

    # --- stage 3: extraction ---
    ke = package.knowledge_extraction
    assert ke is not None
    assert len(ke.concepts) >= 3
    assert ke.learning_objectives

    # --- stage 4: adaptive plan ---
    plan = package.teaching_plan
    assert plan is not None
    assert plan.total_periods >= 1
    assert plan.total_periods == len(plan.periods)
    assert plan.adaptation_rationale
    # Every concept must be scheduled somewhere.
    scheduled = {cid for p in plan.periods for cid in p.key_concepts}
    assert scheduled == {c.id for c in ke.concepts}

    # --- stage 5: content for every period ---
    assert len(package.classroom_content) == plan.total_periods
    for content in package.classroom_content:
        assert content.teacher_script
        assert content.blackboard_notes
        assert len(content.checkpoint_questions) >= 2

    # --- stages 6-8 ---
    assert package.activities
    assert len({a.activity_type for a in package.activities}) >= 3
    assert package.assessments is not None
    assert package.assessments.items.mcqs
    assert package.assessments.items.total_marks > 0
    assert package.gap_analysis is not None
    assert package.gap_analysis.misconceptions

    # --- stage 9: validation ran and consistency holds ---
    v = package.validation
    assert v is not None
    assert v.consistency_check.status == "pass", v.consistency_check.issues

    # --- stage 10: all exports on disk ---
    ex = package.exports
    assert Path(ex.json_path).exists()
    assert Path(ex.lesson_plan_pdf_path).exists()
    assert Path(ex.teacher_guide_pdf_path).exists()
    assert Path(ex.assessment_pack_pdf_path).exists()
    for pdf in (ex.lesson_plan_pdf_path, ex.teacher_guide_pdf_path, ex.assessment_pack_pdf_path):
        assert Path(pdf).stat().st_size > 1500, f"{pdf} looks truncated"

    # --- the JSON export round-trips ---
    from app.models.schemas import TeacherKnowledgePackage

    reloaded = TeacherKnowledgePackage.model_validate(
        json.loads(Path(ex.json_path).read_text(encoding="utf-8"))
    )
    assert reloaded.summary() == package.summary()

    # --- demo output is labelled as such ---
    assert package.metadata.demo_mode is True
    assert package.metadata.model_calls > 0


@pytest.mark.asyncio
async def test_progress_events_are_ordered_and_monotonic(demo_env, sample_text_file: Path):
    from app.services.pipeline import run_pipeline
    from app.services.progress import ProgressReporter

    store = RecordingStore()
    reporter = ProgressReporter("testjob2", store)

    await run_pipeline(
        job_id="testjob2",
        file_path=str(sample_text_file),
        original_name="force_and_motion.md",
        document_hint=DocumentHint.NOT_SURE,
        user_context={},
        reporter=reporter,
    )

    types = [e["type"] for e in store.events]
    assert types[0] == "job_started"
    assert types[-1] == "job_completed"

    # Progress must never go backwards — the UI depends on this.
    progress_values = [e["progress"] for e in store.events if "progress" in e]
    assert progress_values == sorted(progress_values), progress_values
    assert progress_values[-1] == 100

    # Stages must start in canonical order.
    started = [e["stage"] for e in store.events if e["type"] == "stage_started"]
    assert started == [s.value for s in StageName]

    # Each stage's completion percentage matches its declared range.
    for event in store.events:
        if event["type"] == "stage_completed":
            _, end = STAGE_PROGRESS[StageName(event["stage"])]
            assert event["progress"] == end


@pytest.mark.asyncio
async def test_unreadable_document_fails_cleanly(demo_env, tmp_path: Path):
    """A file with no extractable text must fail with a useful message."""
    from app.services.pipeline import run_pipeline
    from app.services.progress import ProgressReporter

    empty = tmp_path / "empty.txt"
    empty.write_text("   \n\n  \n", encoding="utf-8")

    store = RecordingStore()
    reporter = ProgressReporter("testjob3", store)

    with pytest.raises(Exception):
        await run_pipeline(
            job_id="testjob3",
            file_path=str(empty),
            original_name="empty.txt",
            document_hint=DocumentHint.MOSTLY_TEXT,
            user_context={},
            reporter=reporter,
        )

    failures = [e for e in store.events if e["type"] == "job_failed"]
    assert failures
    assert "no readable text" in failures[0]["error"].lower()
