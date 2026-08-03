"""
Progress reporting — the backbone of the streaming progress API.

Each job gets a ProgressReporter that writes stage transitions into the job
store and pushes events onto an asyncio queue.  The SSE endpoint drains that
queue, so the frontend receives updates the moment they happen rather than by
polling.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.models.enums import STAGE_LABELS, STAGE_PROGRESS, JobStatus, StageName
from app.models.schemas import StageProgress, TeacherKnowledgePackage

logger = logging.getLogger("gyantra.progress")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProgressReporter:
    """Emits progress events for one job.

    The event shape matches what the assignment asks for:
        {"stage": "classroom_content", "progress": 60, ...}
    """

    def __init__(self, job_id: str, store: "JobStore"):
        self.job_id = job_id
        self.store = store
        self.current_stage: StageName | None = None

    async def _emit(self, event: dict[str, Any]) -> None:
        event.setdefault("job_id", self.job_id)
        event.setdefault("timestamp", _now())
        await self.store.publish(self.job_id, event)

    # ── job lifecycle ────────────────────────────────────────────────────

    async def job_started(self) -> None:
        await self.store.update(
            self.job_id, status=JobStatus.RUNNING, progress_pct=0.0
        )
        await self._emit({"type": "job_started", "progress": 0})

    async def job_completed(
        self,
        package: TeacherKnowledgePackage,
        degraded: list[str] | None = None,
    ) -> None:
        """Mark the job finished.

        `degraded` lists stages that ran but produced nothing. The job is still
        completed — there is a usable partial package — but the shortfall is
        recorded so the UI can say which sections are missing rather than
        presenting empty tabs as a success.
        """
        warning = ""
        if degraded:
            warning = (
                f"{len(degraded)} stage(s) produced no output: {', '.join(degraded)}. "
                "This usually means the AI provider was rate-limited or unavailable. "
                "Re-running the document may fill in the missing sections."
            )

        await self.store.update(
            self.job_id,
            status=JobStatus.COMPLETED,
            progress_pct=100.0,
            result=package,
            current_stage=None,
            error_message=warning,
        )
        await self._emit(
            {
                "type": "job_completed",
                "progress": 100,
                "summary": package.summary(),
                "degraded_stages": degraded or [],
                "warning": warning,
            }
        )

    async def job_failed(self, message: str, stage: StageName) -> None:
        await self.store.update(
            self.job_id, status=JobStatus.FAILED, error_message=message
        )
        await self.store.set_stage_status(
            self.job_id, stage, JobStatus.FAILED, message
        )
        await self._emit(
            {
                "type": "job_failed",
                "stage": stage.value,
                "error": message,
            }
        )

    # ── stage lifecycle ──────────────────────────────────────────────────

    async def stage_started(
        self, stage: StageName, label: str, progress: int, message: str = ""
    ) -> None:
        self.current_stage = stage
        await self.store.update(
            self.job_id, current_stage=stage, progress_pct=float(progress)
        )
        await self.store.set_stage_status(
            self.job_id, stage, JobStatus.RUNNING, message, started=True
        )
        await self._emit(
            {
                "type": "stage_started",
                "stage": stage.value,
                "label": label,
                "progress": progress,
                "message": message,
            }
        )
        logger.info("[%s] %s started — %s", self.job_id[:8], label, message)

    async def stage_progress(
        self, stage: StageName, label: str, progress: int, message: str = ""
    ) -> None:
        await self.store.update(self.job_id, progress_pct=float(progress))
        await self._emit(
            {
                "type": "stage_progress",
                "stage": stage.value,
                "label": label,
                "progress": progress,
                "message": message,
            }
        )

    async def stage_completed(
        self, stage: StageName, label: str, progress: int, message: str = ""
    ) -> None:
        await self.store.update(self.job_id, progress_pct=float(progress))
        await self.store.set_stage_status(
            self.job_id, stage, JobStatus.COMPLETED, message, finished=True
        )
        await self._emit(
            {
                "type": "stage_completed",
                "stage": stage.value,
                "label": label,
                "progress": progress,
                "message": message,
            }
        )
        logger.info("[%s] %s done — %s", self.job_id[:8], label, message)

    async def stage_failed(
        self,
        stage: StageName,
        label: str,
        error: str,
        fatal: bool = True,
        progress: int | None = None,
    ) -> None:
        await self.store.set_stage_status(
            self.job_id, stage, JobStatus.FAILED, error, finished=True
        )
        await self._emit(
            {
                "type": "stage_failed",
                "stage": stage.value,
                "label": label,
                "error": error,
                "fatal": fatal,
                "progress": progress,
            }
        )
        logger.warning("[%s] %s failed (fatal=%s): %s", self.job_id[:8], label, fatal, error)
