"""
Stages 2 & 3 — Educational Classification and Knowledge Extraction.

Both stages are token-budget aware:
 - Classification sees only headings plus two small text samples.
 - Extraction runs map-reduce: one small call per chunk, then a merge call.
"""

from __future__ import annotations

import asyncio
import json
import logging

from app.config import settings
from app.models.enums import BloomLevel, Difficulty, Origin
from app.models.schemas import (
    Concept,
    Definition,
    DocumentIntelligenceResult,
    DocumentProfile,
    Example,
    Formula,
    KnowledgeExtractionResult,
    MisconceptionExtracted,
    SourceRef,
)
from app.services import prompts
from app.services.chunker import Chunk
from app.services.llm_client import LLMClient, LLMError

logger = logging.getLogger("gyantra.stages.knowledge")


def _safe_enum(enum_cls, value, default):
    """Coerce a model-supplied string into an enum, falling back on garbage."""
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(str(value).strip().lower())
    except (ValueError, AttributeError):
        return default


# ── Stage 2: classification ──────────────────────────────────────────────────


async def classify_document(
    client: LLMClient,
    doc: DocumentIntelligenceResult,
    chunks: list[Chunk],
    user_context: dict,
) -> DocumentProfile:
    """Infer subject, grade, topic and other educational metadata.

    Sends a deliberately small prompt: headings carry most of the signal.
    """
    headings = [b.content for b in doc.heading_blocks][:40]
    headings_text = "\n".join(f"- {h}" for h in headings) or "(no headings detected)"

    # Two samples: the opening (usually states the topic) and the middle
    # (shows the actual difficulty level).
    text = doc.plain_text
    head_sample = text[:1800]
    mid = len(text) // 2
    mid_sample = text[mid : mid + 1200] if len(text) > 3000 else ""
    sample = head_sample + ("\n[...]\n" + mid_sample if mid_sample else "")

    ctx_lines = [f"{k}: {v}" for k, v in user_context.items() if v]
    ctx_text = "\n".join(ctx_lines) or "(none provided)"

    user_prompt = prompts.CLASSIFY_USER.format(
        file_name=doc.file_name,
        page_count=doc.page_count,
        table_count=doc.table_count,
        figure_count=doc.figure_count,
        equation_count=doc.equation_count,
        headings=headings_text,
        sample=sample,
        user_context=ctx_text,
    )

    try:
        data = await client.complete_json(
            stage="classification",
            system_prompt=prompts.CLASSIFY_SYSTEM,
            user_prompt=user_prompt,
            max_tokens=700,
            temperature=0.1,  # classification wants determinism
        )
    except LLMError as exc:
        logger.error("classification failed, using fallback profile: %s", exc)
        data = {}

    profile = DocumentProfile(
        subject=str(data.get("subject") or user_context.get("subject") or "General"),
        grade=str(data.get("grade") or user_context.get("grade") or "Unspecified"),
        difficulty=_safe_enum(Difficulty, data.get("difficulty"), Difficulty.INTERMEDIATE),
        topic=str(data.get("topic") or ""),
        chapter=str(data.get("chapter") or ""),
        language=str(data.get("language") or doc.language_hint or "en"),
        board=str(data.get("board") or user_context.get("board") or ""),
        document_type=str(data.get("document_type") or "educational document"),
        estimated_periods=int(data.get("estimated_periods") or 0),
        confidence=float(data.get("confidence") or 0.5),
    )

    # The user's explicit answers always win over inference.
    if user_context.get("subject"):
        profile.subject = user_context["subject"]
    if user_context.get("grade"):
        profile.grade = user_context["grade"]
    if user_context.get("language"):
        profile.language = user_context["language"]
    if user_context.get("board"):
        profile.board = user_context["board"]

    return profile


# ── Stage 3: knowledge extraction (map-reduce) ───────────────────────────────


