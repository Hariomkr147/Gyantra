"""
Job store — SQLite persistence plus in-memory pub/sub for SSE.

Jobs survive a restart (SQLite), while live progress events flow through
per-job asyncio queues.  A late-connecting SSE client still gets the full
picture because the job row carries the current stage list.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from app.config import settings
from app.models.enums import STAGE_LABELS, DocumentHint, JobStatus, StageName
from app.models.schemas import (
    JobRecord,
    StageProgress,
    TeacherKnowledgePackage,
)

logger = logging.getLogger("gyantra.store")

_DB_PATH = settings.database_url.split("///")[-1] if "///" in settings.database_url else "./data/gyantra.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,
    file_name       TEXT NOT NULL DEFAULT '',
    file_type       TEXT NOT NULL DEFAULT '',
    file_size_bytes INTEGER NOT NULL DEFAULT 0,
    document_hint   TEXT NOT NULL DEFAULT 'not_sure',
    user_context    TEXT NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'queued',
    stages          TEXT NOT NULL DEFAULT '[]',
    current_stage   TEXT,
    progress_pct    REAL NOT NULL DEFAULT 0,
    error_message   TEXT NOT NULL DEFAULT '',
    result          TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status  ON jobs(status);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _initial_stages() -> list[dict]:
    return [
        StageProgress(
            stage=s, label=STAGE_LABELS[s], status=JobStatus.QUEUED
        ).model_dump(mode="json")
        for s in StageName
    ]


class JobStore:
    """Async job persistence + event fan-out."""

    def __init__(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        # job_id -> list of subscriber queues
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        from pathlib import Path

        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()
        logger.info("job store ready at %s", self.db_path)

    # ── CRUD ─────────────────────────────────────────────────────────────

    async def create(
        self,
        job_id: str,
        file_name: str,
        file_type: str,
        file_size_bytes: int,
        document_hint: DocumentHint,
        user_context: dict,
    ) -> JobRecord:
        now = _now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO jobs
                   (id, file_name, file_type, file_size_bytes, document_hint,
                    user_context, status, stages, progress_pct, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_id,
                    file_name,
                    file_type,
                    file_size_bytes,
                    document_hint.value,
                    json.dumps(user_context),
                    JobStatus.QUEUED.value,
                    json.dumps(_initial_stages()),
                    0.0,
                    now,
                    now,
                ),
            )
            await db.commit()
        return await self.get(job_id)

    async def get(self, job_id: str) -> JobRecord | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = await cur.fetchone()
        return self._row_to_record(row) if row else None

    async def list_recent(self, limit: int = 25) -> list[JobRecord]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            rows = await cur.fetchall()
        # Library view doesn't need the full package; strip it for payload size.
        records = []
        for row in rows:
            rec = self._row_to_record(row, include_result=False)
            if rec:
                records.append(rec)
        return records

    async def update(self, job_id: str, **fields: Any) -> None:
        if not fields:
            return

        sets: list[str] = []
        values: list[Any] = []

        for key, value in fields.items():
            if key == "result" and value is not None:
                value = json.dumps(
                    value.model_dump(mode="json")
                    if hasattr(value, "model_dump")
                    else value,
                    ensure_ascii=False,
                )
            elif key in ("status", "current_stage") and value is not None:
                value = value.value if hasattr(value, "value") else value
            elif key == "user_context" and isinstance(value, dict):
                value = json.dumps(value)
            sets.append(f"{key} = ?")
            values.append(value)

        sets.append("updated_at = ?")
        values.append(_now())
        values.append(job_id)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", values)
            await db.commit()

    async def set_stage_status(
        self,
        job_id: str,
        stage: StageName,
        status: JobStatus,
        message: str = "",
        started: bool = False,
        finished: bool = False,
    ) -> None:
        """Update one entry in the job's stage list."""
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute("SELECT stages FROM jobs WHERE id = ?", (job_id,))
                row = await cur.fetchone()
                if not row:
                    return

                stages = json.loads(row["stages"])
                for entry in stages:
                    if entry.get("stage") == stage.value:
                        entry["status"] = status.value
                        entry["message"] = message
                        if started:
                            entry["started_at"] = _now()
                        if finished:
                            entry["finished_at"] = _now()
                        break

                await db.execute(
                    "UPDATE jobs SET stages = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(stages), _now(), job_id),
                )
                await db.commit()

    def _row_to_record(self, row, include_result: bool = True) -> JobRecord | None:
        if row is None:
            return None

        result = None
        if include_result and row["result"]:
            try:
                result = TeacherKnowledgePackage.model_validate(json.loads(row["result"]))
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("could not deserialize result for %s: %s", row["id"], exc)

        try:
            stages = [StageProgress.model_validate(s) for s in json.loads(row["stages"])]
        except (json.JSONDecodeError, ValueError):
            stages = []

        try:
            user_context = json.loads(row["user_context"])
        except json.JSONDecodeError:
            user_context = {}

        return JobRecord(
            id=row["id"],
            file_name=row["file_name"],
            file_type=row["file_type"],
            file_size_bytes=row["file_size_bytes"],
            document_hint=DocumentHint(row["document_hint"]),
            user_context=user_context,
            status=JobStatus(row["status"]),
            stages=stages,
            current_stage=StageName(row["current_stage"]) if row["current_stage"] else None,
            progress_pct=row["progress_pct"],
            error_message=row["error_message"],
            result=result,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def delete(self, job_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            await db.commit()
            return cur.rowcount > 0

    # ── pub/sub for SSE ──────────────────────────────────────────────────

    def subscribe(self, job_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.setdefault(job_id, []).append(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(job_id)
        if not subs:
            return
        if queue in subs:
            subs.remove(queue)
        if not subs:
            self._subscribers.pop(job_id, None)

    async def publish(self, job_id: str, event: dict) -> None:
        """Fan an event out to every subscriber of this job."""
        for queue in list(self._subscribers.get(job_id, [])):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # A stalled client must not block the pipeline.
                logger.debug("dropping event for slow subscriber on %s", job_id)


# Single shared instance for the app.
job_store = JobStore()
