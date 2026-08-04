# Gyantra Architecture Documentation

This document describes the actual implemented architecture of Gyantra.

## System Overview

Gyantra is a multi-provider LLM pipeline system that converts educational documents (e.g., textbook chapters) into a structured **Teacher Knowledge Package (TKP)**. The TKP contains educational classification, knowledge extraction (concepts, facts), a period-by-period teaching plan, classroom content, activities, assessments, misconception gap analysis, and a grounding validation audit.

The system is split into:
1. **React/Vite Frontend** — Responsive UI built with React, Vite, and TailwindCSS.
2. **FastAPI Backend** — Python FastAPI backend orchestrating the 10-stage pipeline, storing job states in SQLite, and generating exports.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           GYANTRA SYSTEM ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────────┐  │
│  │    REACT     │    │    FASTAPI   │    │     PIPELINE ORCHESTRATOR    │  │
│  │   FRONTEND   │◀──▶│    BACKEND   │◀──▶│      (pipeline.py)           │  │
│  │  (Vite + TS) │    │  (Uvicorn)   │    │                              │  │
│  │              │    │              │    │  ┌────────────────────────┐  │  │
│  │ • Upload UI  │    │ • REST API   │    │  │ 1. Doc Intelligence    │  │  │
│  │ • Progress   │    │ • SSE Stream │    │  │ 2. Classification       │  │  │
│  │ • Preview    │    │ • Job Mgmt   │    │  │ 3. Knowledge Extraction │  │  │
│  │ • Export     │    │ • File Store │    │  │ 4. Teaching Planner     │  │  │
│  └──────────────┘    └──────────────┘    │  │ 5. Classroom Content   │  │  │
│         ▲                  ▲              │  │ 6. Activity Generation  │  │  │
│         │                  │              │  │ 7. Assessment Gen       │  │  │
│         │                  │              │  │ 8. Gap Analysis         │  │  │
│         │                  │              │  │ 9. Validation           │  │  │
│         └──────────────────┘              │  │ 10. Publishing          │  │  │
│                    SSE                        └────────────────────────┘  │  │
│                                                        ▲                  │  │
│                                                        │                  │  │
│                              ┌─────────────────────────┴───┐              │  │
│                              │   LLM CLIENT (llm_client.py)│              │  │
│                              ├─────────────────────────────┤              │  │
│                              │  Provider Failover Chain:   │              │  │
│                              │  • Gemini (Primary)         │              │  │
│                              │  • RoutesMe / Nvidia NIM    │              │  │
│                              │  • Groq / OpenRouter        │              │  │
│                              └─────────────────────────────┘              │  │
│                                             ▲                             │  │
│                              ┌──────────────┴──────────────┐             │  │
│                              │      DATA LAYER             │             │  │
│                              │                             │             │  │
│                              │ • SQLite (jobs, packages)   │             │  │
│                              │ • File System (uploads,     │             │  │
│                              │   exports)                  │             │  │
│                              └─────────────────────────────┘             │  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. Frontend (React/Vite)
- **Tech Stack**: React, Vite, TailwindCSS.
- **Responsibilities**:
  - File upload with teaching preferences (style, period duration, etc.).
  - Real-time progress display using **Server-Sent Events (SSE)** with automatic fallback to polling.
  - Interactive Preview panel to view the generated Overview, Concepts, Lesson Plan, Activities, Assessments, and Gap Analysis.
  - Download options for the raw JSON and ReportLab-generated PDFs.

### 2. Backend API (FastAPI)
- **File**: `backend/app/main.py`
- **Endpoints**:
  - `POST /api/upload` — Validates upload size/type, creates a database job record, and fires the async background task.
  - `GET /api/jobs/{job_id}` — Returns the job status, metadata, and full TKP result if completed.
  - `GET /api/jobs/{job_id}/progress` — Direct Server-Sent Events stream for real-time stage updates.
  - `GET /api/jobs/{job_id}/download/{format}` — Serves generated export files (JSON/PDF).
  - `GET /api/health` — API health check.

### 3. Pipeline Orchestrator
- **File**: `backend/app/services/pipeline.py`
- **Responsibilities**:
  - Sequentially triggers each of the 10 stages.
  - Manages stage timeouts and records telemetry metrics.
  - Integrates two core execution engines:
    - `stages_knowledge.py` — Handles extraction, classification, gap analysis, and validation.
    - `stages_pedagogy.py` — Handles lesson planning, classroom content, activities, and assessments.

