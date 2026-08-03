"""
Prompt templates for every LLM stage.

Rules baked into every prompt:
 - Ground factual content in the supplied source snippets only.
 - Mark anything invented for teaching purposes as pedagogical support.
 - Return JSON only, matching the supplied schema.
 - Keep prompts short: free-tier models degrade fast on long instructions.
"""

from __future__ import annotations

# The grounding contract is repeated in every system prompt because free
# open-weight models forget constraints stated only once.
GROUNDING_RULE = (
    "GROUNDING CONTRACT:\n"
    "1. Every factual claim, definition, formula, and concept MUST come from the "
    "SOURCE text provided. Do not add subject matter that is not present.\n"
    "2. You may add teaching scaffolding (analogies, activity framing, pacing "
    "advice, classroom management tips). Mark such items origin='pedagogical'.\n"
    "3. If the source does not support a field, return an empty value rather "
    "than inventing content.\n"
    "4. Output valid JSON only. No prose, no markdown fences."
)

LANGUAGE_INSTRUCTION = """
IMPORTANT MULTILINGUAL INSTRUCTION:
Generate ALL output content (scripts, notes, questions, activities, etc.) in {language}.
Keep technical/scientific terms in English where standard practice, but all
explanatory text, instructions, and questions must be in {language}.
"""

BASE_SYSTEM = (
    "You are Gyantra, an expert curriculum designer and educational content "
    "analyst. You convert source documents into precise, structured, "
    "classroom-ready teaching data.\n\n" + GROUNDING_RULE
)


# ── Stage 2: classification ──────────────────────────────────────────────────

CLASSIFY_SYSTEM = BASE_SYSTEM

CLASSIFY_USER = """Classify this educational document.

DOCUMENT METADATA
File: {file_name}
Pages: {page_count}
Tables: {table_count} | Figures: {figure_count} | Equations: {equation_count}

HEADINGS DETECTED
{headings}

SOURCE SAMPLE (beginning and middle of document)
{sample}

USER-PROVIDED CONTEXT (treat as authoritative where given)
{user_context}

Return JSON with exactly these keys:
- subject: string (e.g. "Physics", "History", "Mathematics")
- grade: string (e.g. "Class 9", "Class 11"; infer from vocabulary and depth)
- difficulty: one of "foundational" | "intermediate" | "advanced"
- topic: string (the specific topic, not the whole subject)
- chapter: string (chapter title if identifiable, else "")
- language: ISO code, e.g. "en", "hi"
- board: string (e.g. "CBSE", "ICSE", "NCERT", "" if unclear)
- document_type: string (e.g. "textbook chapter", "lecture notes", "research paper")
- estimated_periods: integer, your estimate of 40-minute periods needed
- confidence: float 0-1
"""


# ── Stage 3: knowledge extraction (map step, per chunk) ──────────────────────

EXTRACT_SYSTEM = BASE_SYSTEM

EXTRACT_CHUNK_USER = """Extract educational knowledge from this ONE SECTION of a \
{subject} document for {grade}.

SECTION HEADING: {heading}
CHUNK ID: {chunk_id}

SOURCE TEXT
\"\"\"
{chunk_text}
\"\"\"

Extract only what this section actually contains. Return JSON:
{{
  "learning_objectives": ["specific, measurable objective starting with a verb"],
  "concepts": [
    {{"name": "...", "description": "1-2 sentences from the source",
      "bloom_level": "remember|understand|apply|analyze|evaluate|create",
      "difficulty": "foundational|intermediate|advanced",
      "is_core": true|false}}
  ],
  "definitions": [{{"term": "...", "text": "definition as stated in source"}}],
  "formulas": [{{"name": "...", "latex": "...", "explanation": "..."}}],
  "keywords": ["term"],
  "examples": [{{"title": "...", "text": "...", "is_solved": true|false}}],
  "misconceptions": [{{"statement": "a mistake students commonly make here"}}]
}}

Return empty arrays for anything the section does not cover. Do not repeat the \
section heading as a concept unless it is genuinely a distinct idea."""


# ── Stage 3b: extraction merge (reduce step) ─────────────────────────────────

EXTRACT_MERGE_SYSTEM = BASE_SYSTEM

EXTRACT_MERGE_USER = """You are merging per-section extraction results for a \
{subject} document for {grade}. Remove duplicates and near-duplicates, order \
concepts in teaching order, and produce document-level objectives.

PER-SECTION RESULTS (JSON)
{partials}

Return JSON:
{{
  "learning_objectives": ["5-8 document-level objectives, measurable verbs"],
  "prerequisites_list": ["what students must already know before this chapter"],
  "concepts": [
    {{"name": "...", "description": "...", "bloom_level": "...",
      "difficulty": "...", "is_core": true|false,
      "prerequisites": ["names of earlier concepts in this list"]}}
  ],
  "definitions": [{{"term": "...", "text": "..."}}],
  "formulas": [{{"name": "...", "latex": "...", "explanation": "..."}}],
  "keywords": ["..."],
  "examples": [{{"title": "...", "text": "...", "is_solved": true|false}}],
  "applications": [{{"name": "...", "description": "real-world use"}}],
  "common_misconceptions": [{{"statement": "..."}}],
  "key_terms_glossary": {{"term": "short gloss"}}
}}

Merge aggressively: two concepts describing the same idea become one. Keep \
concepts ordered so prerequisites come before dependents."""


