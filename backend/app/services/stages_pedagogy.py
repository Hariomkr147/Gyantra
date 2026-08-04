"""
Stages 4-8 — Teaching Planner, Classroom Content, Activities, Assessments,
Learning Gap Analysis.

Token discipline in this module:
 - The planner sees only the structured concept list, never raw document text.
 - Content generation retrieves only the chunks relevant to its own period.
 - Assessment generation sees concepts + definitions, plus a small snippet set.
"""

from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.models.enums import (
    ActivityType,
    BloomLevel,
    Difficulty,
    Origin,
    Severity,
)
from app.models.schemas import (
    Activity,
    AssessmentItem,
    AssessmentPack,
    ClassroomContent,
    DocumentProfile,
    GapAnalysis,
    KnowledgeExtractionResult,
    LongAnswerItem,
    MCQItem,
    MCQOption,
    MisconceptionAnalysis,
    NumericalItem,
    PeriodObjective,
    PeriodPlan,
    ShortAnswerItem,
    TeachingPlan,
)
from app.services import prompts
from app.services.chunker import Chunk, SectionIndex
from app.services.llm_client import LLMClient, LLMError
from app.services.stages_knowledge import _safe_enum

def _safe_int(val: Any, default: int) -> int:
    try:
        if val is None:
            return default
        s = str(val).strip().split()[0].replace(",", "")
        return int(float(s))
    except (ValueError, TypeError, IndexError, AttributeError):
        return default

def _safe_list(val: Any) -> list:
    if isinstance(val, list):
        return val
    return []
def _get_lang_inst(profile: DocumentProfile) -> str:
    lang = profile.language.lower() if profile.language else "en"
    if lang.startswith("en") or lang == "english":
        return ""
    return prompts.LANGUAGE_INSTRUCTION.format(language=profile.language)

logger = logging.getLogger("gyantra.stages.pedagogy")

# Subjects where numerical problems make sense.
_QUANTITATIVE_HINTS = (
    "math", "physic", "chemis", "account", "statistic", "econom",
    "engineer", "comput", "financ",
)


def _is_quantitative(profile: DocumentProfile, knowledge: KnowledgeExtractionResult) -> bool:
    subject = (profile.subject or "").lower()
    if any(h in subject for h in _QUANTITATIVE_HINTS):
        return True
    # A document with real formulas is quantitative regardless of subject label.
    return len(knowledge.formulas) >= 2


# ── Stage 4: teaching planner ────────────────────────────────────────────────


