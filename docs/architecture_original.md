# Gyantra Architecture Documentation

## System Overview

Gyantra is a microservice-style pipeline architecture for converting educational documents into Teacher Knowledge Packages (TKP). The system is designed as a solo-developer project with clear separation of concerns across 10 distinct stages.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           GYANTRA SYSTEM ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────────┐  │
│  │   STREAMLIT  │    │    FASTAPI   │    │      PIPELINE ORCHESTRATOR   │  │
│  │   FRONTEND   │◀──▶│    BACKEND   │◀──▶│                              │  │
│  │              │    │              │    │  ┌────────────────────────┐  │  │
│  │ • Upload UI  │    │ • REST API   │    │  │ 1. Document Intelligence│  │  │
│  │ • Progress   │    │ • SSE Stream │    │  │ 2. Classification       │  │  │
│  │ • Preview    │    │ • Job Mgmt   │    │  │ 3. Knowledge Extraction │  │  │
│  │ • Export     │    │ • File Store │    │  │ 4. Teaching Planner     │  │  │
│  └──────────────┘    └──────────────┘    │  │ 5. Content Generation   │  │  │
│         ▲                  ▲              │  │ 6. Activity Generation  │  │  │
│         │                  │              │  │ 7. Assessment Gen       │  │  │
│         │                  │              │  │ 8. Gap Analysis         │  │  │
│         │                  │              │  │ 9. Validation           │  │  │
│         │                  │              │  │ 10. Publishing          │  │  │
│         └──────────────────┘              │  └────────────────────────┘  │  │
│                    SSE                        ▲                ▲          │  │
│                                             │                │          │  │
│                              ┌────────────────┴────┐ ┌────────┴────┐     │  │
│                              │   LLM CLIENT        │ │  PARSERS    │     │  │
│                              │   (OpenRouter)      │ │             │     │  │
│                              │                     │ │ • PDF       │     │  │
│                              │ • Classification    │ │ • DOCX      │     │  │
│                              │ • Extraction        │ │ • PPTX      │     │  │
│                              │ • Planning          │ │ • OCR       │     │  │
│                              │ • Generation        │ │ • Router    │     │  │
│                              │ • Validation        │ └─────────────┘     │  │
│                              └─────────────────────┘                     │  │
│                                             ▲                             │  │
│                              ┌──────────────┴──────────────┐             │  │
│                              │      DATA LAYER             │             │  │
│                              │                             │             │  │
│                              │ • SQLite (jobs, packages)   │             │  │
│                              │ • File System (uploads,     │             │  │
│                              │   exports)                  │             │  │
│                              └─────────────────────────────┘             │  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Frontend (Streamlit)
- **File**: `frontend/streamlit_app.py`
- **Responsibilities**:
  - File upload with document type hint selection
  - Real-time progress display via SSE
  - Tabbed package preview (Overview, Knowledge, Plan, Content, Activities, Assessments, Gaps, Validation)
  - Export downloads (JSON, 3 PDF formats)
- **State Management**: Streamlit session state for job tracking

### 2. Backend API (FastAPI)
- **File**: `backend/app/main.py`
- **Endpoints**:
  - `POST /api/upload` — Accept file, create job, start background pipeline
  - `GET /api/jobs/{job_id}` — Job status and results
  - `GET /api/jobs/{job_id}/progress` — SSE progress stream
  - `GET /api/jobs/{job_id}/download/{format}` — Export downloads
  - `GET /api/health` — Health check
- **Background Processing**: FastAPI BackgroundTasks for non-blocking pipeline execution

### 3. Pipeline Orchestrator
- **File**: `backend/app/services/pipeline.py`
- **Function**: `run_pipeline(job_id, file_path, user_hint)`
- **Stages** (with progress ranges):
  1. Document Intelligence (0-10%)
  2. Educational Classification (10-15%)
  3. Knowledge Extraction (15-30%)
  4. Teaching Planner (30-40%)
  5. Classroom Content (40-55%)
  6. Activities (55-65%)
  7. Assessments (65-80%)
  8. Gap Analysis (80-85%)
  9. Validation (85-95%)
  10. Publishing (95-100%)
- **Error Handling**: Try/catch with job failure recording
- **Progress Updates**: `update_job_progress()` called after each stage

### 4. Document Parsers
- **Module**: `backend/parsers/`
- **Parsers**:
  - `pdf_parser.py` — PyMuPDF (fitz): text, headings, tables, figures, equations
  - `docx_parser.py` — python-docx: paragraphs, headings, tables, inline math
  - `ppt_parser.py` — python-pptx: slides, shapes, tables, images
  - `ocr_fallback.py` — Tesseract: scanned PDFs and images
- **Router** (`router.py`): Routes based on file extension + user hint + auto-detection

### 5. LLM Client
- **File**: `backend/app/services/llm_client.py`
- **Class**: `OpenRouterClient`
- **Features**:
  - Async HTTP client with timeout
  - Structured output via JSON Schema (`response_format`)
  - Retry logic for JSON parsing failures
  - Model selection per stage (configurable via settings)

### 6. Prompt Templates
- **File**: `backend/app/services/prompt_templates.py`
- **Approach**: Jinja2 templates for each stage
- **Stages with Prompts**:
  - Classification → `DocumentProfile`
  - Extraction → `KnowledgeExtractionResult`
  - Planning → `TeachingPlan`
  - Content Generation → `ClassroomContent` (per period)
  - Activity Generation → `List[Activity]`
  - Assessment Generation → `AssessmentPack`
  - Gap Analysis → `LearningGapAnalysis`
  - Validation → `ValidationRecord`

