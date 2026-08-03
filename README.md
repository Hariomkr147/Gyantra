# Gyantra

**From Chapter to Classroom.** Gyantra converts an educational document into a
structured, grounded **Teacher Knowledge Package (TKP)**: an adaptive lesson
plan, classroom scripts, activities, assessments, a misconception analysis, and a
validation report — every fact traceable to the source document.

```
Upload a chapter  →  10-stage pipeline  →  Review in the UI  →  Export JSON + PDFs
```

---

## Table of contents

- [Quick start](#quick-start)
- [Architecture](#architecture)
- [The 10-stage pipeline](#the-10-stage-pipeline)
- [How grounding works](#how-grounding-works)
- [Token-budget strategy](#token-budget-strategy)
- [Model routing and failover](#model-routing-and-failover)
- [API reference](#api-reference)
- [Output contract](#output-contract)
- [Configuration](#configuration)
- [Testing](#testing)
- [Project layout](#project-layout)
- [Design decisions and trade-offs](#design-decisions-and-trade-offs)
- [Bonus Features Implemented](#bonus-features-implemented)

---

## Quick start

### Option 1 — Docker (recommended)

```bash
cp .env.example .env
# Add a key to .env: GEMINI_API_KEY=... (recommended), GROQ_API_KEY=...,
# or OPENROUTER_API_KEY=...   Or set DEMO_MODE=true to run with no key.

docker compose up --build
```

- Frontend → <http://localhost:5173>
- API docs → <http://localhost:8000/docs>

### Option 2 — Local development

**Backend**

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example .env      # note: backend/.env, not the repo root
uvicorn app.main:app --reload --port 8000
```

Settings load relative to the working directory, so the file must be
`backend/.env` and the server must be started from `backend/`.

**Frontend** (separate terminal)

```bash
cd frontend
npm install
npm run dev                  # http://localhost:5173, proxies /api to :8000
```

### Trying it without an API key

Set `DEMO_MODE=true`. The full ten-stage pipeline runs against a deterministic
offline stub, so you can walk the entire UI, stream progress, and download real
PDFs. Output is structurally valid but pedagogically shallow, and every package
is tagged `metadata.demo_mode = true` so it can never be mistaken for real model
output.

> **OCR note:** scanned PDFs need `tesseract` on PATH. The Docker image includes
> it. For a local run either install `tesseract-ocr` or set `OCR_ENABLED=false`.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  BROWSER                                                                 │
│  React + Vite + Tailwind                                                 │
│  Landing · Upload · Live progress (SSE) · Output viewer · Exports         │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │  REST + Server-Sent Events
┌───────────────────────────────▼──────────────────────────────────────────┐
│  FastAPI                                                                 │
│  POST /api/upload   GET /api/jobs/{id}   GET /api/jobs/{id}/progress      │
│  GET  /api/jobs/{id}/download/{format}                                   │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │  BackgroundTasks
┌───────────────────────────────▼──────────────────────────────────────────┐
│  PIPELINE ORCHESTRATOR            ProgressReporter ──► SSE fan-out        │
│                                                                          │
│   1 Document Intelligence  ─┐                                            │
│   2 Classification          │  each stage: typed input → typed output,    │
│   3 Knowledge Extraction    │  persisted to exports/{job}/stages/*.json   │
│   4 Teaching Planner        │                                            │
│   5 Classroom Content       ├─► critical stages abort on failure;         │
│   6 Activities              │   optional stages degrade and continue      │
│   7 Assessments             │                                            │
│   8 Gap Analysis            │                                            │
│   9 Validation              │                                            │
│  10 Publishing             ─┘                                            │
└──────┬──────────────┬───────────────┬──────────────────┬─────────────────┘
       │              │               │                  │
┌──────▼─────┐ ┌──────▼──────┐ ┌──────▼───────┐ ┌────────▼────────┐
│  PARSERS   │ │  CHUNKER +  │ │  LLM CLIENT  │ │  VALIDATION      │
│            │ │  RETRIEVAL  │ │              │ │                  │
│ PDF (fitz) │ │ heading-    │ │ OpenRouter   │ │ schema           │
│ DOCX       │ │ aligned     │ │ Groq         │ │ consistency      │
│ PPTX       │ │ sections    │ │              │ │ pedagogy         │
│ TXT / MD   │ │ SectionIndex│ │ retry →      │ │ grounding        │
│ OCR        │ │ keyword     │ │ failover →   │ │ (lexical + LLM)  │
│ + router   │ │ retrieval   │ │ disk cache   │ │                  │
└────────────┘ └─────────────┘ └──────────────┘ └──────────────────┘
       │                                                  │
┌──────▼──────────────────────────────────────────────────▼─────────────────┐
│  STORAGE   SQLite (jobs, packages) · filesystem (uploads, exports, cache)  │
└───────────────────────────────────────────────────────────────────────────┘
```

**Orchestration pattern:** a custom async orchestrator, not LangChain or
LlamaIndex. Each stage is a plain async function with a Pydantic input and
output. The reasons: the ten stages are a fixed known sequence rather than an
agent deciding its own path, so a framework's planning machinery adds
indirection without buying anything; failure handling needs to be per-stage
(some abort, some degrade), which is clearer as explicit code; and the
dependency surface stays small, which matters for a solo build.

Where multi-agent separation does apply, it is by **role**: each stage has its
own system prompt, its own output schema, and its own model tier — a classifier,
an extractor, a planner, a content writer, and an auditor. The auditor
deliberately never sees the generator's reasoning, only its output and the
source, so the grounding check stays adversarial.

The pipeline is managed by a centralized `AgentCoordinator` (in `agents.py`) which maps 
these roles to pipeline stages, dynamically selecting the correct prompt instruction 
based on the `LANGUAGE_INSTRUCTION` derived from the document profile.

---

## The 10-stage pipeline

| # | Stage | Input | Output | Model role |
|---|-------|-------|--------|-----------|
| 1 | Document Intelligence | uploaded file | `DocumentIntelligenceResult` — blocks, tables, figures, equations | none (code) |
| 2 | Educational Classification | headings + 2 samples | `DocumentProfile` | fast |
| 3 | Knowledge Extraction | chunks (map-reduce) | `KnowledgeExtractionResult` | extract |
| 4 | Teaching Planner | concept list only | `TeachingPlan` | plan |
| 5 | Classroom Content | one period + its chunks | `ClassroomContent[]` | generate |
| 6 | Activity Generation | plan + core concepts | `Activity[]` | generate |
| 7 | Assessment Generation | concepts + definitions | `AssessmentPack` | generate |
| 8 | Learning Gap Analysis | concept list | `GapAnalysis` | extract |
| 9 | Validation | whole package | `ValidationRecord` | validate |
| 10 | Publishing | whole package | JSON + 3 PDFs | none (code) |

**Adaptive period count.** Stage 4 is explicitly instructed not to default to
five periods; it chooses a count from concept volume, conceptual difficulty,
grade level, and any teacher-stated time constraint, and must justify the choice
in `adaptation_rationale`. If the planning model fails, a deterministic fallback
groups concepts by a difficulty-weighted load budget — still adaptive, just
without the model. The two bundled samples produce 3 periods each from their
content rather than a template number.

**Failure policy.** Stages 1–4 are critical: without a parse, a profile,
concepts, and a plan there is no package, so a failure aborts the job with a
specific message. Stages 5–9 degrade — the failure is recorded on that stage,
the UI shows it, and the run continues so the teacher still gets a partial
package rather than nothing.

---

## How grounding works

The FAQ draws a specific line: factual and conceptual content must come from the
primary source, while pedagogical scaffolding may come from elsewhere as long as
it is distinguishable. Gyantra enforces that line in four places.

**1. Provenance in the type system.** Every content-bearing model carries an
`origin` field of `source` or `pedagogical`. Concepts, definitions, formulas and
examples are `source`. Activities, applications and the mentor moment are
`pedagogical`. The distinction survives into the JSON export and is surfaced in
the UI as a badge, so a teacher always knows which is which.

**2. Source references.** Concepts and definitions carry a `source_ref` with the
chunk IDs and page numbers they were extracted from. Because extraction runs
per-section, provenance is recorded during the map step and reattached after the
merge step — the merge itself would otherwise lose it.

**3. Retrieval, not recall.** Content generation never asks a model to write
from memory about a topic. Each period's generation call receives only the source
chunks tied to that period's concepts, and is told all factual content must come
from that text.

**4. A two-pass audit.** Stage 9 builds a vocabulary from the source document
plus everything extraction found, then scores every generated claim by the
fraction of its content words absent from that vocabulary. Claims above the
threshold are shortlisted, and only that shortlist goes to a model for
adjudication. This keeps validation cheap and stable — the deterministic pass
does the bulk filtering, and the model only judges genuinely ambiguous cases.

The lexical pass applies light suffix stemming before comparing. Without it,
"newtons" in generated content reads as ungrounded against "Newton's" in the
source, which produced false hallucination flags on correct material during
development.

`hallucination_risk` is reported as a number, and the specific flagged claims
are shown in the validation panel rather than hidden.

---

## Token-budget strategy

Free and open-weight endpoints have small context windows and real rate limits.
The design assumption is a ~8k context, not a 200k one.

**The document is parsed once and chunked once.** Every later stage retrieves
from that index instead of re-reading the document.

**Chunks align to headings, not to a fixed size.** `chunk_by_headings` runs three
passes: split at every heading; split any section that still exceeds the token
target (falling back to word-level wrapping for a single long paragraph with no
line breaks); then merge negligible stubs and cap the total count. The result
respects document structure — so extraction stays section-scoped and citable —
while keeping every chunk inside budget. `MAX_CHUNKS` bounds total extraction
cost on long inputs.

**Per-stage context discipline:**

| Stage | What it actually receives |
|-------|--------------------------|
| Classification | headings + two ~1.5k samples, never the whole document |
| Extraction | one chunk per call, in parallel with a concurrency cap |
| Extraction merge | compacted partial results, verbose fields dropped before truncating |
| Planning | the structured concept list only — zero raw document text |
| Content | one period, plus only the chunks tied to its concepts |
| Assessments | concepts + definitions + a bounded snippet sample |
| Validation | structured objects and a shortlist of claims, not the source |

**Map-reduce for extraction.** Each chunk is extracted independently, then a
single merge call deduplicates and orders the results. When the merge call fails,
a deterministic code path merges instead, so a long document degrades in quality
rather than failing outright.

**Disk cache.** Responses are cached on `(model, prompt)`. Re-running the same
document during development costs nothing, which also makes the test suite fast.

---

## Model routing and failover

Stages map to **roles**, and roles map to concrete model IDs per provider. The
orchestrator asks for "the extraction model" and never names a vendor.

| Role | Used by | Why |
|------|---------|-----|
| `fast` | classification | small structured decision, wants determinism (`temperature 0.1`) |
| `extract` | knowledge extraction, gap analysis | instruction-following over source text |
| `plan` | teaching planner | sequencing and pedagogical judgement |
| `generate` | content, activities, assessments | longer creative output (`temperature 0.4–0.5`) |
| `validate` | grounding audit | critical reading (`temperature 0.0`) |

**Providers are adapters.** `providers.py` defines a base interface plus one
adapter each for Gemini, OpenRouter and Groq. Gemini's wire format is genuinely
different (system instruction, `contents`, `responseMimeType`), so it gets its
own request builder; OpenRouter and Groq share the OpenAI-compatible path. A
fourth provider is a new class, not a change to the pipeline.

**Fail-fast failover.** Each adapter classifies every failure:
- `retry` — transient (429, 5xx, timeout); retry with backoff.
- `failover` — permanent (404 dead model, 401/403 bad key, 400 unsupported
  param); move to the next provider immediately, no retries.
- A 429 that quotes a retry delay longer than `RATE_LIMIT_WAIT_CEILING` is
  treated as failover — waiting 25 minutes to burn one attempt is pointless.

The old client retried everything, so a permanently dead model ID burned three
attempts with backoff on every stage. That is what made the pipeline appear to
hang at 10%: stage 1 finished and the first LLM call silently crawled through
dead retries. Permanent errors now fail over in a single request.

**Startup verification.** `LLM_PROBE_ON_STARTUP` sends a tiny request to each
configured provider at boot and logs OK/FAIL per provider, so a revoked key or
rotated-away model is visible before anyone uploads a document. `/api/health`
reports the configured providers and `?probe=true` runs a live probe.

**Why Gemini first.** Google AI Studio's free tier is the most reliable of the
three and its model IDs are stable. OpenRouter rotates free models in and out
without notice — `google/gemma-2-9b-it:free` and
`meta-llama/llama-3.3-70b-instruct:free` are gone as of this writing, which is
precisely the failure mode that used to stall the pipeline. Gemini also accepts
`responseSchema`, so JSON output is structurally constrained rather than merely
requested.

**Reasoning-model guard.** Several open-weight models wrap chain-of-thought in
`<think>` blocks before the JSON. `_extract_json` strips those blocks (and the
unterminated-tag case where the model runs out of tokens mid-thought), which is
why nemotron's output finally parsed. The OpenRouter defaults deliberately use
instruction-tuned models over reasoning models to avoid the truncation in the
first place.

---

## Document parsing

**Docling is the primary parser** for PDF, DOCX and PPTX. It produces a real
document model — reading order, table structure, heading hierarchy — where the
font-size heuristics in the built-in PDF parser can only approximate them. That
matters most on multi-column NCERT layouts, where visual order and reading order
diverge.

The built-in parsers (PyMuPDF, python-docx, python-pptx, plain text, OCR) remain
as the **automatic fallback**. Docling is never allowed to break a job:

| Situation | Behaviour |
|-----------|-----------|
| Docling not installed | built-in parser, logged once at startup |
| `DOCLING_ENABLED=false` | built-in parser |
| Less than `DOCLING_MIN_MEMORY_MB` free | skipped before it can fail |
| Conversion raises mid-parse | caught, falls back, reason recorded on the package |
| Plain text / Markdown | skipped — already structured, docling would add cost for nothing |
| Scanned PDF (OCR route) | dedicated OCR path, not docling |

Every fallback records `metadata.docling_fallback_reason` on the result, so the
JSON export always says which parser ran and why.

Two operational details worth knowing:

- **Models download at startup, not on first upload.** Docling pulls several
  hundred MB of layout models on first use; lazily, that lands inside a
  teacher's first upload and looks like a four-minute hang.
  `DOCLING_WARMUP_ON_STARTUP` moves it to boot. Warm parses take ~1s.
- **Memory is checked before use.** Docling's layout models need roughly 1.5 GB
  of headroom; below that the native layer dies with `std::bad_alloc`. Gyantra
  probes free memory and skips docling rather than crashing mid-parse. Docling's
  own OCR stage is disabled for the same reason — Gyantra has a dedicated OCR
  path that costs far less.

Heading depth is derived from section numbering (`8.1` → level 2, `8.2.1` →
level 3) rather than from docling's own level field, which labels every
`section_header` as level 1. Without that, a chapter's structure flattens and
heading-aligned chunking stops working.

---

## API reference

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/upload` | Upload a document, create a job, start the pipeline. Returns `202` with `job_id`. |
| `GET` | `/api/jobs` | Recent jobs for the library view. |
| `GET` | `/api/jobs/{id}` | Job status, per-stage progress, and the full package once ready. |
| `GET` | `/api/jobs/{id}/progress` | **SSE** progress stream. |
| `GET` | `/api/jobs/{id}/package` | Just the TKP JSON. |
| `GET` | `/api/jobs/{id}/download/{format}` | `json` · `lesson-plan` · `teacher-guide` · `assessments` |
| `DELETE` | `/api/jobs/{id}` | Delete a job and its artifacts. |
| `GET` | `/api/health` | Health plus which LLM providers are configured. |
| `GET` | `/api/config/options` | Form options and limits, so the frontend hardcodes nothing. |

### Progress streaming

```
data: {"type":"stage_started","stage":"classroom_content","progress":44,
       "label":"Classroom Content","message":"Writing material for 3 periods"}

data: {"type":"stage_progress","stage":"classroom_content","progress":50,
       "message":"Generating periods (2/3)"}

data: {"type":"stage_completed","stage":"classroom_content","progress":62,
       "message":"3 period(s) written"}
```

Three details that matter in practice:

- **A late subscriber is not stranded.** The stream opens with a `snapshot`
  event carrying full current state, so a page reload mid-job renders correctly.
- **Fan-out stages report sub-progress.** Extraction and content generation
  interpolate within their percentage range, so the bar moves during the slowest
  stages instead of appearing frozen.
- **The client falls back to polling.** Some proxies and free hosts buffer or
  drop event streams; `subscribeToProgress` detects a dead `EventSource` and
  switches to 2-second polling with the same callback contract.

---

## Output contract

```jsonc
{
  "metadata": {
    "job_id": "…", "created_at": "…", "processing_time_seconds": 41.2,
    "model_calls": 14, "total_tokens_used": 18432,
    "models_used": ["…"], "demo_mode": false
  },
  "document_intelligence": { "blocks": [], "page_count": 6, "parse_route": "…" },
  "document_profile":      { "subject": "Physics", "grade": "Class 9", "…": "…" },
  "knowledge_extraction":  { "concepts": [], "definitions": [], "formulas": [] },
  "teaching_plan":         { "total_periods": 3, "adaptation_rationale": "…" },
  "classroom_content":     [ { "period_id": "…", "teacher_script": "…" } ],
  "activities":            [ { "activity_type": "demonstration", "…": "…" } ],
  "assessments":           { "items": { "mcqs": [], "short_answers": [] } },
  "gap_analysis":          { "misconceptions": [] },
  "validation":            { "overall_status": "pass", "grounding_check": {} },
  "exports":               { "json_path": "…", "lesson_plan_pdf_path": "…" }
}
```

Four artifacts are produced per job: the canonical JSON, a **Lesson Plan PDF**
(period-by-period, ready to teach from), a **Teacher Guide PDF** (concept
reference, activity bank, gap analysis, validation report), and an **Assessment
Pack PDF** (questions, then the answer key on separate pages so it can be
printed and split).

### Samples

`samples/` holds two generated packages plus the source documents they came from:

| Sample | Subject | Concepts | Periods | Notes |
|--------|---------|----------|---------|-------|
| `force_and_laws_of_motion_TeacherKnowledgePackage.json` | Physics, Class 9 | 5 | 3 | STEM — extracts 2 formulas |
| `nationalism_in_india_TeacherKnowledgePackage.json` | History, Class 10 | 5 | 3 | Humanities — 0 formulas, narrative concepts |

The contrast is the point: the same pipeline extracts formulas from the physics
chapter and none from the history chapter, and both chose their period count from
content rather than a template. Regenerate with:

```bash
cd backend && python -m tests.generate_samples
```

> These samples were generated in `DEMO_MODE`, so their prose is illustrative.
> The *structure*, routing, adaptivity, and validation behaviour are real.

---

## Configuration

Every setting is an environment variable; see [`.env.example`](.env.example) for
the annotated list. The ones worth knowing:

| Variable | Default | Notes |
|----------|---------|-------|
| `GEMINI_API_KEY` | — | Recommended primary. Or Groq / OpenRouter, unless `DEMO_MODE=true` |
| `LLM_PROVIDER` | `gemini,groq,openrouter` | Preference order for failover |
| `DEMO_MODE` | `false` | Run offline with the deterministic stub |
| `LLM_PROBE_ON_STARTUP` | `true` | Verify every provider at boot |
| `RATE_LIMIT_WAIT_CEILING` | `20` | Seconds; a longer quoted 429 delay triggers failover |
| `GEMINI_MODEL_*` etc. | see `.env.example` | Per-role model IDs, per provider |
| `DOCLING_ENABLED` | `true` | Primary parser; falls back automatically |
| `DOCLING_WARMUP_ON_STARTUP` | `true` | Download models at boot, not mid-upload |
| `DOCLING_MIN_MEMORY_MB` | `1500` | Skip docling below this much free RAM |
| `CHUNK_TARGET_TOKENS` | `700` | Raise for large-context models |
| `MAX_CHUNKS` | `40` | Caps extraction cost on long documents |
| `PARALLEL_PERIOD_GENERATION` | `2` | Keep low on free tiers to avoid rate limits |
| `OCR_ENABLED` | `true` | Needs `tesseract` on PATH |
| `MAX_FILE_SIZE_MB` | `25` | Enforced while streaming, not after |

### If generation fails

The failure is surfaced in the UI with a plain-language explanation, the
technical detail behind a disclosure, and a retry action. To diagnose:

```bash
curl 'http://localhost:8000/api/health?probe=true'   # live per-provider check
```

The backend log records every attempt as
`[stage] provider/model  status  elapsed  tokens`, so a stalled or failing stage
is visible rather than silent.

---

## Frontend design system

The landing page is dark, the workspace is light, and both use **one component
set**. That only works because components reference semantic tokens rather than
palette steps:

```
--fg / --fg-muted / --fg-subtle      text, three levels of emphasis
--surface / --surface-sunken         cards and code blocks
--border / --border-strong           boundaries
--accent / --accent-fg               the single accent colour
--success / --warn / --danger        status
--syn-key / --syn-string / ...       JSON viewer syntax
```

`text-fg-muted` resolves to a light grey on dark and a dark grey on light, so a
card looks correct in either context with no per-page overrides. The earlier
version hardcoded dark-palette classes (`text-ink-300` on `bg-ink-900`) inside
the light workspace, which is why text was washing out — light grey text on a
white card.

**Contrast is verified, not assumed.** `frontend/src/styles/contrast.test.mjs`
computes WCAG ratios for all 72 foreground/background combinations across both
themes and exits non-zero on any failure:

```bash
cd frontend && node src/styles/contrast.test.mjs
# dark   36 pairs checked, worst: fg-subtle on subtle = 4.63:1
# light  36 pairs checked, worst: syn-key on sunken   = 3.58:1
# PASS — 72 pairs meet WCAG AA.
```

Two token values were corrected by that check rather than by eye: dark
`fg-subtle` measured 3.75:1 against `--surface` (below the 4.5 body-text floor)
and light `fg-subtle` measured 4.34:1 against `--subtle`. Both now clear AA.

Other accessibility work: visible focus rings on every interactive element, a
skip-to-content link, `aria-expanded`/`aria-controls` on disclosures, arrow-key
tab navigation, status conveyed by text and icon rather than colour alone, and
`prefers-reduced-motion` replacing animation with instant transitions.

---

## Testing

```bash
cd backend && python -m pytest        # 65 passed, 2 skipped
cd frontend && node src/styles/contrast.test.mjs
```

| File | Covers |
|------|--------|
| `test_parsers.py` | structure extraction, heading levels, routing decisions, language detection |
| `test_pipeline.py` | chunker behaviour, validation checks, heuristic planner |
| `test_docling.py` | heading-depth derivation, resource handling, and every fallback path |
| `test_e2e.py` | all 10 stages via the stub; progress ordering; clean failure on unreadable input |
| `test_api.py` | upload validation, full job lifecycle, PDF downloads, SSE, delete |

The two skips are the real Docling conversion tests, which are gated on
available memory — they skip rather than fail on a constrained machine, since
`std::bad_alloc` from a native library says nothing about the code under test.

The end-to-end tests assert on real properties rather than smoke-passing: that
progress is monotonic and never regresses, that stage completion percentages
match their declared ranges, that every extracted concept is scheduled into some
period, and that each exported PDF starts with `%PDF` and is not truncated.

Bugs caught by these tests during development, each now covered by a regression
test:

- a ReportLab API misuse that broke all PDF export
- a chunker that silently ignored heading boundaries, collapsing multi-section
  chapters into one chunk
- an oversized-section splitter that could not split a paragraph with no line
  breaks
- dead default model IDs that stalled the pipeline at 10% (see
  [Model routing](#model-routing-and-failover))
- two theme tokens below the WCAG AA contrast floor

---

## Project layout

```
gyantra/
├─ backend/
│  ├─ app/
│  │  ├─ main.py                    FastAPI app, CORS, lifespan
│  │  ├─ config.py                  pydantic-settings
│  │  ├─ api/routes.py              REST + SSE
│  │  ├─ models/
│  │  │  ├─ enums.py                stages, statuses, origins
│  │  │  └─ schemas.py              every stage contract + the TKP
│  │  ├─ parsers/
│  │  │  ├─ router.py               cost-aware routing + escalation
│  │  │  ├─ pdf_parser.py           PyMuPDF, font-size heading detection
│  │  │  ├─ docx_parser.py  pptx_parser.py  text_parser.py  ocr_fallback.py
│  │  └─ services/
│  │     ├─ pipeline.py             the orchestrator
│  │     ├─ stages_knowledge.py     stages 2–3
│  │     ├─ stages_pedagogy.py      stages 4–8
│  │     ├─ validation.py           stage 9
│  │     ├─ exporter.py             stage 10
│  │     ├─ chunker.py              chunking + SectionIndex retrieval
│  │     ├─ llm_client.py           providers, retry, failover, cache
│  │     ├─ model_registry.py       stage → role → model
│  │     ├─ prompts.py              all prompt templates
│  │     ├─ demo_llm.py             offline stub
│  │     ├─ progress.py  job_store.py
│  │  └─ tests/                     48 tests + sample generator
├─ frontend/
│  └─ src/
│     ├─ pages/                     Landing, Dashboard, Upload, JobProgress, Output, Library
│     ├─ components/{ui,layout,upload,pipeline,output}/
│     └─ lib/                       api client, constants, utils
├─ samples/                         2 generated TKPs + source documents
└─ docker-compose.yml  .env.example
```

---

## Design decisions and trade-offs

**Custom orchestrator over LangChain.** The pipeline is a fixed sequence, not an
agent choosing its own path. A framework would add a planning layer with nothing
to plan, and would make the per-stage failure policy harder to read. The cost is
writing the retry and failover logic by hand — about 200 lines in
`llm_client.py`.

**React over Streamlit.** The charter allowed either. Streamlit would have been
faster to build, but the progress experience is central to this product — live
stage transitions, sub-stage progress, reviewing completed sections while later
ones run — and Streamlit's rerun model fights all three. The cost is a second
toolchain and a Docker stage.

**SQLite and in-process background tasks over Postgres and Celery.** The
workload is one document at a time for one teacher. A broker would add
infrastructure without removing a real constraint. The honest limit: a server
restart mid-job orphans that job, and concurrent write throughput is low. Both
are acceptable for a prototype and neither is load-bearing on the architecture —
`JobStore` is the only thing that would change.

**Sequential stages, parallel within a stage.** Stages have genuine data
dependencies, so the sequence is inherent rather than a simplification. The
fan-out points — per-chunk extraction and per-period content — run concurrently
under a semaphore. The cap is deliberately low (2) because free-tier endpoints
reject bursts, and a rejected batch costs more wall-clock time than running
narrower.

**Deterministic checks before model-based ones.** Three of the four validation
checks are pure code and always reliable. Only grounding needs judgement, and
even there a lexical pre-filter does the bulk of the work so the model adjudicates
a shortlist. This keeps validation fast, mostly deterministic, and cheap enough
to run on every job.

### Known limits

- Retrieval is keyword-based, not embedding-based. It is deterministic and needs
  no vector store, which suits the size of a single chapter, but it will miss
  paraphrased matches. An embedding index is the obvious upgrade.
- Docling needs ~1.5 GB of free RAM and adds a slow first startup while it
  downloads models. On a constrained machine Gyantra silently uses the built-in
  parsers instead — correct behaviour, but the parse quality is lower, and the
  only signal is `metadata.docling_fallback_reason` in the output.
- Free provider tiers have daily token caps. Failover covers one provider
  running out, but if every configured provider is exhausted the job fails with
  a rate-limit message; there is no queue-and-resume.
- No authentication. Single-user by design, per the charter's scope. Do not
  expose an instance publicly without adding it.
- Table extraction quality tracks PyMuPDF's detector; complex nested or
  borderless layouts degrade to plain text.
- Multilingual support extends to script detection and generating in the
  document's language when the model supports it. It is not a full localisation
  path.
- `demo_mode` output is structurally complete but pedagogically generic. It
  exists to demonstrate and test the system, not to teach from.

---

## Bonus Features Implemented

This repository includes several advanced "Bonus" features beyond the core capabilities:

### 1. Multi-Agent Orchestration
The pipeline utilizes an **Agent Coordinator** (`backend/app/services/agents.py`) to decouple execution logic from model roles. Different agents (`EXTRACTOR`, `PLANNER`, `CONTENT_WRITER`) are dynamically routed to specific API endpoints based on the `DocumentProfile` and stage requirements, complete with traceable role execution logs.

### 2. Curriculum Alignment
After knowledge extraction, the system automatically detects the pedagogical framework (e.g., CBSE, ICSE, NGSS) and runs a **Standards Mapping** pass (`backend/app/services/curriculum.py`). This identifies exactly which standard codes (e.g., `CBSE-SCI-09-02`) the content covers, complete with a coverage score that is rendered in the Output Dashboard.

### 3. Observability & Telemetry
A dedicated **JobTelemetry** tracker intercepts every request at the `LLMClient` level. It tracks wall-clock time, LLM cost estimates, token usage, and cache hit rates. These statistics are bundled into the final `TeacherKnowledgePackage.json` metadata and visualized directly in the frontend's Overview tab.

### 4. Multilingual Support
Teachers can select from **6 output languages** (English, Hindi, Bengali, Tamil, Telugu, Marathi) via the frontend upload form. The orchestrator injects strict `LANGUAGE_INSTRUCTION` rules into the system prompts. Crucially, the agents are instructed to translate the *pedagogical prose* (like scripts and activity instructions) while leaving *technical terms* (like "Velocity", "Newton's Laws") in English, maximizing classroom utility for ESL/Bilingual education.

---

## Production & Future Considerations

While Gyantra is fully functional for free-tier deployments, migrating to a high-scale production environment unlocks additional capabilities. The architecture is designed to support the following upgrades seamlessly:

1. **Enable Deep OCR & Layout Parsing:** 
   In free-tier deployments, memory-heavy document layout models (like `docling` and Tesseract OCR) are disabled by default to stay within the 512MB RAM limits and prevent Out Of Memory (OOM) crashes. In production with dedicated RAM (>= 2GB), setting `DOCLING_ENABLED=true` and `OCR_ENABLED=true` allows the pipeline to perfectly digest complex two-column layouts, deep tables, and scanned/image-heavy PDFs.
2. **Migrate to PostgreSQL:**
   Gyantra currently uses SQLite + `aiosqlite` for zero-configuration deployments. For horizontally scaled production environments, the SQLAlchemy ORM layer can trivially be pointed to a PostgreSQL database by simply updating the `DATABASE_URL` environment variable.
3. **Phase-Wise Parallelization:**
   The `AgentCoordinator` orchestrates LLM calls. Currently, lesson periods are generated with limited concurrency (`parallel_period_generation = 2`). In production with higher API rate limits, this can be increased, or entire stages (like Assessment Generation and Content Validation) can be parallelized to drastically reduce the total generation time.
4. **Authentication & Rate Limiting:**
   A full production environment should integrate robust API key authentication (e.g., JWT-based auth via Auth0 or custom middleware) and user-specific rate limiting to protect LLM budgets and prevent abuse.
5. **Advanced Model Routing:**
   Integrating better API keys and utilizing provider fallback chains (e.g., routing complex reasoning to GPT-4o or Claude 3.5 Sonnet, while routing simpler extractions to faster models like Gemini 1.5 Flash) can optimize both cost and quality at scale.
