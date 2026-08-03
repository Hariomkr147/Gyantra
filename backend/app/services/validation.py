"""
Stage 9 — Validation engine.

Four independent checks:
  1. Schema      — required fields present and non-empty (deterministic).
  2. Consistency — cross-stage reference integrity (deterministic).
  3. Pedagogical — coverage, Bloom spread, activity variety (deterministic).
  4. Grounding   — do generated claims stay inside the source's subject scope?
                   Deterministic lexical pre-filter + one LLM audit pass.

Deterministic checks run first and are always reliable.  The LLM is used only
where judgement is genuinely needed, which keeps validation cheap and stable.
"""

from __future__ import annotations

import logging
import re

from app.models.enums import ValidationStatus
from app.models.schemas import (
    ConsistencyCheck,
    GroundingCheck,
    PedagogicalCheck,
    SchemaCheck,
    TeacherKnowledgePackage,
    ValidationRecord,
)
from app.services import prompts
from app.services.llm_client import LLMClient, LLMError

logger = logging.getLogger("gyantra.validation")

# Words that carry no subject meaning — excluded from grounding comparison.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "than", "of", "in", "on",
    "at", "to", "for", "with", "by", "from", "as", "is", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "can", "could", "should", "may", "might", "must", "this", "that",
    "these", "those", "it", "its", "they", "them", "their", "we", "us", "our",
    "you", "your", "he", "she", "his", "her", "not", "no", "so", "such", "what",
    "which", "who", "how", "when", "where", "why", "all", "any", "each", "more",
    "most", "some", "other", "into", "about", "also", "very", "just", "only",
    "student", "students", "teacher", "teachers", "class", "classroom", "lesson",
    "period", "activity", "question", "answer", "example", "understand", "learn",
    "explain", "discuss", "write", "read", "ask", "tell", "show", "use", "make",
    "one", "two", "three", "first", "second", "next", "last", "new", "own",
}

_WORD = re.compile(r"[a-z][a-z\-]{2,}")

# Suffixes stripped before comparing words, longest first.  Without this,
# "newtons" in generated content looks ungrounded against "Newton's" in the
# source, producing false hallucination flags on correct material.
_SUFFIXES = (
    "ational", "ization", "iveness", "fulness", "ousness", "ations", "ition",
    "ingly", "ement", "ities", "ances", "ences", "ments", "ising", "izing",
    "ional", "ness", "less", "able", "ible", "ally", "edly", "ance", "ence",
    "ment", "tion", "sion", "ing", "ies", "ied", "est", "ers", "ity", "ive",
    "ise", "ize", "ous", "ial", "ial", "er", "ed", "es", "ly", "al", "s",
)


def _stem(word: str) -> str:
    """Crude suffix stripper — cheap, deterministic, and good enough here.

    We only need two word forms to collide, not linguistic correctness.
    """
    word = word.replace("-", "")
    for suffix in _SUFFIXES:
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word

# Content that is explicitly allowed to go beyond the source, because it is
# teaching scaffolding rather than subject matter (FAQ Q4).
PEDAGOGICAL_FIELDS = {"mentor_moment", "warmup", "activities", "applications"}


def _tokens(text: str) -> set[str]:
    """Content words, stemmed, with stopwords removed."""
    return {
        _stem(w)
        for w in _WORD.findall(text.lower())
        if w not in _STOPWORDS
    }


# ── check 1: schema ──────────────────────────────────────────────────────────


def check_schema(pkg: TeacherKnowledgePackage) -> SchemaCheck:
    """Required-field presence. Pydantic already guarantees types."""
    missing: list[str] = []

    if not pkg.document_profile or not pkg.document_profile.subject:
        missing.append("document_profile.subject")
    if not pkg.knowledge_extraction:
        missing.append("knowledge_extraction")
    else:
        ke = pkg.knowledge_extraction
        if not ke.learning_objectives:
            missing.append("knowledge_extraction.learning_objectives")
        if not ke.concepts:
            missing.append("knowledge_extraction.concepts")
    if not pkg.teaching_plan or not pkg.teaching_plan.periods:
        missing.append("teaching_plan.periods")
    if not pkg.classroom_content:
        missing.append("classroom_content")
    else:
        for i, c in enumerate(pkg.classroom_content):
            if not c.teacher_script.strip():
                missing.append(f"classroom_content[{i}].teacher_script")
            if not c.blackboard_notes.strip():
                missing.append(f"classroom_content[{i}].blackboard_notes")
    if not pkg.activities:
        missing.append("activities")
    if not pkg.assessments or not pkg.assessments.items.mcqs:
        missing.append("assessments.items.mcqs")
    if not pkg.gap_analysis or not pkg.gap_analysis.misconceptions:
        missing.append("gap_analysis.misconceptions")

    status = ValidationStatus.PASS
    if missing:
        # Missing core knowledge is fatal; missing extras is a warning.
        fatal = any(
            m.startswith(("knowledge_extraction", "teaching_plan", "document_profile"))
            for m in missing
        )
        status = ValidationStatus.FAIL if fatal else ValidationStatus.WARN

    return SchemaCheck(status=status, missing_fields=missing)


