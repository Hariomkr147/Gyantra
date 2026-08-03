"""Maps pipeline stages onto logical model roles.

Concrete model IDs live on the provider classes, so switching providers or
models never touches the orchestrator.
"""

from __future__ import annotations

from enum import Enum


class ModelRole(str, Enum):
    FAST = "fast"          # classification, routing, small structured decisions
    EXTRACT = "extract"    # knowledge extraction, gap analysis
    PLAN = "plan"          # teaching planning and sequencing
    GENERATE = "generate"  # content, activities, assessments
    VALIDATE = "validate"  # grounding audit


STAGE_TO_ROLE: dict[str, ModelRole] = {
    "classification": ModelRole.FAST,
    "knowledge_extraction": ModelRole.EXTRACT,
    "teaching_plan": ModelRole.PLAN,
    "classroom_content": ModelRole.GENERATE,
    "activities": ModelRole.GENERATE,
    "assessments": ModelRole.GENERATE,
    "gap_analysis": ModelRole.EXTRACT,
    "validation": ModelRole.VALIDATE,
}


def role_for_stage(stage: str) -> str:
    """Logical role for a pipeline stage. Unknown stages get the general model."""
    return STAGE_TO_ROLE.get(stage, ModelRole.GENERATE).value