async def _extract_one_chunk(
    client: LLMClient,
    chunk: Chunk,
    profile: DocumentProfile,
) -> dict:
    """Map step: extract knowledge from a single chunk."""
    user_prompt = prompts.EXTRACT_CHUNK_USER.format(
        subject=profile.subject,
        grade=profile.grade,
        heading=chunk.heading_path or "(untitled section)",
        chunk_id=chunk.id,
        chunk_text=chunk.text[: settings.max_context_tokens_per_call * 4],
    )
    try:
        data = await client.complete_json(
            stage="knowledge_extraction",
            system_prompt=prompts.EXTRACT_SYSTEM,
            user_prompt=user_prompt,
            max_tokens=1600,
        )
        if isinstance(data, dict):
            data["_chunk_id"] = chunk.id
            data["_pages"] = chunk.pages
            data["_heading"] = chunk.heading_path
            return data
    except LLMError as exc:
        logger.warning("extraction failed for %s: %s", chunk.id, exc)
    return {"_chunk_id": chunk.id, "_pages": chunk.pages, "_heading": chunk.heading_path}


async def extract_knowledge(
    client: LLMClient,
    chunks: list[Chunk],
    profile: DocumentProfile,
    progress_cb=None,
) -> KnowledgeExtractionResult:
    """Map-reduce knowledge extraction over the document's chunks.

    Map:    one compact call per chunk (bounded concurrency).
    Reduce: one merge call over the compacted partial results.
    """
    if not chunks:
        return KnowledgeExtractionResult()

    sem = asyncio.Semaphore(settings.parallel_period_generation)
    done = 0

    async def guarded(ch: Chunk) -> dict:
        nonlocal done
        async with sem:
            result = await _extract_one_chunk(client, ch, profile)
            done += 1
            if progress_cb:
                await progress_cb(done, len(chunks))
            return result

    partials = await asyncio.gather(*(guarded(c) for c in chunks))

    # Record a per-chunk summary so later stages can retrieve cheaply.
    for chunk, part in zip(chunks, partials):
        names = [c.get("name", "") for c in (part.get("concepts") or []) if isinstance(c, dict)]
        chunk.summary = "; ".join(n for n in names if n)[:300]

    merged = await _merge_partials(client, partials, profile)
    return merged


def _compact_partials(partials: list[dict], max_chars: int = 14000) -> str:
    """Shrink map results so the reduce prompt stays inside a small context.

    Drops verbose fields (example text, long descriptions) before truncating, so
    we lose detail rather than whole sections.
    """
    compact = []
    for p in partials:
        entry = {
            "chunk": p.get("_chunk_id"),
            "heading": p.get("_heading", "")[:80],
            "objectives": (p.get("learning_objectives") or [])[:5],
            "concepts": [
                {
                    "name": str(c.get("name", ""))[:80],
                    "description": str(c.get("description", ""))[:180],
                    "bloom_level": c.get("bloom_level", "understand"),
                    "difficulty": c.get("difficulty", "intermediate"),
                    "is_core": bool(c.get("is_core", False)),
                }
                for c in (p.get("concepts") or [])[:8]
                if isinstance(c, dict)
            ],
            "definitions": [
                {"term": str(d.get("term", ""))[:60], "text": str(d.get("text", ""))[:180]}
                for d in (p.get("definitions") or [])[:6]
                if isinstance(d, dict)
            ],
            "formulas": [
                {
                    "name": str(f.get("name", ""))[:60],
                    "latex": str(f.get("latex", ""))[:120],
                    "explanation": str(f.get("explanation", ""))[:120],
                }
                for f in (p.get("formulas") or [])[:5]
                if isinstance(f, dict)
            ],
            "keywords": (p.get("keywords") or [])[:10],
            "examples": [
                {"title": str(e.get("title", ""))[:60], "text": str(e.get("text", ""))[:150]}
                for e in (p.get("examples") or [])[:3]
                if isinstance(e, dict)
            ],
            "misconceptions": [
                str(m.get("statement", ""))[:150]
                for m in (p.get("misconceptions") or [])[:3]
                if isinstance(m, dict)
            ],
        }
        compact.append(entry)

    text = json.dumps(compact, ensure_ascii=False)
    if len(text) <= max_chars:
        return text

    # Still too long: halve the per-chunk concept allowance and retry once.
    for entry in compact:
        entry["concepts"] = entry["concepts"][:4]
        entry["definitions"] = entry["definitions"][:3]
        entry["examples"] = entry["examples"][:1]
        entry["keywords"] = entry["keywords"][:5]
    text = json.dumps(compact, ensure_ascii=False)
    return text[:max_chars]


