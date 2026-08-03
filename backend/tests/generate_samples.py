"""
Generate the two sample TKP packages required by the assignment.

Usage:
    cd backend
    python -m tests.generate_samples

Produces samples/force_and_laws_of_motion.json and
samples/nationalism_in_india.json, both with all 10 pipeline stages populated.
Runs the full pipeline in DEMO_MODE (no API key needed).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.models.enums import DocumentHint  # noqa: E402
from app.services.pipeline import run_pipeline  # noqa: E402
from app.services.progress import ProgressReporter  # noqa: E402


class QuietStore:
    async def publish(self, job_id, event):
        pass

    async def update(self, job_id, **fields):
        pass

    async def set_stage_status(self, job_id, stage, status, message="", started=False, finished=False):
        pass


JOBS = [
    (
        "force_and_laws_of_motion",
        ROOT / "samples" / "source_documents" / "force_and_laws_of_motion.md",
        DocumentHint.MOSTLY_TEXT,
        {"subject": "Physics", "grade": "Class 9", "period_minutes": 40},
    ),
    (
        "nationalism_in_india",
        ROOT / "samples" / "source_documents" / "nationalism_in_india.md",
        DocumentHint.MOSTLY_TEXT,
        {"subject": "History", "grade": "Class 10", "period_minutes": 40},
    ),
]


async def main() -> None:
    settings.demo_mode = True
    settings.llm_cache_enabled = False
    settings.export_dir = ROOT / "samples" / "exports"
    settings.ensure_dirs()

    for name, source, hint, ctx in JOBS:
        print(f"[generating] {name}")
        reporter = ProgressReporter(f"sample-{name}", QuietStore())
        package = await run_pipeline(
            job_id=f"sample-{name}",
            file_path=str(source),
            original_name=f"{name}.md",
            document_hint=hint,
            user_context=ctx,
            reporter=reporter,
        )

        out = ROOT / "samples" / f"{name}_TeacherKnowledgePackage.json"
        out.write_text(
            json.dumps(package.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        summary = package.summary()
        print(
            f"  ok: {summary['subject']} | {summary['grade']} | "
            f"{summary['periods']} periods | {summary['concepts']} concepts | "
            f"validation={summary['validation']} -> {out.name}"
        )

    print("done")


if __name__ == "__main__":
    asyncio.run(main())
