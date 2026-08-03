"""API-level tests using FastAPI's TestClient."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path: Path):
    """A TestClient with storage redirected to tmp_path and demo mode on."""
    from app.config import settings

    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(settings, "export_dir", tmp_path / "exports")
    monkeypatch.setattr(settings, "cache_dir", tmp_path / "cache")
    monkeypatch.setattr(settings, "llm_cache_enabled", False)
    settings.ensure_dirs()

    from app.services.job_store import job_store

    monkeypatch.setattr(job_store, "db_path", str(tmp_path / "test.db"))

    from app.main import app

    with TestClient(app) as c:
        yield c


class TestHealth:
    def test_health_reports_status(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "supported_extensions" in body
        assert ".pdf" in body["supported_extensions"]

    def test_root_endpoint(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert r.json()["name"] == "Gyantra"

    def test_config_options_drive_the_upload_form(self, client):
        r = client.get("/api/config/options")
        assert r.status_code == 200
        body = r.json()

        # The frontend renders the hint selector straight from this payload.
        hints = {h["value"] for h in body["document_hints"]}
        assert "mostly_text" in hints
        assert "scanned_pdf" in hints
        assert "not_sure" in hints

        # All 10 stages, in order, for the pipeline stepper.
        assert len(body["stages"]) == 10
        assert body["stages"][0]["value"] == "document_intelligence"
        assert body["stages"][-1]["value"] == "publishing"
        assert [s["order"] for s in body["stages"]] == list(range(1, 11))


class TestUploadValidation:
    def test_rejects_unsupported_extension(self, client):
        r = client.post(
            "/api/upload",
            files={"file": ("photo.png", io.BytesIO(b"\x89PNG"), "image/png")},
        )
        assert r.status_code == 400
        assert "Unsupported file type" in r.json()["detail"]

    def test_rejects_empty_file(self, client):
        r = client.post(
            "/api/upload",
            files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
        )
        assert r.status_code == 400
        assert "empty" in r.json()["detail"].lower()

    def test_rejects_oversized_file(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "max_file_size_mb", 1)
        big = b"x" * (2 * 1024 * 1024)
        r = client.post(
            "/api/upload",
            files={"file": ("big.txt", io.BytesIO(big), "text/plain")},
        )
        assert r.status_code == 413
        assert "limit" in r.json()["detail"].lower()

    def test_unknown_job_returns_404(self, client):
        assert client.get("/api/jobs/doesnotexist").status_code == 404

    def test_unknown_download_format_rejected(self, client):
        r = client.get("/api/jobs/anything/download/exe")
        assert r.status_code == 400
        assert "Unknown format" in r.json()["detail"]


class TestFullUploadFlow:
    """Upload a document and walk the whole job lifecycle through the API."""

    def _upload(self, client, text: str, name: str = "chapter.md") -> str:
        r = client.post(
            "/api/upload",
            files={"file": (name, io.BytesIO(text.encode()), "text/markdown")},
            data={
                "document_hint": "mostly_text",
                "grade": "Class 9",
                "assessment_depth": "balanced",
                "period_minutes": "40",
            },
        )
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["status"] == "queued"
        assert body["progress_url"].endswith("/progress")
        return body["job_id"]

    def test_upload_creates_and_completes_job(self, client, sample_chapter_text):
        job_id = self._upload(client, sample_chapter_text)

        # TestClient runs BackgroundTasks synchronously before returning, so by
        # the time we query, the pipeline has finished.
        r = client.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200
        job = r.json()

        assert job["status"] == "completed", job.get("error_message")
        assert job["progress"] == 100
        assert len(job["stages"]) == 10
        assert all(s["status"] == "completed" for s in job["stages"])

        summary = job["summary"]
        assert summary["subject"] == "Physics"
        assert summary["periods"] >= 1
        assert summary["concepts"] >= 3
        assert summary["mcqs"] > 0

        pkg = job["package"]
        assert pkg["teaching_plan"]["total_periods"] == summary["periods"]
        assert len(pkg["classroom_content"]) == summary["periods"]
        assert pkg["metadata"]["demo_mode"] is True

    def test_package_endpoint_returns_tkp(self, client, sample_chapter_text):
        job_id = self._upload(client, sample_chapter_text)
        r = client.get(f"/api/jobs/{job_id}/package")
        assert r.status_code == 200

        pkg = r.json()
        # The documented top-level contract.
        for key in (
            "metadata",
            "document_profile",
            "knowledge_extraction",
            "teaching_plan",
            "classroom_content",
            "activities",
            "assessments",
            "gap_analysis",
            "validation",
            "exports",
        ):
            assert key in pkg, f"missing top-level key: {key}"

    def test_all_downloads_work(self, client, sample_chapter_text):
        job_id = self._upload(client, sample_chapter_text)

        available = client.get(f"/api/jobs/{job_id}").json()["available_downloads"]
        assert set(available) == {"json", "lesson-plan", "teacher-guide", "assessments"}

        r = client.get(f"/api/jobs/{job_id}/download/json")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")
        assert json.loads(r.content)["metadata"]["job_id"] == job_id

        for fmt in ("lesson-plan", "teacher-guide", "assessments"):
            r = client.get(f"/api/jobs/{job_id}/download/{fmt}")
            assert r.status_code == 200, fmt
            assert r.headers["content-type"] == "application/pdf"
            assert r.content.startswith(b"%PDF"), f"{fmt} is not a valid PDF"
            assert len(r.content) > 1500

    def test_progress_stream_replays_snapshot(self, client, sample_chapter_text):
        """A client connecting after completion still gets full state."""
        job_id = self._upload(client, sample_chapter_text)

        with client.stream("GET", f"/api/jobs/{job_id}/progress") as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            events = []
            for line in r.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
                if events and events[-1].get("type") == "stream_end":
                    break

        assert events[0]["type"] == "snapshot"
        assert events[0]["status"] == "completed"
        assert events[0]["progress"] == 100
        assert len(events[0]["stages"]) == 10

    def test_job_appears_in_library_list(self, client, sample_chapter_text):
        job_id = self._upload(client, sample_chapter_text, name="force.md")

        jobs = client.get("/api/jobs").json()["jobs"]
        entry = next((j for j in jobs if j["job_id"] == job_id), None)
        assert entry is not None
        assert entry["file_name"] == "force.md"
        assert entry["status"] == "completed"

    def test_delete_removes_job_and_artifacts(self, client, sample_chapter_text):
        from app.config import settings

        job_id = self._upload(client, sample_chapter_text)
        export_dir = Path(settings.export_dir) / job_id
        assert export_dir.exists()

        r = client.delete(f"/api/jobs/{job_id}")
        assert r.status_code == 200
        assert r.json()["deleted"] is True

        assert client.get(f"/api/jobs/{job_id}").status_code == 404
        assert not export_dir.exists()

    def test_failed_job_reports_error(self, client):
        """A document with no extractable text should fail with a clear message."""
        job_id = self._upload(client, "   \n\n   \n", name="blank.txt")

        job = client.get(f"/api/jobs/{job_id}").json()
        assert job["status"] == "failed"
        assert "no readable text" in job["error_message"].lower()

        # Downloads must not 500 on a failed job.
        assert client.get(f"/api/jobs/{job_id}/download/json").status_code == 409