async def _merge_partials(
    client: LLMClient,
    partials: list[dict],
    profile: DocumentProfile,
) -> KnowledgeExtractionResult:
    """Reduce step: deduplicate and order the merged knowledge."""
    user_prompt = prompts.EXTRACT_MERGE_USER.format(
        subject=profile.subject,
        grade=profile.grade,
        partials=_compact_partials(partials),
    )

    try:
        data = await client.complete_json(
            stage="knowledge_extraction",
            system_prompt=prompts.EXTRACT_MERGE_SYSTEM,
            user_prompt=user_prompt,
            max_tokens=3000,
        )
    except LLMError as exc:
        logger.error("merge failed, falling back to deterministic merge: %s", exc)
        return _deterministic_merge(partials)

    if not isinstance(data, dict):
        return _deterministic_merge(partials)

    return _build_extraction_result(data, partials)


def _build_extraction_result(
    data: dict, partials: list[dict]
) -> KnowledgeExtractionResult:
    """Convert merged LLM output into typed objects, attaching source refs."""
    # Build a name → (chunk_ids, pages) lookup from the map results so we can
    # restore traceability that the merge step doesn't carry.
    provenance: dict[str, tuple[set[str], set[int]]] = {}
    for p in partials:
        cid = p.get("_chunk_id")
        pages = set(p.get("_pages") or [])
        for c in p.get("concepts") or []:
            if isinstance(c, dict) and c.get("name"):
                key = str(c["name"]).strip().lower()
                chunk_ids, pgs = provenance.setdefault(key, (set(), set()))
                if cid:
                    chunk_ids.add(cid)
                pgs.update(pages)
        for d in p.get("definitions") or []:
            if isinstance(d, dict) and d.get("term"):
                key = str(d["term"]).strip().lower()
                chunk_ids, pgs = provenance.setdefault(key, (set(), set()))
                if cid:
                    chunk_ids.add(cid)
                pgs.update(pages)

    def ref_for(name: str) -> SourceRef | None:
        entry = provenance.get(str(name).strip().lower())
        if not entry:
            return None
        chunk_ids, pages = entry
        return SourceRef(chunk_ids=sorted(chunk_ids), pages=sorted(pages))

    concepts: list[Concept] = []
    name_to_id: dict[str, str] = {}
    for raw in data.get("concepts") or []:
        if not isinstance(raw, dict) or not raw.get("name"):
            continue
        concept = Concept(
            name=str(raw["name"])[:150],
            description=str(raw.get("description", ""))[:600],
            bloom_level=_safe_enum(BloomLevel, raw.get("bloom_level"), BloomLevel.UNDERSTAND),
            difficulty=_safe_enum(Difficulty, raw.get("difficulty"), Difficulty.INTERMEDIATE),
            is_core=bool(raw.get("is_core", False)),
            source_ref=ref_for(raw["name"]),
            origin=Origin.SOURCE,
        )
        concepts.append(concept)
        name_to_id[concept.name.strip().lower()] = concept.id

    # Resolve prerequisite names → concept IDs.
    for raw, concept in zip(
        [c for c in (data.get("concepts") or []) if isinstance(c, dict) and c.get("name")],
        concepts,
    ):
        prereq_names = raw.get("prerequisites") or []
        concept.prerequisites = [
            name_to_id[str(p).strip().lower()]
            for p in prereq_names
            if str(p).strip().lower() in name_to_id
        ]

    definitions = [
        Definition(
            term=str(d.get("term", ""))[:150],
            text=str(d.get("text", ""))[:600],
            source_ref=ref_for(d.get("term", "")),
        )
        for d in (data.get("definitions") or [])
        if isinstance(d, dict) and d.get("term")
    ]

    formulas = [
        Formula(
            name=str(f.get("name", ""))[:150],
            latex=str(f.get("latex", ""))[:300],
            explanation=str(f.get("explanation", ""))[:400],
            variables=[v for v in (f.get("variables") or []) if isinstance(v, dict)],
        )
        for f in (data.get("formulas") or [])
        if isinstance(f, dict) and f.get("name")
    ]

    examples = [
        Example(
            title=str(e.get("title", ""))[:150],
            text=str(e.get("text", ""))[:800],
            is_solved=bool(e.get("is_solved", False)),
        )
        for e in (data.get("examples") or [])
        if isinstance(e, dict) and e.get("text")
    ]

    from app.models.schemas import Application

    applications = [
        Application(
            name=str(a.get("name", ""))[:150],
            description=str(a.get("description", ""))[:400],
            origin=Origin.PEDAGOGICAL,
        )
        for a in (data.get("applications") or [])
        if isinstance(a, dict) and a.get("name")
    ]

    misconceptions = [
        MisconceptionExtracted(statement=str(m.get("statement", ""))[:400])
        for m in (data.get("common_misconceptions") or [])
        if isinstance(m, dict) and m.get("statement")
    ]

    concept_graph = {c.id: c.prerequisites for c in concepts if c.prerequisites}

    glossary = data.get("key_terms_glossary")
    if not isinstance(glossary, dict):
        glossary = {}

    return KnowledgeExtractionResult(
        learning_objectives=[
            str(o)[:300] for o in (data.get("learning_objectives") or []) if str(o).strip()
        ],
        prerequisites_list=[
            str(p)[:200] for p in (data.get("prerequisites_list") or []) if str(p).strip()
        ],
        concepts=concepts,
        definitions=definitions,
        formulas=formulas,
        keywords=[str(k)[:80] for k in (data.get("keywords") or []) if str(k).strip()][:60],
        examples=examples,
        applications=applications,
        common_misconceptions=misconceptions,
        concept_graph=concept_graph,
        key_terms_glossary={str(k)[:80]: str(v)[:300] for k, v in glossary.items()},
    )


