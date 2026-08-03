"""
REST + SSE API.

Endpoints:
  POST   /api/upload                          create a job and start the pipeline
  GET    /api/jobs                            recent jobs (library view)
  GET    /api/jobs/{id}                       job status + full package
  GET    /api/jobs/{id}/progress              SSE progress stream
  GET    /api/jobs/{id}/package               just the TKP JSON
  GET    /api/jobs/{id}/download/{format}     export download
  DELETE /api/jobs/{id}                       remove a job and its artifacts
  GET    /api/health                          health + provider readiness
  GET    /api/config/options                  form options for the upload UI
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.config import settings
from app.models.enums import (
    STAGE_LABELS,
    DocumentHint,
    JobStatus,
    StageName,
)
from app.parsers.router import SUPPORTED_EXTENSIONS, UnsupportedFileError
from app.services.job_store import job_store
from app.services.llm_client import LLMClient
from app.services.pipeline import run_pipeline
from app.services.progress import ProgressReporter

logger = logging.getLogger("gyantra.api")
router = APIRouter()

DOWNLOAD_FORMATS = {
    "json": ("json_path", "application/json", "TeacherKnowledgePackage.json"),
    "lesson-plan": ("lesson_plan_pdf_path", "application/pdf", "LessonPlan.pdf"),
    "teacher-guide": ("teacher_guide_pdf_path", "application/pdf", "TeacherGuide.pdf"),
    "assessments": ("assessment_pack_pdf_path", "application/pdf", "AssessmentPack.pdf"),
}


# ── health & config ──────────────────────────────────────────────────────────


@router.get("/health")
async def health(probe: bool = False) -> dict:
    """Health check.

    Pass ?probe=true to actually call each provider — useful for confirming a
    key works, but it costs a real (tiny) request per provider.
    """
    client = LLMClient()
    providers = client.available_providers()

    payload = {
        "status": "ok",
        "app": settings.app_name,
        "llm_providers_configured": providers,
        "llm_ready": bool(providers) or settings.demo_mode,
        "demo_mode": settings.demo_mode,
        "model_routing": client.describe_routing(),
        "ocr_enabled": settings.ocr_enabled,
        "parser": "docling" if settings.docling_enabled else "builtin",
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "max_file_size_mb": settings.max_file_size_mb,
    }

    if probe and not settings.demo_mode:
        from app.services.llm_client import probe_providers

        payload["provider_probe"] = await probe_providers()

    return payload


@router.get("/config/options")
async def config_options() -> dict:
    """Options the upload form needs, so the frontend has no hardcoded lists."""
    return {
        "document_hints": [
            {"value": DocumentHint.MOSTLY_TEXT.value, "label": "Mostly text",
             "description": "Plain prose chapters — cheapest, fastest parse"},
            {"value": DocumentHint.TEXT_WITH_TABLES.value, "label": "Text with tables",
             "description": "Preserves tabular structure"},
            {"value": DocumentHint.TEXT_WITH_DIAGRAMS.value, "label": "Text with diagrams",
             "description": "Keeps figure references and captions"},
            {"value": DocumentHint.TEXT_WITH_EQUATIONS.value, "label": "Text with equations",
             "description": "Preserves formulas alongside their concepts"},
            {"value": DocumentHint.SCANNED_PDF.value, "label": "Scanned PDF",
             "description": "Runs OCR — slower but handles image-only pages"},
            {"value": DocumentHint.NOT_SURE.value, "label": "Let the system decide",
             "description": "Gyantra inspects the file and picks a strategy"},
        ],
        "stages": [
            {"value": s.value, "label": STAGE_LABELS[s], "order": i + 1}
            for i, s in enumerate(StageName)
        ],
        "assessment_depths": [
            {"value": "light", "label": "Light"},
            {"value": "balanced", "label": "Balanced"},
            {"value": "thorough", "label": "Thorough"},
        ],
        "teaching_styles": [
            {"value": "conceptual", "label": "Conceptual understanding"},
            {"value": "exam_oriented", "label": "Exam oriented"},
            {"value": "activity_based", "label": "Activity based"},
            {"value": "balanced", "label": "Balanced"},
        ],
        "max_file_size_mb": settings.max_file_size_mb,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
    }


# ── upload ───────────────────────────────────────────────────────────────────


@router.post("/upload", status_code=202)
async def upload(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    document_hint: str = Form(DocumentHint.NOT_SURE.value),
    subject: str = Form(""),
    grade: str = Form(""),
    language: str = Form(""),
    board: str = Form(""),
    teaching_style: str = Form(""),
    period_minutes: str = Form(""),
    total_periods_available: str = Form(""),
    assessment_depth: str = Form("balanced"),
    time_constraints: str = Form(""),
) -> dict:
    """Accept a document, create a job, and start the pipeline in the background."""
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    try:
        hint = DocumentHint(document_hint)
    except ValueError:
        hint = DocumentHint.NOT_SURE

    job_id = uuid.uuid4().hex[:12]
    job_dir = Path(settings.upload_dir) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    dest = job_dir / f"source{ext}"

    # Stream to disk with a running size check so a huge upload can't fill the volume.
    size = 0
    limit = settings.max_file_size_bytes
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    out.close()
                    shutil.rmtree(job_dir, ignore_errors=True)
                    raise HTTPException(
                        413,
                        f"File exceeds the {settings.max_file_size_mb} MB limit",
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except OSError as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(500, f"Could not save upload: {exc}") from exc

    if size == 0:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(400, "Uploaded file is empty")

    # Only keep answers the teacher actually gave.
    user_context = {
        k: v
        for k, v in {
            "subject": subject.strip(),
            "grade": grade.strip(),
            "language": language.strip(),
            "board": board.strip(),
            "teaching_style": teaching_style.strip(),
            "period_minutes": _to_int(period_minutes),
            "total_periods_available": _to_int(total_periods_available),
            "assessment_depth": assessment_depth.strip() or "balanced",
            "time_constraints": time_constraints.strip(),
        }.items()
        if v not in ("", None)
    }

    await job_store.create(
        job_id=job_id,
        file_name=file.filename,
        file_type=ext.lstrip("."),
        file_size_bytes=size,
        document_hint=hint,
        user_context=user_context,
    )

    background.add_task(
        _run_job, job_id, str(dest), file.filename, hint, user_context
    )

    logger.info("job %s queued for %s (%s bytes)", job_id, file.filename, size)
    return {
        "job_id": job_id,
        "status": JobStatus.QUEUED.value,
        "file_name": file.filename,
        "file_size_bytes": size,
        "document_hint": hint.value,
        "progress_url": f"{settings.api_prefix}/jobs/{job_id}/progress",
    }


def _to_int(value: str) -> int | None:
    try:
        n = int(str(value).strip())
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


async def _run_job(
    job_id: str,
    file_path: str,
    original_name: str,
    hint: DocumentHint,
    user_context: dict,
) -> None:
    """Background entry point. Exceptions are already recorded by the pipeline."""
    reporter = ProgressReporter(job_id, job_store)
    try:
        await asyncio.wait_for(
            run_pipeline(job_id, file_path, original_name, hint, user_context, reporter),
            timeout=settings.job_timeout_seconds,
        )
    except asyncio.TimeoutError:
        msg = f"Job exceeded the {settings.job_timeout_seconds}s time limit"
        logger.error("job %s timed out", job_id)
        await job_store.update(job_id, status=JobStatus.FAILED, error_message=msg)
        await job_store.publish(job_id, {"type": "job_failed", "error": msg})
    except Exception as exc:  # noqa: BLE001 — background tasks must never raise
        logger.exception("job %s crashed", job_id)
        await job_store.update(job_id, status=JobStatus.FAILED, error_message=str(exc))


# ── job queries ──────────────────────────────────────────────────────────────


@router.get("/jobs")
async def list_jobs(limit: int = 25) -> dict:
    jobs = await job_store.list_recent(min(max(limit, 1), 100))
    return {
        "jobs": [
            {
                "job_id": j.id,
                "file_name": j.file_name,
                "file_type": j.file_type,
                "status": j.status.value,
                "progress": round(j.progress_pct),
                "created_at": j.created_at,
                "updated_at": j.updated_at,
                "error_message": j.error_message,
            }
            for j in jobs
        ]
    }


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")

    payload = {
        "job_id": job.id,
        "file_name": job.file_name,
        "file_type": job.file_type,
        "file_size_bytes": job.file_size_bytes,
        "document_hint": job.document_hint.value,
        "user_context": job.user_context,
        "status": job.status.value,
        "progress": round(job.progress_pct),
        "current_stage": job.current_stage.value if job.current_stage else None,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "stages": [s.model_dump(mode="json") for s in job.stages],
        "package": None,
        "summary": None,
        "available_downloads": [],
    }

    if job.result:
        payload["package"] = job.result.model_dump(mode="json")
        payload["summary"] = job.result.summary()
        payload["available_downloads"] = [
            fmt
            for fmt, (attr, _, _) in DOWNLOAD_FORMATS.items()
            if getattr(job.result.exports, attr, "")
        ]

    return payload


@router.get("/jobs/{job_id}/package")
async def get_package(job_id: str) -> dict:
    """Just the TKP — useful for programmatic consumers."""
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    if not job.result:
        raise HTTPException(
            409, f"Job {job_id} has no package yet (status: {job.status.value})"
        )
    return job.result.model_dump(mode="json")


# ── SSE progress ─────────────────────────────────────────────────────────────


@router.get("/jobs/{job_id}/progress")
async def stream_progress(job_id: str) -> StreamingResponse:
    """Server-Sent Events stream of pipeline progress.

    Sends an immediate snapshot so a client that connects late (or reconnects)
    is never left with an empty screen, then streams live events.
    """
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")

    async def event_source():
        queue = job_store.subscribe(job_id)
        try:
            snapshot = {
                "type": "snapshot",
                "job_id": job_id,
                "status": job.status.value,
                "progress": round(job.progress_pct),
                "current_stage": job.current_stage.value if job.current_stage else None,
                "stages": [s.model_dump(mode="json") for s in job.stages],
                "error": job.error_message,
            }
            yield f"data: {json.dumps(snapshot)}\n\n"

            # A job that already finished needs no live stream.
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"
                return

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # Keep-alive comment so proxies don't drop the connection.
                    yield ": keep-alive\n\n"
                    current = await job_store.get(job_id)
                    if current and current.status in (
                        JobStatus.COMPLETED,
                        JobStatus.FAILED,
                    ):
                        yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"
                        return
                    continue

                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("job_completed", "job_failed"):
                    yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"
                    return
        finally:
            job_store.unsubscribe(job_id, queue)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


# ── downloads ────────────────────────────────────────────────────────────────


@router.get("/jobs/{job_id}/download/{fmt}")
async def download(job_id: str, fmt: str) -> FileResponse:
    if fmt not in DOWNLOAD_FORMATS:
        raise HTTPException(
            400, f"Unknown format '{fmt}'. Available: {', '.join(DOWNLOAD_FORMATS)}"
        )

    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    if not job.result:
        raise HTTPException(409, "This job has no exports yet")

    attr, media_type, default_name = DOWNLOAD_FORMATS[fmt]
    path_str = getattr(job.result.exports, attr, "")
    if not path_str:
        raise HTTPException(404, f"The '{fmt}' export was not generated for this job")

    path = Path(path_str)
    if not path.exists():
        raise HTTPException(410, f"Export file is no longer on disk: {path.name}")

    # Prefix with the source name so a teacher's downloads folder stays readable.
    stem = Path(job.file_name).stem[:40].replace(" ", "_") or "gyantra"
    filename = f"{stem}_{default_name}"

    return FileResponse(path=path, media_type=media_type, filename=filename)


# ── delete ───────────────────────────────────────────────────────────────────


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str) -> dict:
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")

    deleted = await job_store.delete(job_id)
    for base in (settings.upload_dir, settings.export_dir):
        shutil.rmtree(Path(base) / job_id, ignore_errors=True)

    return {"deleted": deleted, "job_id": job_id}