async def build_teaching_plan(
    client: LLMClient,
    profile: DocumentProfile,
    knowledge: KnowledgeExtractionResult,
    chunks: list[Chunk],
    user_context: dict,
) -> TeachingPlan:
    """Produce an adaptive period plan.

    Explicitly does NOT default to 5 periods — the FAQ requires the count to
    follow content volume and complexity.
    """
    concept_lines = "\n".join(
        f"- {c.id} → {c.name} — {c.difficulty.value}"
        + (" [core]" if c.is_core else "")
        for c in knowledge.concepts
    ) or "(no concepts extracted)"

    objectives = "\n".join(f"- {o}" for o in knowledge.learning_objectives) or "(none)"
    prereqs = "\n".join(f"- {p}" for p in knowledge.prerequisites_list) or "(none stated)"

    constraint_bits = []
    if user_context.get("period_minutes"):
        constraint_bits.append(f"each period is {user_context['period_minutes']} minutes")
    if user_context.get("total_periods_available"):
        constraint_bits.append(
            f"teacher has about {user_context['total_periods_available']} periods available"
        )
    if user_context.get("teaching_style"):
        constraint_bits.append(f"preferred teaching style: {user_context['teaching_style']}")
    if user_context.get("time_constraints"):
        constraint_bits.append(str(user_context["time_constraints"]))
    constraints = "; ".join(constraint_bits) or "no specific constraints given"

    word_count = sum(len(c.text.split()) for c in chunks)

    user_prompt = prompts.PLAN_USER.format(
        subject=profile.subject,
        grade=profile.grade,
        topic=profile.topic,
        difficulty=profile.difficulty.value,
        chunk_count=len(chunks),
        word_count=word_count,
        constraints=constraints,
        objectives=objectives,
        concepts=concept_lines,
        prerequisites=prereqs,
    )

    try:
        data = await client.complete_json(
            stage="teaching_plan",
            system_prompt=prompts.PLAN_SYSTEM,
            user_prompt=user_prompt + "\n\nCRITICAL: You must respond with ONLY raw, valid JSON. Do not include markdown formatting, preambles, or explanations. If you include quotation marks inside your JSON string values (such as dialogue or quotes), you MUST use single quotes (') instead of double quotes (\") to ensure the JSON is valid.",
            json_schema={"type": "object"},
            max_tokens=2600,
        )
    except LLMError as exc:
        logger.error("planning failed, using heuristic plan: %s", exc)
        return _heuristic_plan(profile, knowledge, user_context)

    if not isinstance(data, dict) or not data.get("periods"):
        return _heuristic_plan(profile, knowledge, user_context)

    default_minutes = int(
        data.get("default_minutes_per_period")
        or user_context.get("period_minutes")
        or 40
    )

    periods: list[PeriodPlan] = []
    valid_ids = {c.id for c in knowledge.concepts}

    for i, raw in enumerate(data.get("periods") or [], start=1):
        if not isinstance(raw, dict):
            continue
        objectives_raw = raw.get("objectives") or []
        period_objectives = []
        for o in objectives_raw:
            if isinstance(o, dict):
                period_objectives.append(
                    PeriodObjective(
                        text=str(o.get("text", ""))[:300],
                        concept_ids=[
                            str(cid) for cid in (o.get("concept_ids") or [])
                            if str(cid) in valid_ids
                        ],
                    )
                )
            elif str(o).strip():
                period_objectives.append(PeriodObjective(text=str(o)[:300]))

        key_concepts = [
            str(cid) for cid in (raw.get("key_concepts") or []) if str(cid) in valid_ids
        ]

        periods.append(
            PeriodPlan(
                number=int(raw.get("number") or i),
                title=str(raw.get("title") or f"Period {i}")[:200],
                estimated_minutes=int(raw.get("estimated_minutes") or default_minutes),
                objectives=period_objectives,
                key_concepts=key_concepts,
                warmup_strategy=str(raw.get("warmup_strategy", ""))[:400],
                flow_summary=str(raw.get("flow_summary", ""))[:600],
                prerequisite_review=[
                    str(p)[:200] for p in (raw.get("prerequisite_review") or [])
                ],
            )
        )

    if not periods:
        return _heuristic_plan(profile, knowledge, user_context)

    periods.sort(key=lambda p: p.number)
    for i, p in enumerate(periods, start=1):
        p.number = i

    plan = TeachingPlan(
        total_periods=len(periods),
        default_minutes_per_period=default_minutes,
        adaptation_rationale=str(data.get("adaptation_rationale", ""))[:800],
        periods=periods,
        sequence_map={p.number: p.key_concepts for p in periods},
        cross_period_review_points=[
            str(r)[:200] for r in (data.get("cross_period_review_points") or [])
        ],
    )

    _assign_orphan_concepts(plan, knowledge)
    _attach_source_chunks(plan, knowledge, chunks)
    return plan


def _assign_orphan_concepts(plan: TeachingPlan, knowledge: KnowledgeExtractionResult) -> None:
    """Make sure every extracted concept is taught somewhere.

    The planner sometimes drops concepts; validation would flag this, but it's
    cheaper to repair it deterministically here.
    """
    assigned = {cid for p in plan.periods for cid in p.key_concepts}
    orphans = [c for c in knowledge.concepts if c.id not in assigned]
    if not orphans or not plan.periods:
        return

    logger.info("assigning %s orphan concepts to periods", len(orphans))
    # Distribute in extraction order across periods, keeping load balanced.
    for i, concept in enumerate(orphans):
        target = min(plan.periods, key=lambda p: len(p.key_concepts))
        target.key_concepts.append(concept.id)

    plan.sequence_map = {p.number: p.key_concepts for p in plan.periods}


