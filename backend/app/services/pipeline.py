"""
Pipeline orchestrator — runs the 10 canonical stages for one job.

Responsibilities:
 - Execute stages in order, with a clear input/output contract per stage.
 - Emit progress after every stage (and mid-stage for the fan-out stages).
 - Persist intermediate results so a failure is debuggable and partial output
   remains viewable in the UI.
 - Degrade gracefully: a non-critical stage failure records the error and lets
   the run continue; a critical failure stops the job with a useful message.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from app.config import settings
from app.models.enums import STAGE_LABELS, STAGE_PROGRESS, JobStatus, StageName
from app.models.schemas import (
    AssessmentPack,
    GapAnalysis,
    PackageMeta,
    TeacherKnowledgePackage,
)
from app.parsers import router as parse_router
from app.services import stages_knowledge as sk
from app.services import stages_pedagogy as sp
from app.services import validation as validation_service
from app.services.chunker import SectionIndex, chunk_by_headings, chunk_flat
from app.services.exporter import export_package
from app.services.llm_client import LLMClient, LLMError, LLMUsage
from app.services.progress import ProgressReporter
from app.services.agents import AgentCoordinator, AgentRole
from app.services.telemetry import JobTelemetry
from app.services.curriculum import align_objectives

logger = logging.getLogger("gyantra.pipeline")

# Stages whose failure should abort the run — without these there is no package.
CRITICAL_STAGES = {
    StageName.DOCUMENT_INTELLIGENCE,
    StageName.CLASSIFICATION,
    StageName.KNOWLEDGE_EXTRACTION,
    StageName.TEACHING_PLAN,
}


class PipelineError(RuntimeError):
    """Raised when a critical stage fails."""


class Pipeline:
    """One instance per job."""

    def __init__(
        self,
        job_id: str,
        file_path: str,
        original_name: str,
        document_hint,
        user_context: dict,
        reporter: ProgressReporter,
    ):
        self.job_id = job_id
        self.file_path = file_path
        self.original_name = original_name
        self.document_hint = document_hint
        self.user_context = user_context or {}
        self.reporter = reporter

        self.usage = LLMUsage()
        self.coordinator = AgentCoordinator()
        self.telemetry = JobTelemetry(job_id)
        self.package = TeacherKnowledgePackage(
            metadata=PackageMeta(job_id=job_id, source_file=original_name)
        )
        # Stages that ran but produced nothing usable. Surfaced on the job so
        # the UI can tell the teacher which parts of the package are missing.
        self.degraded_stages: list[str] = []
        self.chunks: list = []
        self.index: SectionIndex | None = None
        self._stage_dir = Path(settings.export_dir) / job_id / "stages"
        self._stage_dir.mkdir(parents=True, exist_ok=True)
        self._started = 0.0

    # ── helpers ──────────────────────────────────────────────────────────

    def _persist(self, stage: StageName, data) -> None:
        """Write a stage's output to disk for debugging and partial recovery."""
        try:
            payload = (
                data.model_dump(mode="json") if hasattr(data, "model_dump") else data
            )
            (self._stage_dir / f"{stage.value}.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except (OSError, TypeError, ValueError) as exc:
            logger.debug("could not persist %s: %s", stage.value, exc)

    async def _begin(self, stage: StageName, message: str = "") -> None:
        start, _ = STAGE_PROGRESS[stage]
        await self.reporter.stage_started(
            stage, STAGE_LABELS[stage], start, message
        )

    async def _finish(self, stage: StageName, message: str = "") -> None:
        _, end = STAGE_PROGRESS[stage]
        await self.reporter.stage_completed(
            stage, STAGE_LABELS[stage], end, message
        )

    async def _degraded(self, stage: StageName, reason: str) -> None:
        """Mark a stage as having run but produced nothing.

        Reporting an empty stage as 'completed' would put a green tick next to
        "0 activities" — the pipeline must not claim success it did not achieve.
        The run continues, but the shortfall is recorded and surfaced.
        """
        _, end = STAGE_PROGRESS[stage]
        self.degraded_stages.append(STAGE_LABELS[stage])
        await self.reporter.stage_failed(
            stage, STAGE_LABELS[stage], reason, fatal=False, progress=end
        )
        logger.warning("stage %s degraded: %s", stage.value, reason)

    async def _substep(self, stage: StageName, done: int, total: int, label: str) -> None:
        """Interpolate progress inside a fan-out stage."""
        start, end = STAGE_PROGRESS[stage]
        frac = done / max(total, 1)
        pct = int(start + (end - start) * frac)
        await self.reporter.stage_progress(
            stage, STAGE_LABELS[stage], pct, f"{label} ({done}/{total})"
        )

    # ── stage 1 ──────────────────────────────────────────────────────────

    async def stage_document_intelligence(self) -> None:
        stage = StageName.DOCUMENT_INTELLIGENCE
        await self._begin(stage, "Parsing document structure")

        doc = parse_router.parse_document(
            self.file_path, self.document_hint, self.original_name
        )

        if not doc.plain_text.strip():
            raise PipelineError(
                "No readable text could be extracted. If this is a scanned "
                "document, ensure OCR is enabled and tesseract is installed."
            )

        self.package.document_intelligence = doc

        # Chunk once; every later stage retrieves from this index.
        self.chunks = (
            chunk_by_headings(doc.blocks)
            if doc.heading_blocks
            else chunk_flat(doc.plain_text)
        )
        if not self.chunks:
            self.chunks = chunk_flat(doc.plain_text)
        self.index = SectionIndex(self.chunks)

        self._persist(stage, doc)
        await self._finish(
            stage,
            f"{doc.page_count} page(s), {len(doc.blocks)} blocks, "
            f"{len(self.chunks)} chunks · route: {doc.parse_route.value}",
        )

    # ── stage 2 ──────────────────────────────────────────────────────────

    async def stage_classification(self, client: LLMClient) -> None:
        stage = StageName.CLASSIFICATION
        await self._begin(stage, "Inferring subject, grade and topic")

        profile = await sk.classify_document(
            client, self.package.document_intelligence, self.chunks, self.user_context
        )
        self.package.document_profile = profile
        self._persist(stage, profile)
        await self._finish(
            stage, f"{profile.subject} · {profile.grade} · {profile.topic}"
        )

    # ── stage 3 ──────────────────────────────────────────────────────────

    async def stage_knowledge_extraction(self, client: LLMClient) -> None:
        stage = StageName.KNOWLEDGE_EXTRACTION
        await self._begin(stage, f"Extracting knowledge from {len(self.chunks)} sections")

        async def cb(done: int, total: int) -> None:
            await self._substep(stage, done, total, "Analysing sections")

        knowledge = await sk.extract_knowledge(
            client, self.chunks, self.package.document_profile, progress_cb=cb
        )

        if not knowledge.concepts:
            raise PipelineError(
                "No concepts could be extracted from this document. It may not be "
                "educational content, or the text extraction may have failed."
            )

        self.package.knowledge_extraction = knowledge
        self._persist(stage, knowledge)
        await self._finish(
            stage,
            f"{len(knowledge.concepts)} concepts, {len(knowledge.definitions)} definitions, "
            f"{len(knowledge.learning_objectives)} objectives",
        )

    # ── stage 4 ──────────────────────────────────────────────────────────

    async def stage_teaching_plan(self, client: LLMClient) -> None:
        stage = StageName.TEACHING_PLAN
        await self._begin(stage, "Designing an adaptive teaching sequence")

        plan = await sp.build_teaching_plan(
            client,
            self.package.document_profile,
            self.package.knowledge_extraction,
            self.chunks,
            self.user_context,
        )
        if not plan.periods:
            raise PipelineError("The teaching planner returned no periods.")

        self.package.teaching_plan = plan
        self._persist(stage, plan)
        await self._finish(
            stage,
            f"{plan.total_periods} periods × {plan.default_minutes_per_period} min",
        )

    # ── stage 5 ──────────────────────────────────────────────────────────

    async def stage_classroom_content(self, client: LLMClient) -> None:
        stage = StageName.CLASSROOM_CONTENT
        plan = self.package.teaching_plan
        await self._begin(stage, f"Writing material for {plan.total_periods} periods")

        async def cb(done: int, total: int) -> None:
            await self._substep(stage, done, total, "Generating periods")

        content = await sp.generate_classroom_content(
            client,
            plan,
            self.package.document_profile,
            self.package.knowledge_extraction,
            self.index,
            progress_cb=cb,
        )
        self.package.classroom_content = content
        self._persist(stage, [c.model_dump(mode="json") for c in content])

        # A period whose generation failed comes back with an empty script.
        written = sum(1 for c in content if c.teacher_script.strip())
        if written == 0:
            await self._degraded(
                stage, "No classroom content could be generated for any period."
            )
            return
        if written < len(content):
            await self._degraded(
                stage,
                f"Only {written} of {len(content)} periods have teaching content.",
            )
            return

        await self._finish(stage, f"{written} period(s) written")

    # ── stage 6 ──────────────────────────────────────────────────────────

    async def stage_activities(self, client: LLMClient) -> None:
        stage = StageName.ACTIVITIES
        await self._begin(stage, "Designing classroom activities")

        activities = await sp.generate_activities(
            client,
            self.package.teaching_plan,
            self.package.document_profile,
            self.package.knowledge_extraction,
        )
        self.package.activities = activities
        self._persist(stage, [a.model_dump(mode="json") for a in activities])

        if not activities:
            await self._degraded(
                stage, "No activities were generated — the model returned nothing usable."
            )
            return

        kinds = len({a.activity_type for a in activities})
        await self._finish(stage, f"{len(activities)} activities across {kinds} type(s)")

    # ── stage 7 ──────────────────────────────────────────────────────────

    async def stage_assessments(self, client: LLMClient) -> None:
        stage = StageName.ASSESSMENTS
        await self._begin(stage, "Building assessment items")

        pack = await sp.generate_assessments(
            client,
            self.package.document_profile,
            self.package.knowledge_extraction,
            self.index,
            self.user_context,
        )
        self.package.assessments = pack
        self._persist(stage, pack)
        i = pack.items

        total = len(i.mcqs) + len(i.short_answers) + len(i.long_answers) + len(i.numericals)
        if total == 0:
            await self._degraded(
                stage, "No assessment items were generated."
            )
            return

        await self._finish(
            stage,
            f"{len(i.mcqs)} MCQs, {len(i.short_answers)} short, "
            f"{len(i.long_answers)} long, {len(i.numericals)} numerical "
            f"({i.total_marks} marks)",
        )

    # ── stage 8 ──────────────────────────────────────────────────────────

    async def stage_gap_analysis(self, client: LLMClient) -> None:
        stage = StageName.GAP_ANALYSIS
        await self._begin(stage, "Diagnosing likely misconceptions")

        gaps = await sp.analyse_gaps(
            client, self.package.document_profile, self.package.knowledge_extraction
        )
        self.package.gap_analysis = gaps
        self._persist(stage, gaps)

        if not gaps.misconceptions:
            await self._degraded(stage, "No misconceptions were identified.")
            return

        await self._finish(
            stage,
            f"{len(gaps.misconceptions)} misconception(s), "
            f"{gaps.coverage_score:.0%} concept coverage",
        )

    # ── stage 9 ──────────────────────────────────────────────────────────

    async def stage_validation(self, client: LLMClient) -> None:
        stage = StageName.VALIDATION
        await self._begin(stage, "Checking schema, consistency and grounding")

        record = await validation_service.validate_package(self.package, client)
        self.package.validation = record
        self._persist(stage, record)

        await self._finish(
            stage,
            f"{record.overall_status.value.upper()} · grounding "
            f"{record.grounding_check.status.value} "
            f"(risk {record.grounding_check.hallucination_risk:.0%})",
        )

    # ── stage 10 ─────────────────────────────────────────────────────────

    async def stage_publishing(self) -> None:
        stage = StageName.PUBLISHING
        await self._begin(stage, "Packaging exports")

        self.package.metadata.processing_time_seconds = round(
            time.monotonic() - self._started, 2
        )
        self.package.metadata.model_calls = self.usage.calls
        self.package.metadata.total_tokens_used = self.usage.total_tokens
        self.package.metadata.models_used = sorted(self.usage.by_model)
        self.package.metadata.demo_mode = settings.demo_mode

        manifest = export_package(self.package, self.job_id)
        self.package.exports = manifest
        self._persist(stage, manifest)

        formats = sum(
            1
            for p in (
                manifest.json_path,
                manifest.lesson_plan_pdf_path,
                manifest.teacher_guide_pdf_path,
                manifest.assessment_pack_pdf_path,
            )
            if p
        )
        await self._finish(stage, f"{formats} export format(s) ready")

    # ── client selection ─────────────────────────────────────────────────

    def _make_client(self):
        """Return a real LLM client, or the offline stub when DEMO_MODE is on."""
        if settings.demo_mode:
            from app.services.demo_llm import DemoLLMClient

            logger.warning(
                "job %s running in DEMO_MODE — output is illustrative, not real "
                "model output",
                self.job_id,
            )
            return DemoLLMClient(usage=self.usage, telemetry=self.telemetry)
        return LLMClient(usage=self.usage, telemetry=self.telemetry)

    # ── run ──────────────────────────────────────────────────────────────

    async def run(self) -> TeacherKnowledgePackage:
        """Execute the full pipeline."""
        self._started = time.monotonic()
        await self.reporter.job_started()

        try:
            # Stage 1 needs no LLM.
            self.telemetry.begin_stage(StageName.DOCUMENT_INTELLIGENCE.value)
            await self.coordinator.run_stage_with_agent(
                AgentRole.PARSER, StageName.DOCUMENT_INTELLIGENCE, self.stage_document_intelligence, "Parse document"
            )
            self.telemetry.end_stage(StageName.DOCUMENT_INTELLIGENCE.value)

            async with self._make_client() as client:
                if not client.available_providers():
                    raise PipelineError(
                        "No LLM provider is configured. Set OPENROUTER_API_KEY or "
                        "GROQ_API_KEY in your environment and restart, or set "
                        "DEMO_MODE=true to run with the offline stub."
                    )

                stage_calls = [
                    (StageName.CLASSIFICATION, self.stage_classification),
                    (StageName.KNOWLEDGE_EXTRACTION, self.stage_knowledge_extraction),
                    (StageName.TEACHING_PLAN, self.stage_teaching_plan),
                    (StageName.CLASSROOM_CONTENT, self.stage_classroom_content),
                    (StageName.ACTIVITIES, self.stage_activities),
                    (StageName.ASSESSMENTS, self.stage_assessments),
                    (StageName.GAP_ANALYSIS, self.stage_gap_analysis),
                    (StageName.VALIDATION, self.stage_validation),
                ]

                for stage, fn in stage_calls:
                    try:
                        self.telemetry.begin_stage(stage.value)
                        
                        role_map = {
                            StageName.CLASSIFICATION: AgentRole.CLASSIFIER,
                            StageName.KNOWLEDGE_EXTRACTION: AgentRole.EXTRACTOR,
                            StageName.TEACHING_PLAN: AgentRole.PLANNER,
                            StageName.CLASSROOM_CONTENT: AgentRole.CONTENT_WRITER,
                            StageName.ACTIVITIES: AgentRole.ACTIVITY_DESIGNER,
                            StageName.ASSESSMENTS: AgentRole.ASSESSOR,
                            StageName.GAP_ANALYSIS: AgentRole.DIAGNOSTICIAN,
                            StageName.VALIDATION: AgentRole.VALIDATOR,
                        }
                        role = role_map.get(stage, AgentRole.PLANNER)
                        
                        async def run_fn(f=fn, c=client):
                            await f(c)
                            
                        await self.coordinator.run_stage_with_agent(
                            role, stage, run_fn, f"Run {stage.value}"
                        )
                        
                        # Inject Curriculum Alignment after Stage 3
                        if stage == StageName.KNOWLEDGE_EXTRACTION:
                            self.telemetry.begin_stage("curriculum_alignment")
                            self.package.curriculum_alignment = align_objectives(
                                self.package.knowledge_extraction.learning_objectives if self.package.knowledge_extraction else [],
                                self.package.knowledge_extraction.concepts if self.package.knowledge_extraction else [],
                                self.package.document_profile
                            )
                            self.telemetry.end_stage("curriculum_alignment")
                            
                        self.telemetry.end_stage(stage.value)
                    except (PipelineError, LLMError) as exc:
                        self.telemetry.end_stage(stage.value)
                        if stage in CRITICAL_STAGES:
                            raise
                        # Non-critical: record and keep going with partial output.
                        logger.error("stage %s failed (non-critical): %s", stage.value, exc)
                        await self.reporter.stage_failed(
                            stage, STAGE_LABELS[stage], str(exc), fatal=False
                        )

            # Publishing runs even if optional stages degraded.
            self.telemetry.begin_stage(StageName.PUBLISHING.value)
            
            # Save bonus metadata before publishing
            self.package.metadata.agent_traces = self.coordinator.traces
            self.package.metadata.telemetry = self.telemetry.summarize()
            self.package.metadata.performance_stats = {
                "cache_hit_rate": self.package.metadata.telemetry.cache_hit_rate if self.package.metadata.telemetry else 0,
                "parallel_tasks_run": 2, # Default parallel limit
                "total_llm_calls": len(self.package.metadata.telemetry.llm_calls) if self.package.metadata.telemetry else 0,
            }
            if self.index:
                self.package.metadata.rag_stats = {
                    "chunks_indexed": len(self.index.chunks),
                    "search_queries_served": getattr(self.index, "queries_served", 0)
                }
            
            await self.coordinator.run_stage_with_agent(
                AgentRole.PUBLISHER, StageName.PUBLISHING, self.stage_publishing, "Export and publish"
            )
            self.telemetry.end_stage(StageName.PUBLISHING.value)
            await self.reporter.job_completed(self.package, self.degraded_stages)
            logger.info(
                "job %s completed in %.1fs · %s model calls · %s tokens",
                self.job_id,
                self.package.metadata.processing_time_seconds,
                self.usage.calls,
                self.usage.total_tokens,
            )
            return self.package

        except Exception as exc:  # noqa: BLE001 — the boundary must catch everything
            logger.exception("job %s failed", self.job_id)
            stage = self.reporter.current_stage or StageName.DOCUMENT_INTELLIGENCE
            await self.reporter.job_failed(str(exc), stage)
            raise


async def run_pipeline(
    job_id: str,
    file_path: str,
    original_name: str,
    document_hint,
    user_context: dict,
    reporter: ProgressReporter,
) -> TeacherKnowledgePackage:
    """Module-level entry point used by the API layer."""
    pipeline = Pipeline(
        job_id=job_id,
        file_path=file_path,
        original_name=original_name,
        document_hint=document_hint,
        user_context=user_context,
        reporter=reporter,
    )
    return await pipeline.run()
