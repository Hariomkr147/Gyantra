"""
Pipeline schemas — the structural contract for every stage.

Every schema is a Pydantic model.  The orchestrator never passes raw text
between stages; it passes instances of these models (or their dicts).  This
keeps the system debuggable, typed, and testable.

Design rules:
 - Every object that carries factual/conceptual content has an *origin* field
   (`Origin.SOURCE` vs `Origin.PEDAGOGICAL`) so we never lose provenance.
 - Source references (`source_ref`) are optional but encouraged on every
   fact-level node.
 - The top-level `TeacherKnowledgePackage` is the canonical output contract.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.enums import (
    ActivityType,
    BlockType,
    BloomLevel,
    Difficulty,
    DocumentHint,
    JobStatus,
    Origin,
    ParseRoute,
    QuestionType,
    Severity,
    StageName,
    ValidationStatus,
)


# ── helpers ──────────────────────────────────────────────────────────────────


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── document intelligence ────────────────────────────────────────────────────


class TextBlock(BaseModel):
    """A single structural unit extracted from the document.

    These blocks are the atoms that later stages reference via source_ref.
    """

    id: str = Field(default_factory=_uid)
    block_type: BlockType
    content: str
    level: int = 0  # heading depth (1=h1, 2=h2, ...), 0 for non-headings
    page: int | None = None
    bbox: list[float] | None = None  # normalised [x0,y0,x1,y1] if available
    caption: str | None = None  # for tables / figures
    raw_html: str | None = None  # for tables that have HTML structure
    origin: Origin = Origin.SOURCE


class DocumentIntelligenceResult(BaseModel):
    """Stage 1 output."""

    metadata: dict[str, Any] = Field(default_factory=dict)
    blocks: list[TextBlock] = Field(default_factory=list)
    plain_text: str = ""
    page_count: int = 0
    file_name: str = ""
    file_type: str = ""
    detected_hint: DocumentHint | None = None
    parse_route: ParseRoute = ParseRoute.LIGHTWEIGHT_TEXT
    ocr_used: bool = False
    language_hint: str = "en"
    table_count: int = 0
    figure_count: int = 0
    equation_count: int = 0

    @property
    def total_chars(self) -> int:
        return len(self.plain_text)

    @property
    def heading_blocks(self) -> list[TextBlock]:
        return [b for b in self.blocks if b.block_type == BlockType.HEADING]


# ── educational classification ───────────────────────────────────────────────


class DocumentProfile(BaseModel):
    """Stage 2 output."""

    subject: str = ""
    grade: str = ""
    difficulty: Difficulty = Difficulty.FOUNDATIONAL
    topic: str = ""
    chapter: str = ""
    language: str = "en"
    board: str = ""
    document_type: str = ""  # e.g. "textbook chapter", "notes", "paper"
    estimated_periods: int = 0
    confidence: float = 1.0  # 0-1


# ── knowledge extraction ─────────────────────────────────────────────────────


class SourceRef(BaseModel):
    """Pointer back to a chunk or block in the source."""

    block_ids: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)
    pages: list[int] = Field(default_factory=list)
    snippet: str = ""  # truncated source text for lightweight grounding checks


class Concept(BaseModel):
    """One distinct idea / topic extracted from the source."""

    id: str = Field(default_factory=_uid)
    name: str
    description: str
    bloom_level: BloomLevel = BloomLevel.UNDERSTAND
    difficulty: Difficulty = Difficulty.INTERMEDIATE
    prerequisites: list[str] = Field(default_factory=list)  # concept IDs
    is_core: bool = False  # true for "must-learn" concepts
    source_ref: SourceRef | None = None
    origin: Origin = Origin.SOURCE


class Definition(BaseModel):
    id: str = Field(default_factory=_uid)
    term: str
    text: str
    source_ref: SourceRef | None = None
    origin: Origin = Origin.SOURCE


class Formula(BaseModel):
    id: str = Field(default_factory=_uid)
    name: str
    latex: str = ""
    explanation: str = ""
    variables: list[dict[str, str]] = Field(default_factory=list)
    source_ref: SourceRef | None = None
    origin: Origin = Origin.SOURCE


class Example(BaseModel):
    id: str = Field(default_factory=_uid)
    title: str = ""
    text: str
    is_solved: bool = False
    source_ref: SourceRef | None = None
    origin: Origin = Origin.SOURCE


class Application(BaseModel):
    id: str = Field(default_factory=_uid)
    name: str
    description: str
    origin: Origin = Origin.PEDAGOGICAL  # usually pedagogical


class MisconceptionExtracted(BaseModel):
    """Quick stub for likely misconceptions; fleshed out in Stage 8."""

    id: str = Field(default_factory=_uid)
    statement: str
    concept_ids: list[str] = Field(default_factory=list)
    source_ref: SourceRef | None = None
    origin: Origin = Origin.SOURCE


class KnowledgeExtractionResult(BaseModel):
    """Stage 3 output."""

    learning_objectives: list[str] = Field(default_factory=list)
    prerequisites_list: list[str] = Field(default_factory=list)
    concepts: list[Concept] = Field(default_factory=list)
    definitions: list[Definition] = Field(default_factory=list)
    formulas: list[Formula] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    examples: list[Example] = Field(default_factory=list)
    applications: list[Application] = Field(default_factory=list)
    common_misconceptions: list[MisconceptionExtracted] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    concept_graph: dict[str, list[str]] = Field(default_factory=dict)  # id → parent ids
    key_terms_glossary: dict[str, str] = Field(default_factory=dict)


# ── teaching plan ────────────────────────────────────────────────────────────


class PeriodObjective(BaseModel):
    concept_ids: list[str] = Field(default_factory=list)
    text: str = ""


class PeriodPlan(BaseModel):
    id: str = Field(default_factory=_uid)
    number: int
    title: str
    estimated_minutes: int = 40
    objectives: list[PeriodObjective] = Field(default_factory=list)
    key_concepts: list[str] = Field(default_factory=list)
    warmup_strategy: str = ""
    flow_summary: str = ""  # 1-2 sentence narrative of the period's arc
    prerequisite_review: list[str] = Field(default_factory=list)
    source_chunks: list[str] = Field(default_factory=list)  # chunk IDs used


class TeachingPlan(BaseModel):
    """Stage 4 output.

    Adaptive — number of periods is chosen by the model based on content volume.
    """

    total_periods: int = 0
    default_minutes_per_period: int = 40
    adaptation_rationale: str = ""
    periods: list[PeriodPlan] = Field(default_factory=list)
    sequence_map: dict[int, list[str]] = Field(
        default_factory=dict
    )  # period_num → concept IDs
    cross_period_review_points: list[str] = Field(default_factory=list)


# ── classroom content ────────────────────────────────────────────────────────


class ClassroomContent(BaseModel):
    """Stage 5 output for one period."""

    period_id: str
    warmup: str = ""
    teacher_script: str = ""
    blackboard_notes: str = ""
    checkpoint_questions: list[str] = Field(default_factory=list)
    exit_ticket: str = ""
    homework: str = ""
    mentor_moment: str = ""  # motivational anecdote or real-world connection
    supporting_resources: list[str] = Field(default_factory=list)


# ── activities ───────────────────────────────────────────────────────────────


class Activity(BaseModel):
    """Stage 6 output — one classroom activity."""

    id: str = Field(default_factory=_uid)
    title: str
    activity_type: ActivityType = ActivityType.DISCUSSION
    duration_minutes: int = 15
    materials: list[str] = Field(default_factory=list)
    teacher_instructions: str = ""
    expected_student_response: str = ""
    success_criteria: str = ""
    linked_period_ids: list[str] = Field(default_factory=list)
    linked_concept_ids: list[str] = Field(default_factory=list)
    origin: Origin = Origin.PEDAGOGICAL


# ── assessments ──────────────────────────────────────────────────────────────


class MCQOption(BaseModel):
    key: str  # "A", "B", "C", "D"
    text: str


class MCQItem(BaseModel):
    id: str = Field(default_factory=_uid)
    stem: str
    options: list[MCQOption] = Field(default_factory=list)
    correct_key: str = ""
    explanation: str = ""
    difficulty: Difficulty = Difficulty.INTERMEDIATE
    bloom_level: BloomLevel = BloomLevel.UNDERSTAND
    linked_concept_ids: list[str] = Field(default_factory=list)
    marks: int = 1


class ShortAnswerItem(BaseModel):
    id: str = Field(default_factory=_uid)
    question: str
    model_answer: str = ""
    key_points: list[str] = Field(default_factory=list)
    marks: int = 2
    linked_concept_ids: list[str] = Field(default_factory=list)
    rubric: dict[str, int] = Field(default_factory=dict)


class LongAnswerItem(BaseModel):
    id: str = Field(default_factory=_uid)
    question: str
    marking_scheme: str = ""
    word_limit: int = 250
    marks: int = 5
    linked_concept_ids: list[str] = Field(default_factory=list)
    rubric: dict[str, int] = Field(default_factory=dict)


class NumericalItem(BaseModel):
    id: str = Field(default_factory=_uid)
    question: str
    answer: str = ""
    unit: str = ""
    solution_steps: list[str] = Field(default_factory=list)
    marks: int = 3
    linked_concept_ids: list[str] = Field(default_factory=list)
    tolerance: float = 0.01


class AssessmentItem(BaseModel):
    mcqs: list[MCQItem] = Field(default_factory=list)
    short_answers: list[ShortAnswerItem] = Field(default_factory=list)
    long_answers: list[LongAnswerItem] = Field(default_factory=list)
    numericals: list[NumericalItem] = Field(default_factory=list)
    total_marks: int = 0
    coverage_map: dict[str, list[str]] = Field(
        default_factory=dict
    )  # concept_id → question ids


class AssessmentPack(BaseModel):
    """Stage 7 output.

    May hold one combined set or be split into formative / summative sections.
    """

    items: AssessmentItem = Field(default_factory=AssessmentItem)
    answer_key: dict[str, str] = Field(default_factory=dict)
    blueprint: dict[str, int] = Field(default_factory=dict)  # Blooms → mark weight


# ── gap analysis ─────────────────────────────────────────────────────────────


class MisconceptionAnalysis(BaseModel):
    """Stage 8 output for one diagnosed misconception."""

    id: str = Field(default_factory=_uid)
    misconception: str
    severity: Severity = Severity.MEDIUM
    diagnostic_question: str = ""
    expected_wrong_answer: str = ""
    remedial_action: str = ""
    linked_concept_ids: list[str] = Field(default_factory=list)


class GapAnalysis(BaseModel):
    misconceptions: list[MisconceptionAnalysis] = Field(default_factory=list)
    coverage_score: float = 0.0  # 0-1
    remediation_summary: str = ""


# ── validation ───────────────────────────────────────────────────────────────


class SchemaCheck(BaseModel):
    status: ValidationStatus = ValidationStatus.PASS
    missing_fields: list[str] = Field(default_factory=list)
    extra_fields: list[str] = Field(default_factory=list)


class GroundingCheck(BaseModel):
    status: ValidationStatus = ValidationStatus.PASS
    ungrounded_claims: list[str] = Field(default_factory=list)
    hallucination_risk: float = 0.0  # 0-1


class ConsistencyCheck(BaseModel):
    status: ValidationStatus = ValidationStatus.PASS
    issues: list[str] = Field(default_factory=list)


class PedagogicalCheck(BaseModel):
    status: ValidationStatus = ValidationStatus.PASS
    notes: list[str] = Field(default_factory=list)
    bloom_distribution: dict[str, int] = Field(default_factory=dict)


class ValidationRecord(BaseModel):
    """Stage 9 output."""

    schema_check: SchemaCheck = Field(default_factory=SchemaCheck)
    grounding_check: GroundingCheck = Field(default_factory=GroundingCheck)
    consistency_check: ConsistencyCheck = Field(default_factory=ConsistencyCheck)
    pedagogical_check: PedagogicalCheck = Field(default_factory=PedagogicalCheck)
    overall_status: ValidationStatus = ValidationStatus.PASS
    regen_suggestions: list[str] = Field(default_factory=list)


# ── publishing / top-level package ───────────────────────────────────────────


class ExportManifest(BaseModel):
    json_path: str = ""
    lesson_plan_pdf_path: str = ""
    teacher_guide_pdf_path: str = ""
    assessment_pack_pdf_path: str = ""

class AgentTraceRecord(BaseModel):
    agent_role: str
    stage: str
    input_summary: str
    output_summary: str
    duration_ms: int
    tokens_used: int
    model_used: str
    messages: list[dict[str, Any]] = Field(default_factory=list)


class CurriculumStandardRef(BaseModel):
    code: str
    description: str
    board: str
    confidence: float


class CurriculumAlignment(BaseModel):
    board: str
    standards_matched: list[CurriculumStandardRef] = Field(default_factory=list)
    coverage_pct: float = 0.0
    gaps: list[str] = Field(default_factory=list)
    alignment_map: dict[str, list[CurriculumStandardRef]] = Field(default_factory=dict)


class LLMCallMetric(BaseModel):
    stage: str
    provider: str
    model: str
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    cached: bool
    attempt: int
    cost_estimate: float = 0.0
    status: str = "success"


class TelemetryRecord(BaseModel):
    total_duration_ms: int = 0
    stage_timings: dict[str, int] = Field(default_factory=dict)
    llm_calls: list[LLMCallMetric] = Field(default_factory=list)
    total_cost_estimate: float = 0.0
    provider_stats: dict[str, dict[str, int]] = Field(default_factory=dict)
    retry_count: int = 0
    cache_hit_rate: float = 0.0


class PackageMeta(BaseModel):
    job_id: str = ""
    created_at: str = Field(default_factory=_now)
    pipeline_version: str = "1.0.0"
    source_file: str = ""
    processing_time_seconds: float = 0.0
    model_calls: int = 0
    total_tokens_used: int = 0
    models_used: list[str] = Field(default_factory=list)
    # True when the offline stub produced this package. Consumers must not treat
    # demo output as real model output.
    demo_mode: bool = False
    
    # Bonus features
    agent_traces: list[AgentTraceRecord] = Field(default_factory=list)
    telemetry: TelemetryRecord | None = None
    rag_stats: dict[str, Any] = Field(default_factory=dict)
    performance_stats: dict[str, Any] = Field(default_factory=dict)


class TeacherKnowledgePackage(BaseModel):
    """Canonical Stage 10 output — the final TKP."""

    metadata: PackageMeta = Field(default_factory=PackageMeta)
    document_intelligence: DocumentIntelligenceResult | None = None
    document_profile: DocumentProfile | None = None
    knowledge_extraction: KnowledgeExtractionResult | None = None
    teaching_plan: TeachingPlan | None = None
    classroom_content: list[ClassroomContent] = Field(default_factory=list)
    activities: list[Activity] = Field(default_factory=list)
    assessments: AssessmentPack | None = None
    gap_analysis: GapAnalysis | None = None
    validation: ValidationRecord | None = None
    curriculum_alignment: CurriculumAlignment | None = None
    exports: ExportManifest = Field(default_factory=ExportManifest)

    def summary(self) -> dict[str, Any]:
        """Compact summary for the frontend overview tab."""
        dp = self.document_profile
        tp = self.teaching_plan
        return {
            "subject": dp.subject if dp else "",
            "grade": dp.grade if dp else "",
            "topic": dp.topic if dp else "",
            "periods": tp.total_periods if tp else 0,
            "concepts": len(self.knowledge_extraction.concepts)
            if self.knowledge_extraction
            else 0,
            "activities": len(self.activities),
            "mcqs": len(self.assessments.items.mcqs) if self.assessments else 0,
            "short_answers": len(self.assessments.items.short_answers)
            if self.assessments
            else 0,
            "misconceptions": len(self.gap_analysis.misconceptions)
            if self.gap_analysis
            else 0,
            "validation": self.validation.overall_status.value if self.validation else "unchecked",
        }


# ── job model ────────────────────────────────────────────────────────────────


class StageProgress(BaseModel):
    stage: StageName
    label: str
    progress_pct: int = 0
    status: JobStatus = JobStatus.QUEUED
    message: str = ""
    started_at: str | None = None
    finished_at: str | None = None


class JobRecord(BaseModel):
    id: str = Field(default_factory=_uid)
    file_name: str = ""
    file_type: str = ""
    file_size_bytes: int = 0
    document_hint: DocumentHint = DocumentHint.NOT_SURE
    user_context: dict[str, Any] = Field(default_factory=dict)
    status: JobStatus = JobStatus.QUEUED
    stages: list[StageProgress] = Field(default_factory=list)
    current_stage: StageName | None = None
    progress_pct: float = 0.0
    error_message: str = ""
    result: TeacherKnowledgePackage | None = None
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