def _attach_source_chunks(
    plan: TeachingPlan, knowledge: KnowledgeExtractionResult, chunks: list[Chunk]
) -> None:
    """Record which source chunks back each period, for traceability + retrieval."""
    by_id = {c.id: c for c in knowledge.concepts}
    for period in plan.periods:
        chunk_ids: set[str] = set()
        for cid in period.key_concepts:
            concept = by_id.get(cid)
            if concept and concept.source_ref:
                chunk_ids.update(concept.source_ref.chunk_ids)
        period.source_chunks = sorted(chunk_ids)


def _heuristic_plan(
    profile: DocumentProfile,
    knowledge: KnowledgeExtractionResult,
    user_context: dict,
) -> TeachingPlan:
    """Deterministic fallback planner used when the LLM call fails.

    Groups concepts into periods by a difficulty-weighted load budget rather
    than a fixed count, so it still honours the 'adaptive' requirement.
    """
    concepts = knowledge.concepts
    minutes = int(user_context.get("period_minutes") or 40)

    if not concepts:
        return TeachingPlan(
            total_periods=1,
            default_minutes_per_period=minutes,
            adaptation_rationale="No concepts were extracted; a single review period is proposed.",
            periods=[
                PeriodPlan(number=1, title=profile.topic or "Introduction", estimated_minutes=minutes)
            ],
        )

    weight = {
        Difficulty.FOUNDATIONAL: 1.0,
        Difficulty.INTERMEDIATE: 1.5,
        Difficulty.ADVANCED: 2.2,
    }
    # A 40-minute period comfortably carries ~4 difficulty-weighted units.
    budget = 4.0 * (minutes / 40)

    periods: list[PeriodPlan] = []
    current: list = []
    load = 0.0

    for concept in concepts:
        w = weight.get(concept.difficulty, 1.5)
        if current and load + w > budget:
            periods.append(_make_period(len(periods) + 1, current, minutes))
            current, load = [], 0.0
        current.append(concept)
        load += w

    if current:
        periods.append(_make_period(len(periods) + 1, current, minutes))

    periods = periods[: settings.max_periods] or [
        _make_period(1, concepts[:4], minutes)
    ]

    return TeachingPlan(
        total_periods=len(periods),
        default_minutes_per_period=minutes,
        adaptation_rationale=(
            f"Generated without the planning model: {len(concepts)} concepts were "
            f"grouped by difficulty weight into {len(periods)} periods of {minutes} minutes."
        ),
        periods=periods,
        sequence_map={p.number: p.key_concepts for p in periods},
    )


def _make_period(number: int, concepts: list, minutes: int) -> PeriodPlan:
    title = concepts[0].name if concepts else f"Period {number}"
    if len(concepts) > 1:
        title = f"{concepts[0].name} and related ideas"
    return PeriodPlan(
        number=number,
        title=title[:200],
        estimated_minutes=minutes,
        key_concepts=[c.id for c in concepts],
        objectives=[
            PeriodObjective(text=f"Understand {c.name}", concept_ids=[c.id])
            for c in concepts[:3]
        ],
        flow_summary=f"Covers: {', '.join(c.name for c in concepts)}"[:600],
    )


# ── Stage 5: classroom content ───────────────────────────────────────────────


async def generate_classroom_content(
    client: LLMClient,
    plan: TeachingPlan,
    profile: DocumentProfile,
    knowledge: KnowledgeExtractionResult,
    index: SectionIndex,
    progress_cb=None,
) -> list[ClassroomContent]:
    """Generate content for each period, one period per LLM call.

    Concurrency is capped so free-tier rate limits don't reject the batch.
    """
    by_id = {c.id: c for c in knowledge.concepts}
    sem = asyncio.Semaphore(settings.parallel_period_generation)
    done = 0

    async def one(period: PeriodPlan) -> ClassroomContent:
        nonlocal done
        async with sem:
            content = await _generate_period_content(
                client, period, plan, profile, by_id, index
            )
            done += 1
            if progress_cb:
                await progress_cb(done, len(plan.periods))
            return content

    return list(await asyncio.gather(*(one(p) for p in plan.periods)))