### 7. Validation Engine
- **File**: `backend/app/services/validation.py`
- **Checks**:
  1. Schema Validation — Pydantic model compliance
  2. Completeness — All required content present
  3. Consistency — Cross-stage reference integrity
  4. Pedagogical Quality — Bloom's distribution, activity diversity, assessment variety
  5. No Hallucination — Source grounding verification
- **Output**: `ValidationRecord` with scores and detailed checks

### 8. Exporter
- **File**: `backend/app/services/exporter.py`
- **Formats**:
  - JSON — Canonical `TeacherKnowledgePackage`
  - Lesson Plan PDF — Period overview + detailed plans (ReportLab)
  - Teacher Guide PDF — Concept reference + gap analysis
  - Assessment Pack PDF — Formative/summative + blueprint + answer key

### 9. Data Layer
- **Database**: SQLite with async SQLAlchemy (aiosqlite)
- **Models** (`database.py`):
  - `GenerationJob` — Job tracking with status, progress, results
- **File Storage**: Local filesystem (`uploads/`, `exports/`)

## Data Flow

```
1. UPLOAD
   User → Streamlit → FastAPI POST /api/upload
   → Save file → Create job record → BackgroundTask(run_pipeline)

2. PIPELINE EXECUTION (async background)
   For each stage:
     → Update job progress (stage, %, status)
     → Execute stage logic (parser or LLM call)
     → Store intermediate results in memory
   
   Final:
     → Run validation
     → Export all formats
     → Save complete package to job record
     → Mark job COMPLETED

3. PROGRESS STREAMING
   Frontend → GET /api/jobs/{id}/progress (SSE)
   → Server sends updates every 1s until completion

4. PREVIEW & EXPORT
   Frontend → GET /api/jobs/{id} → Render tabs
   Frontend → GET /api/jobs/{id}/download/{format} → Download file
```

## LLM Model Assignment

| Stage | Model | Rationale |
|-------|-------|-----------|
| Classification | Gemma-2-9B | Fast, good at structured categorization |
| Extraction | Llama-3.1-8B | Strong reasoning, knowledge extraction |
| Planning | Mistral-7B | Good at sequencing and planning |
| Content Gen | Llama-3.1-8B | Creative, pedagogical content |
| Activities | Llama-3.1-8B | Diverse activity design |
| Assessments | Llama-3.1-8B | Assessment construction |
| Gap Analysis | Llama-3.1-8B | Analytical, misconception knowledge |
| Validation | Mistral-7B | Critical analysis, consistency checking |

All models are free on OpenRouter.

## Error Handling & Resilience

1. **Parser Failures**: OCR fallback for PDFs, graceful degradation
2. **LLM Failures**: Retry with exponential backoff (max 2 retries)
3. **JSON Parsing**: Re-prompt with error feedback
4. **Job Failures**: Recorded in DB with error message, status=FAILED
5. **Timeouts**: Configurable per stage (default 120s per LLM call)

## Security Considerations

- No authentication in prototype (single-user academic)
- File size limits (50MB default)
- File type validation by extension
- No sensitive data in logs
- API keys via environment variables only

## Scalability Notes

Current prototype limitations:
- Single SQLite database (not for concurrent multi-user)
- Local file storage
- Sequential stage execution (could parallelize independent stages)
- In-memory intermediate results

Future improvements:
- PostgreSQL for production
- Redis for job queue + caching
- Celery for distributed task processing
- S3-compatible object storage
- Horizontal scaling with load balancer

## Monitoring & Observability

- SSE progress stream provides real-time visibility
- Structured logging (configure via `DEBUG` setting)
- Job status persisted in database
- Validation record captures quality metrics
- Processing time tracked in package metadata

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     DOCKER COMPOSE                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐          ┌─────────────┐                   │
│  │  FRONTEND   │─────────▶│  BACKEND    │                   │
│  │  (port 8501)│  HTTP    │  (port 8000)│                   │
│  └─────────────┘          └──────┬──────┘                   │
│                                  │                          │
│                    ┌──────────────┼──────────────┐          │
│                    │              │              │          │
│              ┌─────▼─────┐ ┌──────▼──────┐ ┌─────▼─────┐   │
│              │  VOLUMES  │ │  ENV VARS   │ │  HEALTH   │   │
│              │           │ │             │ │  CHECKS   │   │
│              │ uploads/  │ │ OPENROUTER  │ │           │   │
│              │ exports/  │ │ _API_KEY    │ │ /api/     │   │
│              │ data/     │ │             │ │ health    │   │
│              └───────────┘ └─────────────┘ └───────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Configuration Reference

See `.env.example` for all configurable options. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | (required) | API key for LLM access |
| `MODEL_*` | Free models | Per-stage model selection |
| `LLM_TEMPERATURE` | 0.3 | Generation creativity |
| `MAX_FILE_SIZE_MB` | 50 | Upload limit |
| `OCR_ENABLED` | true | Enable Tesseract fallback |
| `JOB_TIMEOUT_SECONDS` | 600 | Max pipeline runtime |

## Testing Strategy

| Level | Tool | Coverage |
|-------|------|----------|
| Unit | pytest | Parsers, schemas, validation logic |
| Integration | pytest | Pipeline with mocked LLM |
| E2E | Manual | NCERT samples (STEM + Humanities) |

Run tests: `cd backend && pytest tests/ -v`

---

*Document Version: 1.0 | Architecture for Gyantra v1.0*