def _deterministic_merge(partials: list[dict]) -> KnowledgeExtractionResult:
    """Code-only merge used when the reduce LLM call fails.

    Keeps the pipeline alive with a slightly noisier result instead of aborting.
    """
    seen_concepts: dict[str, dict] = {}
    seen_defs: dict[str, dict] = {}
    objectives: list[str] = []
    keywords: set[str] = set()
    misconceptions: list[str] = []
    examples: list[dict] = []
    formulas: dict[str, dict] = {}

    for p in partials:
        for o in p.get("learning_objectives") or []:
            if str(o).strip() and str(o) not in objectives:
                objectives.append(str(o))
        for c in p.get("concepts") or []:
            if isinstance(c, dict) and c.get("name"):
                seen_concepts.setdefault(str(c["name"]).strip().lower(), c)
        for d in p.get("definitions") or []:
            if isinstance(d, dict) and d.get("term"):
                seen_defs.setdefault(str(d["term"]).strip().lower(), d)
        for f in p.get("formulas") or []:
            if isinstance(f, dict) and f.get("name"):
                formulas.setdefault(str(f["name"]).strip().lower(), f)
        for k in p.get("keywords") or []:
            if str(k).strip():
                keywords.add(str(k).strip())
        for m in p.get("misconceptions") or []:
            if isinstance(m, dict) and m.get("statement"):
                misconceptions.append(str(m["statement"]))
        for e in p.get("examples") or []:
            if isinstance(e, dict) and e.get("text"):
                examples.append(e)

    data = {
        "learning_objectives": objectives[:10],
        "prerequisites_list": [],
        "concepts": list(seen_concepts.values()),
        "definitions": list(seen_defs.values()),
        "formulas": list(formulas.values()),
        "keywords": sorted(keywords)[:50],
        "examples": examples[:12],
        "applications": [],
        "common_misconceptions": [{"statement": m} for m in misconceptions[:10]],
        "key_terms_glossary": {},
    }
    return _build_extraction_result(data, partials)