async def _generate_period_content(
    client: LLMClient,
    period: PeriodPlan,
    plan: TeachingPlan,
    profile: DocumentProfile,
    by_id: dict,
    index: SectionIndex,
) -> ClassroomContent:
    concepts = [by_id[cid] for cid in period.key_concepts if cid in by_id]
    concept_text = "\n".join(f"- {c.name}: {c.description}" for c in concepts) or "(general review)"
    objectives = "\n".join(f"- {o.text}" for o in period.objectives) or "(none specified)"

    # Retrieve only the source relevant to THIS period.
    snippets = _retrieve_snippets(index, period, concepts, max_chars=5000)

    user_prompt = prompts.CONTENT_USER.format(
        period_number=period.number,
        total_periods=plan.total_periods,
        period_title=period.title,
        minutes=period.estimated_minutes,
        subject=profile.subject,
        grade=profile.grade,
        objectives=objectives,
        concepts=concept_text,
        source_snippets=snippets,
        language_instruction=_get_lang_inst(profile),
    )

    try:
        data = await client.complete_json(
            stage="classroom_content",
            system_prompt=prompts.CONTENT_SYSTEM,
            user_prompt=user_prompt + "\n\nCRITICAL: You must respond with ONLY raw, valid JSON. Do not include markdown formatting, preambles, or explanations. If you include quotation marks inside your JSON string values (such as dialogue or quotes), you MUST use single quotes (') instead of double quotes (\") to ensure the JSON is valid.",
            json_schema={"type": "object"},
            max_tokens=2600,
            temperature=0.4,  # a little warmth for teaching prose
        )
    except LLMError as exc:
        logger.error("content generation failed for period %s: %s", period.number, exc)
        data = {}

    if not isinstance(data, dict):
        data = {}

    checkpoints = data.get("checkpoint_questions") or []
    if isinstance(checkpoints, str):
        checkpoints = [checkpoints]

    return ClassroomContent(
        period_id=period.id,
        warmup=str(data.get("warmup", ""))[:1500],
        teacher_script=str(data.get("teacher_script", ""))[:6000],
        blackboard_notes=str(data.get("blackboard_notes", ""))[:3000],
        checkpoint_questions=[str(q)[:400] for q in checkpoints if str(q).strip()][:6],
        exit_ticket=str(data.get("exit_ticket", ""))[:800],
        homework=str(data.get("homework", ""))[:1000],
        mentor_moment=str(data.get("mentor_moment", ""))[:800],
    )


def _retrieve_snippets(
    index: SectionIndex,
    period: PeriodPlan,
    concepts: list,
    max_chars: int = 5000,
) -> str:
    """Pull the smallest set of source text that covers this period.

    Prefers chunks already linked to the period's concepts; falls back to
    keyword retrieval on concept names.
    """
    picked: list[Chunk] = []
    seen: set[str] = set()

    for chunk_id in period.source_chunks:
        chunk = index.chunk_by_id(chunk_id)
        if chunk and chunk.id not in seen:
            picked.append(chunk)
            seen.add(chunk.id)

    if len(picked) < 3:
        for concept in concepts:
            for chunk in index.get_for_concept(concept.name, max_results=2):
                if chunk.id not in seen:
                    picked.append(chunk)
                    seen.add(chunk.id)
            if len(picked) >= 5:
                break

    if not picked:
        picked = index.all_chunks()[:2]

    out: list[str] = []
    total = 0
    for chunk in picked:
        header = f"[{chunk.id}" + (f" — {chunk.heading_path}" if chunk.heading_path else "") + "]"
        body = chunk.text
        remaining = max_chars - total
        if remaining <= 200:
            break
        if len(body) > remaining:
            body = body[:remaining] + "…"
        piece = f"{header}\n{body}"
        out.append(piece)
        total += len(piece)

    return "\n\n".join(out) or "(no source text available)"


# ── Stage 6: activities ──────────────────────────────────────────────────────