# ── Stage 4: teaching plan ───────────────────────────────────────────────────

PLAN_SYSTEM = (
    "You are an expert instructional designer. You build adaptive, realistic "
    "teaching plans that fit actual classroom constraints.\n\n" + GROUNDING_RULE
)

PLAN_USER = """Design an adaptive teaching plan.

CONTEXT
Subject: {subject} | Grade: {grade} | Topic: {topic}
Difficulty: {difficulty}
Document volume: {chunk_count} sections, ~{word_count} words
Teacher constraints: {constraints}

LEARNING OBJECTIVES
{objectives}

CONCEPTS (in extracted order; id → name — difficulty)
{concepts}

PREREQUISITES
{prerequisites}

CRITICAL RULE: Do NOT default to 5 periods. Choose the period count that the \
content actually needs, based on concept count, conceptual difficulty, grade \
level, and the teacher's stated time constraints. A short simple section may \
need 2 periods; a dense chapter may need 8. Justify your choice.

Return JSON:
{{
  "total_periods": integer,
  "default_minutes_per_period": integer,
  "adaptation_rationale": "2-3 sentences explaining why this many periods, \
referencing content volume and complexity",
  "periods": [
    {{"number": 1,
      "title": "specific title, not 'Period 1'",
      "estimated_minutes": 40,
      "objectives": [{{"text": "...", "concept_ids": ["c1","c2"]}}],
      "key_concepts": ["concept ids covered this period"],
      "warmup_strategy": "one line",
      "flow_summary": "1-2 sentences describing the arc of the period",
      "prerequisite_review": ["what to revisit at the start"]}}
  ],
  "cross_period_review_points": ["concepts worth revisiting later"]
}}

Every concept id from the list above must appear in exactly one period's \
key_concepts. Sequence so prerequisites are taught before dependents."""


# ── Stage 5: classroom content (per period) ──────────────────────────────────

CONTENT_SYSTEM = (
    "You are a master teacher writing classroom-ready material that another "
    "teacher can pick up and deliver without preparation.\n\n" + GROUNDING_RULE
)

CONTENT_USER = """Write the full classroom material for ONE period.

PERIOD {period_number} of {total_periods}: {period_title}
Duration: {minutes} minutes | Subject: {subject} | Grade: {grade}

OBJECTIVES FOR THIS PERIOD
{objectives}

CONCEPTS TO TEACH THIS PERIOD
{concepts}

RELEVANT SOURCE TEXT (use this for all factual content)
\"\"\"
{source_snippets}
\"\"\"

Return JSON:
{{
  "warmup": "3-5 minute entry ticket / warm-up. Concrete, not 'ask students \
what they know'.",
  "teacher_script": "The main teaching narrative, 250-400 words. Write what the \
teacher actually says and does. Include the key explanations and at least one \
worked example or illustration drawn from the source.",
  "blackboard_notes": "What goes on the board, as a compact structured outline \
students can copy. Use short lines and dashes.",
  "checkpoint_questions": ["3-4 quick oral questions to check understanding \
mid-lesson"],
  "exit_ticket": "One question students answer before leaving",
  "homework": "A specific, doable assignment tied to this period's objectives",
  "mentor_moment": "A 2-3 sentence motivational or real-world connection. This \
is pedagogical support, so it may go beyond the source, but must not contradict it."
}}

Write for {grade}. Match the vocabulary level to the grade. Every fact must \
trace to the source text above.
{language_instruction}"""


# ── Stage 6: activities ──────────────────────────────────────────────────────

ACTIVITY_SYSTEM = (
    "You design classroom activities that work with ordinary school resources "
    "and real class sizes.\n\n" + GROUNDING_RULE
)

ACTIVITY_USER = """Design {count} diverse classroom activities for this teaching plan.

Subject: {subject} | Grade: {grade} | Topic: {topic}

PERIODS
{periods}

CORE CONCEPTS
{concepts}

Return JSON: {{"activities": [ ... ]}} where each activity is:
{{
  "title": "...",
  "activity_type": "discussion|demonstration|experiment|role_play|worksheet|\
group_task|board_work|think_pair_share|case_study",
  "duration_minutes": integer,
  "materials": ["items available in a normal classroom"],
  "teacher_instructions": "numbered steps, specific enough to run without prep",
  "expected_student_response": "what good student output looks like",
  "success_criteria": "how the teacher knows it worked",
  "linked_period_ids": ["period ids this fits"],
  "linked_concept_ids": ["concept ids this reinforces"]
}}

play, and case studies; Mathematics gets board work and structured practice. \
Only require materials a typical school actually has.
{language_instruction}"""


