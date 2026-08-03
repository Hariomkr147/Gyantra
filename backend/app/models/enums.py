"""Shared enums used across pipeline schemas."""

from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StageName(str, Enum):
    """The 10 canonical pipeline stages, in execution order."""

    DOCUMENT_INTELLIGENCE = "document_intelligence"
    CLASSIFICATION = "classification"
    KNOWLEDGE_EXTRACTION = "knowledge_extraction"
    TEACHING_PLAN = "teaching_plan"
    CLASSROOM_CONTENT = "classroom_content"
    ACTIVITIES = "activities"
    ASSESSMENTS = "assessments"
    GAP_ANALYSIS = "gap_analysis"
    VALIDATION = "validation"
    PUBLISHING = "publishing"


STAGE_LABELS: dict[str, str] = {
    StageName.DOCUMENT_INTELLIGENCE: "Document Intelligence",
    StageName.CLASSIFICATION: "Educational Classification",
    StageName.KNOWLEDGE_EXTRACTION: "Knowledge Extraction",
    StageName.TEACHING_PLAN: "Teaching Planner",
    StageName.CLASSROOM_CONTENT: "Classroom Content",
    StageName.ACTIVITIES: "Activity Generation",
    StageName.ASSESSMENTS: "Assessment Generation",
    StageName.GAP_ANALYSIS: "Learning Gap Analysis",
    StageName.VALIDATION: "Validation",
    StageName.PUBLISHING: "Publishing",
}

# Progress percentage each stage ends at. Used by the orchestrator so the
# frontend stepper advances predictably.
STAGE_PROGRESS: dict[str, tuple[int, int]] = {
    StageName.DOCUMENT_INTELLIGENCE: (0, 10),
    StageName.CLASSIFICATION: (10, 16),
    StageName.KNOWLEDGE_EXTRACTION: (16, 34),
    StageName.TEACHING_PLAN: (34, 44),
    StageName.CLASSROOM_CONTENT: (44, 62),
    StageName.ACTIVITIES: (62, 72),
    StageName.ASSESSMENTS: (72, 84),
    StageName.GAP_ANALYSIS: (84, 90),
    StageName.VALIDATION: (90, 96),
    StageName.PUBLISHING: (96, 100),
}


class DocumentHint(str, Enum):
    """User-supplied hint that drives cost-aware parser routing (FAQ Q7)."""

    MOSTLY_TEXT = "mostly_text"
    TEXT_WITH_TABLES = "text_with_tables"
    TEXT_WITH_DIAGRAMS = "text_with_diagrams"
    TEXT_WITH_EQUATIONS = "text_with_equations"
    SCANNED_PDF = "scanned_pdf"
    NOT_SURE = "not_sure"


class ParseRoute(str, Enum):
    """Parsing strategy chosen by the router."""

    LIGHTWEIGHT_TEXT = "lightweight_text"
    STRUCTURED_TABLES = "structured_tables"
    LAYOUT_AWARE = "layout_aware"
    EQUATION_PRESERVING = "equation_preserving"
    OCR = "ocr"


class BlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    FIGURE = "figure"
    EQUATION = "equation"
    LIST = "list"
    CAPTION = "caption"


class Origin(str, Enum):
    """Provenance tag. The grounding contract depends on this distinction.

    SOURCE  -> factual/conceptual content traceable to the uploaded document.
    PEDAGOGICAL -> teaching scaffolding (analogies, activity framing, pacing)
                   added by the model. Must not introduce new subject matter.
    """

    SOURCE = "source"
    PEDAGOGICAL = "pedagogical"


class Difficulty(str, Enum):
    FOUNDATIONAL = "foundational"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class BloomLevel(str, Enum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"


class ActivityType(str, Enum):
    DISCUSSION = "discussion"
    DEMONSTRATION = "demonstration"
    EXPERIMENT = "experiment"
    ROLE_PLAY = "role_play"
    WORKSHEET = "worksheet"
    GROUP_TASK = "group_task"
    BOARD_WORK = "board_work"
    THINK_PAIR_SHARE = "think_pair_share"
    CASE_STUDY = "case_study"


class QuestionType(str, Enum):
    MCQ = "mcq"
    SHORT_ANSWER = "short_answer"
    LONG_ANSWER = "long_answer"
    NUMERICAL = "numerical"
    TRUE_FALSE = "true_false"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ValidationStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