# ── check 2: consistency ─────────────────────────────────────────────────────


def check_consistency(pkg: TeacherKnowledgePackage) -> ConsistencyCheck:
    """Cross-stage reference integrity."""
    issues: list[str] = []
    ke = pkg.knowledge_extraction
    plan = pkg.teaching_plan

    if not ke or not plan:
        return ConsistencyCheck(
            status=ValidationStatus.FAIL,
            issues=["Cannot check consistency: extraction or plan missing"],
        )

    concept_ids = {c.id for c in ke.concepts}
    period_ids = {p.id for p in plan.periods}

    # Every concept should be taught somewhere.
    planned = {cid for p in plan.periods for cid in p.key_concepts}
    orphans = concept_ids - planned
    if orphans:
        names = [c.name for c in ke.concepts if c.id in orphans][:5]
        issues.append(
            f"{len(orphans)} extracted concept(s) are not covered by any period: "
            + ", ".join(names)
        )

    # No period should reference a concept that doesn't exist.
    for p in plan.periods:
        unknown = [cid for cid in p.key_concepts if cid not in concept_ids]
        if unknown:
            issues.append(f"Period {p.number} references {len(unknown)} unknown concept id(s)")

    # Content must exist for every period, and only for real periods.
    content_period_ids = {c.period_id for c in pkg.classroom_content}
    missing_content = period_ids - content_period_ids
    if missing_content:
        issues.append(f"{len(missing_content)} period(s) have no generated content")
    stray_content = content_period_ids - period_ids
    if stray_content:
        issues.append(f"{len(stray_content)} content block(s) reference non-existent periods")

    # Activities should point at real periods and concepts.
    for a in pkg.activities:
        bad_periods = [p for p in a.linked_period_ids if p not in period_ids]
        bad_concepts = [c for c in a.linked_concept_ids if c not in concept_ids]
        if bad_periods or bad_concepts:
            issues.append(f"Activity '{a.title[:40]}' has dangling references")

    # Prerequisite graph must be acyclic.
    if _has_cycle(ke.concept_graph):
        issues.append("Concept prerequisite graph contains a cycle")

    # Assessment coverage of core concepts.
    if pkg.assessments:
        assessed = set(pkg.assessments.items.coverage_map.keys())
        core = {c.id for c in ke.concepts if c.is_core}
        unassessed_core = core - assessed
        if unassessed_core:
            names = [c.name for c in ke.concepts if c.id in unassessed_core][:5]
            issues.append(
                f"{len(unassessed_core)} core concept(s) have no assessment item: "
                + ", ".join(names)
            )

    status = ValidationStatus.PASS
    if issues:
        status = ValidationStatus.FAIL if len(issues) > 4 else ValidationStatus.WARN
    return ConsistencyCheck(status=status, issues=issues)