# ── Stage 7: assessments ─────────────────────────────────────────────────────

ASSESS_SYSTEM = (
    "You are an assessment specialist who writes fair, unambiguous items with "
    "clean marking schemes.\n\n" + GROUNDING_RULE
)

ASSESS_USER = """Create an assessment pack.

Subject: {subject} | Grade: {grade} | Topic: {topic}
Assessment depth requested: {depth}
Numerical questions appropriate: {numerical_ok}

CONCEPTS TO ASSESS (id → name)
{concepts}

DEFINITIONS AND FORMULAS AVAILABLE
{reference}

RELEVANT SOURCE TEXT
\"\"\"
{source_snippets}
\"\"\"

Return JSON:
{{
  "mcqs": [
    {{"stem": "...", "options": [{{"key":"A","text":"..."}}, ...4 options],
      "correct_key": "A", "explanation": "why this is right and others wrong",
      "difficulty": "foundational|intermediate|advanced",
      "bloom_level": "remember|understand|apply|analyze|evaluate|create",
      "linked_concept_ids": ["..."], "marks": 1}}
  ],
  "short_answers": [
    {{"question": "...", "model_answer": "...", "key_points": ["..."],
      "marks": 2, "linked_concept_ids": ["..."]}}
  ],
  "long_answers": [
    {{"question": "...", "marking_scheme": "how marks are distributed",
      "word_limit": 250, "marks": 5, "linked_concept_ids": ["..."]}}
  ],
  "numericals": [
    {{"question": "...", "answer": "...", "unit": "...",
      "solution_steps": ["step 1", "step 2"], "marks": 3,
      "linked_concept_ids": ["..."]}}
  ]
}}

Counts: {mcq_count} MCQs, {short_count} short answers, {long_count} long \
answers{numerical_note}. Distractors must be plausible, not obviously wrong. \
Spread items across Bloom levels — not all recall. Every item must be \
answerable from the source content. Return an empty array for numericals if the \
subject is not quantitative.
{language_instruction}"""


# ── Stage 8: gap analysis ────────────────────────────────────────────────────

GAP_SYSTEM = (
    "You are a learning-science specialist who diagnoses why students get "
    "things wrong and prescribes targeted remediation.\n\n" + GROUNDING_RULE
)

GAP_USER = """Analyse likely learning gaps for this topic.

Subject: {subject} | Grade: {grade} | Topic: {topic}

CONCEPTS TAUGHT (id → name)
{concepts}

MISCONCEPTIONS ALREADY NOTED IN THE SOURCE
{known_misconceptions}

Return JSON:
{{
  "misconceptions": [
    {{"misconception": "the specific wrong belief, stated as a student would \
hold it",
      "severity": "low|medium|high",
      "diagnostic_question": "a question that reveals whether a student holds \
this misconception",
      "expected_wrong_answer": "what a student with this misconception answers",
      "remedial_action": "a concrete teaching move to correct it",
      "linked_concept_ids": ["..."]}}
  ],
  "remediation_summary": "2-3 sentences on the overall pattern of difficulty \
for this topic"
}}

Produce 4-7 misconceptions. Severity 'high' means it blocks later learning. \
Ground each misconception in the actual concepts listed — do not import generic \
misconceptions from unrelated topics. Write in a constructive tone meant for a teacher attempting to correct these \
misconceptions gracefully.
{language_instruction}"""


# ── Stage 9: validation (LLM grounding pass) ─────────────────────────────────

VALIDATE_SYSTEM = (
    "You are a strict content auditor. You check generated teaching material "
    "against its source and report problems factually. You do not fix them.\n"
    "Output valid JSON only."
)

VALIDATE_USER = """Audit this generated teaching content for grounding failures.

SOURCE SUMMARY (what the document actually contains)
Concepts: {concepts}
Definitions: {definitions}
Key terms: {keywords}

GENERATED CLAIMS TO AUDIT
{claims}

For each claim, decide whether it is supported by the source summary above.

Return JSON:
{{
  "ungrounded_claims": ["verbatim claims that introduce subject matter absent \
from the source"],
  "hallucination_risk": 0.0,
  "notes": ["short observations about content quality"]
}}

Be precise, not paranoid. Teaching scaffolding (analogies, activity framing, \
motivational content) is allowed and is NOT an ungrounded claim. Only flag new \
*subject matter*: facts, dates, figures, named entities, formulas, or technical \
claims that the source does not contain. hallucination_risk is the fraction of \
audited claims that are genuinely ungrounded."""