async def generate_activities(
    client: LLMClient,
    plan: TeachingPlan,
    profile: DocumentProfile,
    knowledge: KnowledgeExtractionResult,
) -> list[Activity]:
    """Generate a diverse activity set covering the whole plan."""
    # Scale activity count to the plan size, but keep it bounded.
    count = max(3, min(plan.total_periods + 2, 10))

    periods_text = "\n".join(
        f"- {p.id} → Period {p.number}: {p.title}" for p in plan.periods
    )
    concepts_text = "\n".join(
        f"- {c.id} → {c.name}" for c in knowledge.concepts if c.is_core
    ) or "\n".join(f"- {c.id} → {c.name}" for c in knowledge.concepts[:12])

    user_prompt = prompts.ACTIVITY_USER.format(
        count=count,
        subject=profile.subject,
        grade=profile.grade,
        topic=profile.topic,
        periods=periods_text,
        concepts=concepts_text,
        language_instruction=_get_lang_inst(profile),
    )

    try:
        data = await client.complete_json(
            stage="activities",
            system_prompt=prompts.ACTIVITY_SYSTEM,
            user_prompt=user_prompt + "\n\nCRITICAL: You must respond with ONLY raw, valid JSON. Do not include markdown formatting, preambles, or explanations. If you include quotation marks inside your JSON string values (such as dialogue or quotes), you MUST use single quotes (') instead of double quotes (\") to ensure the JSON is valid.",
            json_schema={"type": "object"},
            max_tokens=3000,
            temperature=0.5,  # variety matters here
        )
    except LLMError as exc:
        logger.error("activity generation failed: %s", exc)
        return []

    raw_activities = data.get("activities") if isinstance(data, dict) else data
    if not isinstance(raw_activities, list):
        return []

    valid_period_ids = {p.id for p in plan.periods}
    valid_concept_ids = {c.id for c in knowledge.concepts}

    activities: list[Activity] = []
    for raw in raw_activities:
        if not isinstance(raw, dict) or not raw.get("title"):
            continue
        activities.append(
            Activity(
                title=str(raw["title"])[:200],
                activity_type=_safe_enum(
                    ActivityType, raw.get("activity_type"), ActivityType.DISCUSSION
                ),
                duration_minutes=int(raw.get("duration_minutes") or 15),
                materials=[str(m)[:120] for m in (raw.get("materials") or [])][:12],
                teacher_instructions=str(raw.get("teacher_instructions", ""))[:2500],
                expected_student_response=str(raw.get("expected_student_response", ""))[:1200],
                success_criteria=str(raw.get("success_criteria", ""))[:800],
                linked_period_ids=[
                    str(p) for p in (raw.get("linked_period_ids") or [])
                    if str(p) in valid_period_ids
                ],
                linked_concept_ids=[
                    str(c) for c in (raw.get("linked_concept_ids") or [])
                    if str(c) in valid_concept_ids
                ],
                origin=Origin.PEDAGOGICAL,
            )
        )

    return activities


# ── Stage 7: assessments ─────────────────────────────────────────────────────