def _has_cycle(graph: dict[str, list[str]]) -> bool:
    """DFS cycle detection over the prerequisite graph."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour: dict[str, int] = {}

    def visit(node: str) -> bool:
        state = colour.get(node, WHITE)
        if state == GREY:
            return True
        if state == BLACK:
            return False
        colour[node] = GREY
        for parent in graph.get(node, []):
            if visit(parent):
                return True
        colour[node] = BLACK
        return False

    return any(visit(n) for n in list(graph))


# ── check 3: pedagogical completeness ────────────────────────────────────────


def check_pedagogical(pkg: TeacherKnowledgePackage) -> PedagogicalCheck:
    """Coverage, Bloom distribution, and activity variety."""
    notes: list[str] = []
    bloom: dict[str, int] = {}

    ke = pkg.knowledge_extraction
    if not ke:
        return PedagogicalCheck(
            status=ValidationStatus.FAIL, notes=["No knowledge extraction to evaluate"]
        )

    # Bloom spread across assessments.
    if pkg.assessments:
        for m in pkg.assessments.items.mcqs:
            bloom[m.bloom_level.value] = bloom.get(m.bloom_level.value, 0) + 1
        total_items = (
            len(pkg.assessments.items.mcqs)
            + len(pkg.assessments.items.short_answers)
            + len(pkg.assessments.items.long_answers)
            + len(pkg.assessments.items.numericals)
        )
        if total_items < 6:
            notes.append(f"Only {total_items} assessment items generated; consider more coverage")

        lower = bloom.get("remember", 0) + bloom.get("understand", 0)
        if bloom and lower == sum(bloom.values()):
            notes.append(
                "All MCQs sit at recall/understanding level; higher-order items would strengthen the pack"
            )

    # Activity variety.
    kinds = {a.activity_type.value for a in pkg.activities}
    if pkg.activities and len(kinds) < 3:
        notes.append(
            f"Activity variety is low ({len(kinds)} type(s)): {', '.join(sorted(kinds))}"
        )

    # Per-period completeness.
    for c in pkg.classroom_content:
        gaps = [
            name
            for name, val in (
                ("warm-up", c.warmup),
                ("exit ticket", c.exit_ticket),
                ("homework", c.homework),
                ("mentor moment", c.mentor_moment),
            )
            if not val.strip()
        ]
        if gaps:
            notes.append(f"A period is missing: {', '.join(gaps)}")
        if len(c.checkpoint_questions) < 2:
            notes.append("A period has fewer than 2 checkpoint questions")

    # Objective coverage.
    if pkg.teaching_plan:
        with_objectives = sum(1 for p in pkg.teaching_plan.periods if p.objectives)
        if with_objectives < len(pkg.teaching_plan.periods):
            notes.append("Some periods have no stated learning objectives")

    # Misconception coverage.
    if pkg.gap_analysis and pkg.gap_analysis.coverage_score < 0.3:
        notes.append(
            f"Gap analysis covers only {pkg.gap_analysis.coverage_score:.0%} of concepts"
        )

    status = ValidationStatus.PASS
    if len(notes) > 6:
        status = ValidationStatus.FAIL
    elif notes:
        status = ValidationStatus.WARN

    return PedagogicalCheck(status=status, notes=notes[:15], bloom_distribution=bloom)


# ── check 4: grounding ───────────────────────────────────────────────────────


def _collect_claims(pkg: TeacherKnowledgePackage) -> list[str]:
    """Gather factual statements worth auditing.

    Deliberately excludes fields tagged as pedagogical support — those are
    allowed to go beyond the source per the FAQ.
    """
    claims: list[str] = []

    for c in pkg.classroom_content:
        # Split the teacher script into sentences and keep substantive ones.
        for sentence in re.split(r"(?<=[.!?])\s+", c.teacher_script):
            s = sentence.strip()
            if len(s) > 60 and _tokens(s):
                claims.append(s)
        for line in c.blackboard_notes.split("\n"):
            s = line.strip(" -•\t")
            if len(s) > 40:
                claims.append(s)

    if pkg.assessments:
        for m in pkg.assessments.items.mcqs:
            claims.append(m.stem)
        for s in pkg.assessments.items.short_answers:
            if s.model_answer:
                claims.append(s.model_answer)

    return claims


def check_grounding_lexical(
    pkg: TeacherKnowledgePackage, claims: list[str]
) -> tuple[list[str], float]:
    """Cheap lexical pre-filter for ungrounded content.

    Builds a vocabulary from the source document and flags claims that introduce
    a high proportion of unseen subject terms.  This catches obvious drift
    without an LLM call and produces the shortlist the LLM then audits.
    """
    di = pkg.document_intelligence
    ke = pkg.knowledge_extraction
    if not di or not ke:
        return [], 0.0

    # Source vocabulary: the document itself plus everything extraction found.
    vocab = _tokens(di.plain_text)
    for c in ke.concepts:
        vocab |= _tokens(c.name) | _tokens(c.description)
    for d in ke.definitions:
        vocab |= _tokens(d.term) | _tokens(d.text)
    for k in ke.keywords:
        vocab |= _tokens(k)
    for f in ke.formulas:
        vocab |= _tokens(f.name) | _tokens(f.explanation)
    for e in ke.examples:
        vocab |= _tokens(e.text)

    suspicious: list[str] = []
    for claim in claims:
        claim_tokens = _tokens(claim)
        # Below 3 content words the ratio is too noisy to mean anything, but a
        # short sentence can still smuggle in off-topic subject matter.
        if len(claim_tokens) < 3:
            continue
        unseen = claim_tokens - vocab
        ratio = len(unseen) / len(claim_tokens)
        # >45% unfamiliar subject words suggests content not in the source.
        if ratio > 0.45:
            suspicious.append(claim[:300])

    risk = len(suspicious) / len(claims) if claims else 0.0
    return suspicious[:25], round(risk, 3)


async def check_grounding(
    client: LLMClient | None,
    pkg: TeacherKnowledgePackage,
) -> GroundingCheck:
    """Lexical pre-filter, then an LLM audit of the shortlist."""
    claims = _collect_claims(pkg)
    if not claims:
        return GroundingCheck(status=ValidationStatus.WARN, hallucination_risk=0.0)

    suspicious, lexical_risk = check_grounding_lexical(pkg, claims)

    if not suspicious:
        return GroundingCheck(status=ValidationStatus.PASS, hallucination_risk=0.0)

    # Ask the model to confirm which shortlisted claims are genuinely ungrounded.
    confirmed = suspicious
    llm_risk = lexical_risk

    if client is not None:
        ke = pkg.knowledge_extraction
        try:
            data = await client.complete_json(
                stage="validation",
                system_prompt=prompts.VALIDATE_SYSTEM,
                user_prompt=prompts.VALIDATE_USER.format(
                    concepts=", ".join(c.name for c in ke.concepts)[:1500] if ke else "",
                    definitions="; ".join(f"{d.term}: {d.text[:80]}" for d in ke.definitions[:15])[:1500] if ke else "",
                    keywords=", ".join(ke.keywords[:40])[:800] if ke else "",
                    claims="\n".join(f"- {c}" for c in suspicious[:15]),
                ),
                max_tokens=1200,
                temperature=0.0,
            )
            if isinstance(data, dict):
                reported = data.get("ungrounded_claims")
                if isinstance(reported, list):
                    confirmed = [str(c)[:300] for c in reported if str(c).strip()]
                risk_val = data.get("hallucination_risk")
                if isinstance(risk_val, (int, float)):
                    # Scale the audited-subset risk back to the whole claim set.
                    llm_risk = round(
                        float(risk_val) * (len(suspicious) / len(claims)), 3
                    )
        except LLMError as exc:
            logger.warning("LLM grounding audit failed, using lexical result: %s", exc)

    if not confirmed:
        return GroundingCheck(status=ValidationStatus.PASS, hallucination_risk=0.0)

    status = ValidationStatus.PASS
    if llm_risk > 0.25:
        status = ValidationStatus.FAIL
    elif llm_risk > 0.08 or confirmed:
        status = ValidationStatus.WARN

    return GroundingCheck(
        status=status,
        ungrounded_claims=confirmed[:20],
        hallucination_risk=llm_risk,
    )


# ── orchestration ────────────────────────────────────────────────────────────


def _worst(*statuses: ValidationStatus) -> ValidationStatus:
    if ValidationStatus.FAIL in statuses:
        return ValidationStatus.FAIL
    if ValidationStatus.WARN in statuses:
        return ValidationStatus.WARN
    return ValidationStatus.PASS


async def validate_package(
    pkg: TeacherKnowledgePackage,
    client: LLMClient | None = None,
) -> ValidationRecord:
    """Run all four checks and produce the validation record."""
    schema = check_schema(pkg)
    consistency = check_consistency(pkg)
    pedagogical = check_pedagogical(pkg)
    grounding = await check_grounding(client, pkg)

    overall = _worst(
        schema.status, consistency.status, pedagogical.status, grounding.status
    )

    suggestions: list[str] = []
    if schema.missing_fields:
        suggestions.append(
            "Regenerate the stages that produced empty required fields: "
            + ", ".join(sorted({f.split(".")[0] for f in schema.missing_fields}))
        )
    if grounding.ungrounded_claims:
        suggestions.append(
            "Review the flagged claims against the source; regenerate classroom "
            "content with tighter grounding if they introduce new subject matter."
        )
    if any("not covered by any period" in i for i in consistency.issues):
        suggestions.append("Re-run the teaching planner so every concept is scheduled.")
    if any("variety is low" in n for n in pedagogical.notes):
        suggestions.append("Regenerate activities requesting a wider mix of activity types.")

    return ValidationRecord(
        schema_check=schema,
        grounding_check=grounding,
        consistency_check=consistency,
        pedagogical_check=pedagogical,
        overall_status=overall,
        regen_suggestions=suggestions,
    )