### 4. LLM Client & Resilient Routing
- **File**: `backend/app/services/llm_client.py` & `backend/app/services/providers.py`
- **Multi-Provider Priority Order**: Tries configured LLM endpoints in sequence: `gemini` $\rightarrow$ `routesme` $\rightarrow$ `nvidia` $\rightarrow$ `groq` $\rightarrow$ `openrouter`.
- **Primary Configuration**:
  - `gemini-3.5-flash-lite` (for FAST, GENERATE stages)
  - `gemini-3.1-flash-lite` (for EXTRACT, PLAN, VALIDATE stages)
- **JSON Parsing Safeguards**:
  - Implements dynamic bracket-matching regex to extract valid JSON blocks from conversational wrappers.
  - Uses `json.loads(..., strict=False)` to prevent parsing crashes due to unescaped control characters.
- **Failover Handling**:
  - Automatically parses `Retry-After` headers during HTTP 429 rate limit errors to compute intelligent delay periods.
  - Fallback mechanisms transition tasks to secondary providers (Nvidia NIM, Groq, RoutesMe) if the timeout/delay threshold is breached.

### 5. Document Parsers
- **Module**: `backend/app/parsers/`
- **Parsers**:
  - `pdf_parser.py` — Extracts text, tables, headers, and equations using PyMuPDF.
  - `docx_parser.py` — Parses paragraphs, tables, and structures using python-docx.
  - `pptx_parser.py` — Parses slide shapes and structures.
  - `docling_parser.py` — Handles high-fidelity layout analysis when available.
  - `ocr_fallback.py` — Uses Tesseract for scanned/image documents.
- **Router** (`router.py`): Automatically selects the most appropriate parser depending on format and capabilities.

### 6. Validation Engine
- **File**: `backend/app/services/validation.py`
- **Checks**:
  - Schema integrity and structure verification (Pydantic model compliance).
  - Completeness of periods, concepts, and materials.
  - Consistency of references across pedagogical stages.
  - Grounding audit (hallucination risk): Uses a lexical filter to index concepts and check grounding, then relies on LLM adjudication only for suspect claims.

### 7. Exporter (ReportLab)
- **File**: `backend/app/services/exporter.py`
- **Outputs**:
  - `TeacherKnowledgePackage.json` — Machine-readable structured package.
  - `LessonPlan.pdf` — PDF layout organizing lesson plans by periods.
  - `TeacherGuide.pdf` — Reference guide for teacher concepts and misconception analyses.
  - `AssessmentPack.pdf` — Exam blueprints, questions, and detailed answer keys.

---

## Data Flow

```
1. UPLOAD:
   User → React Form → FastAPI POST /api/upload
   → Save upload file → Insert database JobRecord
   → Launch background thread task (run_pipeline)

2. PIPELINE EXECUTION:
   For Stage 1 to 10:
     → Telemetry tracks stage start
     → Invoke stage service (stages_knowledge or stages_pedagogy)
     → Parse result into structured Pydantic models
     → Save intermediate telemetry to db and broadcast progress
   
   Final:
     → Run validation audit
     → Invoke exporter to build JSON & PDFs
     → Mark JobRecord status as COMPLETED

3. SSE STREAMING:
   React Frontend → EventSource GET /api/jobs/{id}/progress
   → Receives JSON chunks detailing current stage, stage progress, and logs
   → Fallback to standard HTTP polling if SSE is blocked

4. EXPORT:
   React Frontend → GET /api/jobs/{id}/download/{format}
   → Direct FileResponse download from the local storage directories
```

---

## Security & Scalability

- **API Security**: Keys are managed entirely through environment variables (`.env`). Upload limits are enforced (25MB standard).
- **Concurrency**: SQLite manages simultaneous connections using WAL mode. The pipeline processes single jobs sequentially on background threads.
- **Docker-Ready**: Configured for containerization via multi-stage Dockerfiles (`backend/Dockerfile`, `frontend/Dockerfile`) and orchestrated using `docker-compose.yml`.

---
*Document Version: 1.1 | Final Realized System Architecture*