async def generate_assessments(
    client: LLMClient,
    profile: DocumentProfile,
    knowledge: KnowledgeExtractionResult,
    index: SectionIndex,
    user_context: dict,
) -> AssessmentPack:
    """Build MCQs, short/long answers and (where relevant) numerical problems."""
    depth = str(user_context.get("assessment_depth") or "balanced")
    quantitative = _is_quantitative(profile, knowledge)

    # Scale item counts with concept count and requested depth.
    n_concepts = max(1, len(knowledge.concepts))
    scale = {"light": 0.6, "balanced": 1.0, "thorough": 1.5}.get(depth, 1.0)
    mcq_count = max(4, min(int(n_concepts * 1.2 * scale), 15))
    short_count = max(3, min(int(n_concepts * 0.7 * scale), 8))
    long_count = max(2, min(int(n_concepts * 0.3 * scale), 5))
    numerical_count = max(2, min(int(n_concepts * 0.5 * scale), 6)) if quantitative else 0

    concepts_text = "\n".join(f"- {c.id} → {c.name}" for c in knowledge.concepts) or "(none)"

    reference_bits = []
    for d in knowledge.definitions[:12]:
        reference_bits.append(f"DEF {d.term}: {d.text}")
    for f in knowledge.formulas[:8]:
        reference_bits.append(f"FORMULA {f.name}: {f.latex} — {f.explanation}")
    reference = "\n".join(reference_bits) or "(none extracted)"

    # Retrieve a broad but bounded sample across the document.
    core_names = [c.name for c in knowledge.concepts if c.is_core][:6] or [
        c.name for c in knowledge.concepts[:6]
    ]
    chunks = index.search(core_names, max_results=5) or index.all_chunks()[:3]
    snippets = "\n\n".join(f"[{c.id}]\n{c.text[:1200]}" for c in chunks)[:6000]

    numerical_note = (
        f", {numerical_count} numerical problems" if numerical_count else ""
    )

    user_prompt = prompts.ASSESS_USER.format(
        subject=profile.subject,
        grade=profile.grade,
        topic=profile.topic,
        depth=depth,
        numerical_ok="yes" if quantitative else "no — this is not a quantitative subject",
        concepts=concepts_text,
        reference=reference,
        source_snippets=snippets,
        mcq_count=mcq_count,
        short_count=short_count,
        long_count=long_count,
        numerical_note=numerical_note,
        language_instruction=_get_lang_inst(profile),
    )

    try:
        data = await client.complete_json(
            stage="assessments",
            system_prompt=prompts.ASSESS_SYSTEM,
            user_prompt=user_prompt + "\n\nCRITICAL: You must respond with ONLY raw, valid JSON. Do not include markdown formatting, preambles, or explanations. If you include quotation marks inside your JSON string values (such as dialogue or quotes), you MUST use single quotes (') instead of double quotes (\") to ensure the JSON is valid.",
            json_schema={"type": "object"},
            max_tokens=4000,
        )
    except LLMError as exc:
        logger.error("assessment generation failed: %s", exc)
        return AssessmentPack()

    if not isinstance(data, dict):
        return AssessmentPack()

    valid_ids = {c.id for c in knowledge.concepts}

    def links(raw: dict) -> list[str]:
        return [str(c) for c in _safe_list(raw.get("linked_concept_ids")) if str(c) in valid_ids]

    mcqs: list[MCQItem] = []
    for raw in data.get("mcqs") or []:
        if not isinstance(raw, dict) or not raw.get("stem"):
            continue
        options = [
            MCQOption(key=str(o.get("key", chr(65 + i)))[:2], text=str(o.get("text", ""))[:400])
            for i, o in enumerate(_safe_list(raw.get("options")))
            if isinstance(o, dict)
        ]
        if len(options) < 2:
            continue
        correct = str(raw.get("correct_key", "")).strip().upper()[:2]
        if correct not in {o.key.upper() for o in options}:
            correct = options[0].key  # never ship an unanswerable item
        mcqs.append(
            MCQItem(
                stem=str(raw["stem"])[:800],
                options=options,
                correct_key=correct,
                explanation=str(raw.get("explanation", ""))[:800],
                difficulty=_safe_enum(Difficulty, raw.get("difficulty"), Difficulty.INTERMEDIATE),
                bloom_level=_safe_enum(BloomLevel, raw.get("bloom_level"), BloomLevel.UNDERSTAND),
                linked_concept_ids=links(raw),
                marks=_safe_int(raw.get("marks"), 1),
            )
        )

    shorts = [
        ShortAnswerItem(
            question=str(r["question"])[:600],
            model_answer=str(r.get("model_answer", ""))[:1200],
            key_points=[str(k)[:200] for k in _safe_list(r.get("key_points"))][:6],
            marks=_safe_int(r.get("marks"), 2),
            linked_concept_ids=links(r),
        )
        for r in _safe_list(data.get("short_answers"))
        if isinstance(r, dict) and r.get("question")
    ]

    longs = [
        LongAnswerItem(
            question=str(r["question"])[:800],
            marking_scheme=str(r.get("marking_scheme", ""))[:1500],
            word_limit=_safe_int(r.get("word_limit"), 250),
            marks=_safe_int(r.get("marks"), 5),
            linked_concept_ids=links(r),
        )
        for r in _safe_list(data.get("long_answers"))
        if isinstance(r, dict) and r.get("question")
    ]

    numericals = [
        NumericalItem(
            question=str(r["question"])[:800],
            answer=str(r.get("answer", ""))[:200],
            unit=str(r.get("unit", ""))[:40],
            solution_steps=[str(s)[:400] for s in _safe_list(r.get("solution_steps"))][:10],
            marks=_safe_int(r.get("marks"), 3),
            linked_concept_ids=links(r),
        )
        for r in _safe_list(data.get("numericals"))
        if isinstance(r, dict) and r.get("question")
    ] if quantitative else []

    items = AssessmentItem(
        mcqs=mcqs,
        short_answers=shorts,
        long_answers=longs,
        numericals=numericals,
    )
    items.total_marks = (
        sum(m.marks for m in mcqs)
        + sum(s.marks for s in shorts)
        + sum(l.marks for l in longs)
        + sum(n.marks for n in numericals)
    )

    # Coverage map: concept → the question IDs that test it.
    coverage: dict[str, list[str]] = {}
    for group in (mcqs, shorts, longs, numericals):
        for item in group:
            for cid in item.linked_concept_ids:
                coverage.setdefault(cid, []).append(item.id)
    items.coverage_map = coverage

    answer_key: dict[str, str] = {}
    for m in mcqs:
        answer_key[m.id] = m.correct_key
    for s in shorts:
        answer_key[s.id] = s.model_answer[:300]
    for n in numericals:
        answer_key[n.id] = f"{n.answer} {n.unit}".strip()

    blueprint: dict[str, int] = {}
    for m in mcqs:
        blueprint[m.bloom_level.value] = blueprint.get(m.bloom_level.value, 0) + m.marks

    return AssessmentPack(items=items, answer_key=answer_key, blueprint=blueprint)


