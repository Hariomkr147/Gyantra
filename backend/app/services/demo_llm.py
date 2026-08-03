"""
Deterministic stub LLM for demo mode and end-to-end tests.

Purpose: let the full 10-stage pipeline run with no API key so the app is
demonstrable offline and the orchestration can be tested without network calls.

It is NOT a model. It derives output from the source text already present in
each prompt, so results are structurally valid and lexically grounded, but
pedagogically shallow. Never enable DEMO_MODE for real teaching output.
"""

from __future__ import annotations

import logging
import re

from app.services.llm_client import LLMUsage

logger = logging.getLogger("gyantra.demo_llm")

# Prompt-format regexes. These rely on the templates in prompts.py, so the two
# files must change together.
_CONCEPT_LINE = re.compile(r"^- (\S+) → (.+?)(?: — |$)", re.MULTILINE)
_SECTION_HEADING = re.compile(r"^SECTION HEADING: (.*)$", re.MULTILINE)
_PERIOD_HEADER = re.compile(r"^PERIOD (\d+) of (\d+): (.*)$", re.MULTILINE)
_TRIPLE_QUOTED = re.compile(r'"""\s*(.*?)\s*"""', re.DOTALL)
_HEADINGS_BLOCK = re.compile(r"^HEADINGS DETECTED\n(.*?)\n\n", re.MULTILINE | re.DOTALL)

# "X is a Y" / "X are Y" definition patterns found in most textbook prose.
_DEFINITION = re.compile(
    r"\b([A-Z][A-Za-z' ]{2,40}?)\s+(?:is|are)\s+(?:called\s+)?"
    r"(?:a|an|the)?\s*([^.;]{15,180})[.;]"
)
_FORMULA_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z_\d ]{0,20})\s*=\s*([^=\n]{2,80})\s*$", re.MULTILINE)

_SUBJECT_KEYWORDS = {
    "Physics": ("force", "motion", "velocity", "energy", "newton", "momentum", "acceleration"),
    "Chemistry": ("atom", "molecule", "reaction", "compound", "element", "acid", "bond"),
    "Biology": ("cell", "organism", "tissue", "photosynthesis", "gene", "species", "enzyme"),
    "Mathematics": ("theorem", "equation", "triangle", "polynomial", "integer", "algebra"),
    "History": ("empire", "century", "war", "dynasty", "revolution", "colonial", "ancient"),
    "Geography": ("climate", "monsoon", "plateau", "latitude", "river", "soil", "terrain"),
    "Economics": ("market", "demand", "supply", "gdp", "inflation", "revenue", "trade"),
    "Political Science": ("democracy", "constitution", "parliament", "election", "citizen"),
}


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 25]


def _source_text(prompt: str) -> str:
    """Pull the quoted SOURCE TEXT block out of a prompt."""
    m = _TRIPLE_QUOTED.search(prompt)
    return m.group(1) if m else ""


def _concepts_from_prompt(prompt: str) -> list[tuple[str, str]]:
    """Return [(concept_id, concept_name)] as listed in the prompt."""
    return [
        (cid, name.strip())
        for cid, name in _CONCEPT_LINE.findall(prompt)
        if cid and name.strip()
    ]


def _guess_subject(text: str) -> str:
    low = text.lower()
    best, score = "General Studies", 0
    for subject, words in _SUBJECT_KEYWORDS.items():
        hits = sum(low.count(w) for w in words)
        if hits > score:
            best, score = subject, hits
    return best


