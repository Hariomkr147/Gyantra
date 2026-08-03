"""
Honest reporting when optional stages produce nothing.

A stage that ran but returned an empty result must not report success. The job
still completes — a partial package is more useful than none — but the shortfall
has to reach the UI, or a teacher opens empty tabs with no explanation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models.enums import DocumentHint, JobStatus, StageName


@pytest.fixture
def demo_env(monkeypatch, tmp_path: Path):
    from app.config import settings

    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "export_dir", tmp_path / "exports")
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(settings, "cache_dir", tmp_path / "cache")
    monkeypatch.setattr(settings, "llm_cache_enabled", False)
    monkeypatch.setattr(settings, "docling_enabled", False)
    settings.ensure_dirs()
    return settings


class RecordingStore:
    def __init__(self):
        self.events: list[dict] = []
        self.stage_statuses: dict[str, str] = {}
        self.fields: dict = {}

    async def publish(self, job_id, event):
        self.events.append(event)

    async def update(self, job_id, **fields):
        self.fields.update(fields)

    async def set_stage_status(
        self, job_id, stage, status, message="", started=False, finished=False
    ):
        self.stage_statuses[stage.value] = status.value


async def _run(sample: Path, store: RecordingStore):
    from app.services.pipeline import run_pipeline
    from app.services.progress import ProgressReporter

    return await run_pipeline(
        job_id="degradetest",
        file_path=str(sample),
        original_name="chapter.md",
        document_hint=DocumentHint.MOSTLY_TEXT,
        user_context={"grade": "Class 9"},
        reporter=ProgressReporter("degradetest", store),
    )


@pytest.mark.asyncio
async def test_empty_activities_stage_reports_failure_not_success(
    demo_env, sample_text_file, monkeypatch
):
    """The bug this guards: '0 activities' used to arrive with a green tick."""
    from app.services import stages_pedagogy

    async def no_activities(*args, **kwargs):
        return []

    monkeypatch.setattr(stages_pedagogy, "generate_activities", no_activities)

    store = RecordingStore()
    package = await _run(sample_text_file, store)

    # The stage must not claim success.
    assert store.stage_statuses[StageName.ACTIVITIES.value] == JobStatus.FAILED.value

    # But the job still finishes and publishes what it did produce.
    assert store.stage_statuses[StageName.PUBLISHING.value] == JobStatus.COMPLETED.value
    assert package.teaching_plan.total_periods > 0
    assert Path(package.exports.json_path).exists()


@pytest.mark.asyncio
async def test_degraded_stage_is_reported_as_non_fatal(
    demo_env, sample_text_file, monkeypatch
):
    from app.services import stages_pedagogy

    async def no_activities(*args, **kwargs):
        return []

    monkeypatch.setattr(stages_pedagogy, "generate_activities", no_activities)

    store = RecordingStore()
    await _run(sample_text_file, store)

    failures = [e for e in store.events if e["type"] == "stage_failed"]
    assert failures, "a degraded stage must emit stage_failed"

    activity_failure = next(
        e for e in failures if e["stage"] == StageName.ACTIVITIES.value
    )
    # Non-fatal: the UI should warn, not show a dead end.
    assert activity_failure["fatal"] is False
    assert "activities" in activity_failure["error"].lower()
    # Progress must still advance past the stage so the bar does not stall.
    assert activity_failure["progress"] is not None


@pytest.mark.asyncio
async def test_job_completion_lists_degraded_stages(
    demo_env, sample_text_file, monkeypatch
):
    """The teacher needs to know which sections are missing, and why."""
    from app.services import stages_pedagogy
    from app.models.schemas import AssessmentPack, GapAnalysis

    async def no_activities(*args, **kwargs):
        return []

    async def no_assessments(*args, **kwargs):
        return AssessmentPack()

    async def no_gaps(*args, **kwargs):
        return GapAnalysis()

    monkeypatch.setattr(stages_pedagogy, "generate_activities", no_activities)
    monkeypatch.setattr(stages_pedagogy, "generate_assessments", no_assessments)
    monkeypatch.setattr(stages_pedagogy, "analyse_gaps", no_gaps)

    store = RecordingStore()
    await _run(sample_text_file, store)

    completion = next(e for e in store.events if e["type"] == "job_completed")
    degraded = completion["degraded_stages"]

    assert len(degraded) == 3
    assert "Activity Generation" in degraded
    assert "Assessment Generation" in degraded
    assert "Learning Gap Analysis" in degraded

    # A warning must be persisted on the job, not just emitted in passing.
    assert completion["warning"]
    assert "rate-limited" in completion["warning"]
    assert store.fields["error_message"], "the warning must reach the job record"


@pytest.mark.asyncio
async def test_partial_classroom_content_is_flagged(
    demo_env, sample_text_file, monkeypatch
):
    """Some periods generated, some empty — that is still a degraded result."""
    from app.services import stages_pedagogy
    from app.models.schemas import ClassroomContent

    real = stages_pedagogy.generate_classroom_content

    async def half_empty(client, plan, profile, knowledge, index, progress_cb=None):
        content = await real(client, plan, profile, knowledge, index, progress_cb)
        # Blank out the first period, as a failed per-period call would.
        if content:
            content[0] = ClassroomContent(period_id=content[0].period_id)
        return content

    monkeypatch.setattr(stages_pedagogy, "generate_classroom_content", half_empty)

    store = RecordingStore()
    package = await _run(sample_text_file, store)

    assert (
        store.stage_statuses[StageName.CLASSROOM_CONTENT.value]
        == JobStatus.FAILED.value
    )
    failure = next(
        e
        for e in store.events
        if e["type"] == "stage_failed"
        and e["stage"] == StageName.CLASSROOM_CONTENT.value
    )
    assert "of" in failure["error"], f"expected an N-of-M message, got {failure['error']}"
    # The periods that did generate are still in the package.
    assert len(package.classroom_content) == package.teaching_plan.total_periods


@pytest.mark.asyncio
async def test_healthy_run_reports_no_degradation(demo_env, sample_text_file):
    """The control case: nothing degraded means no warning noise."""
    store = RecordingStore()
    await _run(sample_text_file, store)

    completion = next(e for e in store.events if e["type"] == "job_completed")
    assert completion["degraded_stages"] == []
    assert completion["warning"] == ""

    for stage in StageName:
        assert store.stage_statuses[stage.value] == JobStatus.COMPLETED.value