# ── Stage 8: learning gap analysis ───────────────────────────────────────────


async def analyse_gaps(
    client: LLMClient,
    profile: DocumentProfile,
    knowledge: KnowledgeExtractionResult,
) -> GapAnalysis:
    """Diagnose likely misconceptions with diagnostics and remediation."""
    concepts_text = "\n".join(f"- {c.id} → {c.name}" for c in knowledge.concepts) or "(none)"
    known = "\n".join(
        f"- {m.statement}" for m in knowledge.common_misconceptions
    ) or "(none noted during extraction)"

    user_prompt = prompts.GAP_USER.format(
        subject=profile.subject,
        grade=profile.grade,
        topic=profile.topic,
        concepts=concepts_text,
        known_misconceptions=known,
        language_instruction=_get_lang_inst(profile),
    )

    try:
        data = await client.complete_json(
            stage="gap_analysis",
            system_prompt=prompts.GAP_SYSTEM,
            user_prompt=user_prompt + "\n\nCRITICAL: You must respond with ONLY raw, valid JSON. Do not include markdown formatting, preambles, or explanations. If you include quotation marks inside your JSON string values (such as dialogue or quotes), you MUST use single quotes (') instead of double quotes (\") to ensure the JSON is valid.",
            json_schema={"type": "object"},
            max_tokens=2400,
        )
    except LLMError as exc:
        logger.error("gap analysis failed: %s", exc)
        return GapAnalysis()

    if not isinstance(data, dict):
        return GapAnalysis()

    valid_ids = {c.id for c in knowledge.concepts}
    misconceptions = [
        MisconceptionAnalysis(
            misconception=str(r["misconception"])[:600],
            severity=_safe_enum(Severity, r.get("severity"), Severity.MEDIUM),
            diagnostic_question=str(r.get("diagnostic_question", ""))[:600],
            expected_wrong_answer=str(r.get("expected_wrong_answer", ""))[:400],
            remedial_action=str(r.get("remedial_action", ""))[:1000],
            linked_concept_ids=[
                str(c) for c in _safe_list(r.get("linked_concept_ids")) if str(c) in valid_ids
            ],
        )
        for r in (data.get("misconceptions") or [])
        if isinstance(r, dict) and r.get("misconception")
    ]

    covered = {cid for m in misconceptions for cid in m.linked_concept_ids}
    coverage = len(covered) / len(valid_ids) if valid_ids else 0.0

    return GapAnalysis(
        misconceptions=misconceptions,
        coverage_score=round(coverage, 3),
        remediation_summary=str(data.get("remediation_summary", ""))[:1200],
    )