class DemoLLMClient:
    """Drop-in replacement for LLMClient that never makes a network call."""

    def __init__(self, usage: LLMUsage | None = None, telemetry: Any | None = None):
        self.usage = usage or LLMUsage()
        self.telemetry = telemetry
        # Accumulated across the run so the merge stage can reuse map results.
        self._partials: list[dict] = []

    async def __aenter__(self) -> "DemoLLMClient":
        logger.warning("DEMO MODE — using the stub LLM. Output is illustrative only.")
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    def available_providers(self) -> list[str]:
        return ["demo"]

    async def complete_text(self, stage: str, system_prompt: str, user_prompt: str, **kw) -> str:
        return ""

    async def complete_json(
        self,
        stage: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict | None = None,
        max_tokens: int = 2400,
        temperature: float | None = None,
    ):
        self.usage.record("demo/stub", len(user_prompt) // 4, 200)

        if stage == "classification":
            return self._classify(user_prompt)
        if stage == "knowledge_extraction":
            # The merge prompt is the one carrying PER-SECTION RESULTS.
            if "PER-SECTION RESULTS" in user_prompt:
                return self._merge()
            return self._extract(user_prompt)
        if stage == "teaching_plan":
            return self._plan(user_prompt)
        if stage == "classroom_content":
            return self._content(user_prompt)
        if stage == "activities":
            return self._activities(user_prompt)
        if stage == "assessments":
            return self._assessments(user_prompt)
        if stage == "gap_analysis":
            return self._gaps(user_prompt)
        if stage == "validation":
            return {"ungrounded_claims": [], "hallucination_risk": 0.0, "notes": ["Demo mode: grounding audit skipped."]}
        return {}

    # ── stage stubs ──────────────────────────────────────────────────────

    def _classify(self, prompt: str) -> dict:
        headings_match = _HEADINGS_BLOCK.search(prompt)
        headings = headings_match.group(1) if headings_match else ""
        sample = _source_text(prompt) or prompt
        subject = _guess_subject(headings + " " + sample)

        # First heading is usually the chapter title.
        first = ""
        for line in headings.split("\n"):
            line = line.strip().lstrip("- ").strip()
            if line and line != "(no headings detected)":
                first = line
                break

        topic = re.sub(r"^(chapter|unit|lesson)\s*[\d.:]*\s*", "", first, flags=re.I).strip()

        return {
            "subject": subject,
            "grade": "Class 9",
            "difficulty": "intermediate",
            "topic": topic or subject,
            "chapter": first,
            "language": "en",
            "board": "",
            "document_type": "textbook chapter",
            "estimated_periods": 0,
            "confidence": 0.4,
        }

    def _extract(self, prompt: str) -> dict:
        heading_m = _SECTION_HEADING.search(prompt)
        heading = (heading_m.group(1).strip() if heading_m else "").split(" > ")[-1]
        heading = re.sub(r"^\d+(\.\d+)*\s*", "", heading).strip()

        text = _source_text(prompt)
        sents = _sentences(text)

        concepts = []
        if heading and heading != "(untitled section)":
            concepts.append(
                {
                    "name": heading,
                    "description": sents[0][:300] if sents else "",
                    "bloom_level": "understand",
                    "difficulty": "intermediate",
                    "is_core": True,
                }
            )

        definitions = []
        for term, body in _DEFINITION.findall(text)[:3]:
            term = term.strip()
            if 2 < len(term) < 40:
                definitions.append({"term": term, "text": body.strip()[:200]})

        formulas = [
            {"name": lhs.strip(), "latex": f"{lhs.strip()} = {rhs.strip()}", "explanation": ""}
            for lhs, rhs in _FORMULA_LINE.findall(text)[:3]
        ]

        # Frequent multi-character words make serviceable keywords.
        words = re.findall(r"\b[a-z]{5,}\b", text.lower())
        freq: dict[str, int] = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1
        keywords = [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:6]]

        result = {
            "learning_objectives": (
                [f"Explain {heading.lower()}"] if heading else []
            ),
            "concepts": concepts,
            "definitions": definitions,
            "formulas": formulas,
            "keywords": keywords,
            "examples": [
                {"title": "From the text", "text": s[:250], "is_solved": False}
                for s in sents[1:2]
            ],
            "misconceptions": [],
        }
        self._partials.append(result)
        return result

    def _merge(self) -> dict:
        concepts, definitions, formulas = [], [], []
        objectives, keywords = [], []
        seen_c, seen_d, seen_f = set(), set(), set()

        for p in self._partials:
            for c in p.get("concepts", []):
                key = c["name"].strip().lower()
                if key not in seen_c:
                    seen_c.add(key)
                    concepts.append(c)
            for d in p.get("definitions", []):
                key = d["term"].strip().lower()
                if key not in seen_d:
                    seen_d.add(key)
                    definitions.append(d)
            for f in p.get("formulas", []):
                key = f["name"].strip().lower()
                if key not in seen_f:
                    seen_f.add(key)
                    formulas.append(f)
            for o in p.get("learning_objectives", []):
                if o not in objectives:
                    objectives.append(o)
            for k in p.get("keywords", []):
                if k not in keywords:
                    keywords.append(k)

        return {
            "learning_objectives": objectives[:8],
            "prerequisites_list": ["Basic familiarity with the subject vocabulary"],
            "concepts": concepts,
            "definitions": definitions,
            "formulas": formulas,
            "keywords": keywords[:30],
            "examples": [e for p in self._partials for e in p.get("examples", [])][:8],
            "applications": [],
            "common_misconceptions": [],
            "key_terms_glossary": {d["term"]: d["text"][:120] for d in definitions[:10]},
        }

    def _plan(self, prompt: str) -> dict:
        pairs = _concepts_from_prompt(prompt)
        if not pairs:
            pairs = [("c0", "Overview")]

        # Two concepts per period keeps the demo plan legible.
        per_period = 2
        groups = [pairs[i : i + per_period] for i in range(0, len(pairs), per_period)]

        periods = []
        for i, group in enumerate(groups, start=1):
            names = [n for _, n in group]
            periods.append(
                {
                    "number": i,
                    "title": names[0] if len(names) == 1 else f"{names[0]} and {names[1]}",
                    "estimated_minutes": 40,
                    "objectives": [
                        {"text": f"Explain {n.lower()}", "concept_ids": [cid]}
                        for cid, n in group
                    ],
                    "key_concepts": [cid for cid, _ in group],
                    "warmup_strategy": "Recall the previous period's key idea.",
                    "flow_summary": f"Introduce and practise: {', '.join(names)}.",
                    "prerequisite_review": [],
                }
            )

        return {
            "total_periods": len(periods),
            "default_minutes_per_period": 40,
            "adaptation_rationale": (
                f"Demo mode grouped {len(pairs)} extracted concepts into "
                f"{len(periods)} periods at two concepts per period."
            ),
            "periods": periods,
            "cross_period_review_points": [n for _, n in pairs[:3]],
        }

    def _content(self, prompt: str) -> dict:
        m = _PERIOD_HEADER.search(prompt)
        title = m.group(3).strip() if m else "This period"
        source = _source_text(prompt)
        sents = _sentences(source)
        body = " ".join(sents[:4])[:1200] or f"Discuss {title}."

        # Board notes drawn from the source keep the demo lexically grounded.
        bullets = [f"- {s[:110]}" for s in sents[:4]]

        return {
            "warmup": f"Ask students what they already associate with {title.lower()}.",
            "teacher_script": (
                f"Begin by naming today's focus: {title}. {body} "
                "Pause after each idea and ask a student to restate it in their own words."
            ),
            "blackboard_notes": f"{title}\n" + "\n".join(bullets),
            "checkpoint_questions": [
                f"In one sentence, what is {title.lower()}?",
                f"Give one example of {title.lower()} from the chapter.",
                "Which part of today's lesson is still unclear?",
            ],
            "exit_ticket": f"Write two sentences explaining {title.lower()}.",
            "homework": f"Re-read the section on {title.lower()} and answer the textbook questions.",
            "mentor_moment": (
                "Every expert was once a beginner who kept asking questions. "
                "Confusion is a sign you are working at the edge of what you know."
            ),
        }

    def _activities(self, prompt: str) -> dict:
        pairs = _concepts_from_prompt(prompt)
        kinds = ["think_pair_share", "demonstration", "group_task", "worksheet", "discussion"]
        return {
            "activities": [
                {
                    "title": f"{kinds[i % len(kinds)].replace('_', ' ').title()}: {name}",
                    "activity_type": kinds[i % len(kinds)],
                    "duration_minutes": 15,
                    "materials": ["Blackboard", "Notebook"],
                    "teacher_instructions": (
                        f"1. Put the question 'What is {name.lower()}?' on the board.\n"
                        "2. Give pairs three minutes to agree an answer.\n"
                        "3. Take responses from three pairs and correct misstatements."
                    ),
                    "expected_student_response": f"A correct plain-language account of {name.lower()}.",
                    "success_criteria": "Most pairs produce an accurate statement unprompted.",
                    "linked_period_ids": [],
                    "linked_concept_ids": [cid],
                }
                for i, (cid, name) in enumerate(pairs[:6])
            ]
        }

    def _assessments(self, prompt: str) -> dict:
        pairs = _concepts_from_prompt(prompt)
        mcqs = []
        for i, (cid, name) in enumerate(pairs[:6]):
            mcqs.append(
                {
                    "stem": f"Which statement best describes {name.lower()}?",
                    "options": [
                        {"key": "A", "text": f"The definition of {name.lower()} given in the chapter"},
                        {"key": "B", "text": "An unrelated process"},
                        {"key": "C", "text": "A measurement unit only"},
                        {"key": "D", "text": "None of the above"},
                    ],
                    "correct_key": "A",
                    "explanation": f"The chapter defines {name.lower()} directly.",
                    "difficulty": "foundational" if i % 2 else "intermediate",
                    "bloom_level": "remember" if i % 2 else "understand",
                    "linked_concept_ids": [cid],
                    "marks": 1,
                }
            )

        return {
            "mcqs": mcqs,
            "short_answers": [
                {
                    "question": f"Explain {name.lower()} in two or three sentences.",
                    "model_answer": f"A correct explanation of {name.lower()} as presented in the chapter.",
                    "key_points": [name],
                    "marks": 2,
                    "linked_concept_ids": [cid],
                }
                for cid, name in pairs[:4]
            ],
            "long_answers": [
                {
                    "question": f"Discuss {name.lower()} with an example from the chapter.",
                    "marking_scheme": "2 marks definition, 2 marks example, 1 mark clarity.",
                    "word_limit": 250,
                    "marks": 5,
                    "linked_concept_ids": [cid],
                }
                for cid, name in pairs[:2]
            ],
            "numericals": [],
        }

    def _gaps(self, prompt: str) -> dict:
        pairs = _concepts_from_prompt(prompt)
        return {
            "misconceptions": [
                {
                    "misconception": f"Students often confuse {name.lower()} with a superficially similar idea.",
                    "severity": "medium",
                    "diagnostic_question": f"Describe {name.lower()} and say what it is NOT.",
                    "expected_wrong_answer": "A definition that blends two distinct ideas.",
                    "remedial_action": f"Contrast {name.lower()} against the nearest competing idea side by side on the board.",
                    "linked_concept_ids": [cid],
                }
                for cid, name in pairs[:5]
            ],
            "remediation_summary": (
                "Demo mode produced generic misconceptions. Configure a real model "
                "for a genuine diagnostic analysis."
            ),
        }
