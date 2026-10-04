from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.models.schemas import ClassifyRequest, JobStatus
from app.services import analysis_service
from app.services.job_service import Job, JobService


def test_job_creation_status_completion_and_failure_keep_api_shape():
    async def scenario():
        service = JobService()
        completed = await service.create_job("analyze")
        failed = await service.create_job("classify")
        await service.update_job(
            completed.job_id,
            status=JobStatus.COMPLETED,
            progress=100,
            result={"ok": True},
        )
        await service.update_job(
            failed.job_id,
            status=JobStatus.FAILED,
            message="Analysis failed",
            error="expected test failure",
        )

        completed_data = (await service.get_job(completed.job_id)).to_dict()
        failed_data = (await service.get_job(failed.job_id)).to_dict()
        assert completed_data["status"] == JobStatus.COMPLETED
        assert completed_data["result"] == {"ok": True}
        assert failed_data["status"] == JobStatus.FAILED
        assert failed_data["error"] == "expected test failure"
        assert set(completed_data) == {
            "job_id", "job_type", "status", "progress", "message", "result",
            "error", "created_at", "updated_at",
        }

    asyncio.run(scenario())


def test_expiration_removes_terminal_jobs_but_keeps_running_jobs():
    async def scenario():
        service = JobService(retention_seconds=60)
        completed = await service.create_job("analyze")
        running = await service.create_job("classify")
        await service.update_job(completed.job_id, status=JobStatus.COMPLETED)
        await service.update_job(running.job_id, status=JobStatus.RUNNING)
        completed.updated_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        running.updated_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        assert await service.get_job(completed.job_id) is None
        assert service.was_expired(completed.job_id)
        assert "expired from the in-memory demo retention window" in service.missing_job_detail(
            completed.job_id, "Analysis"
        )
        assert (await service.get_job(running.job_id)).status == JobStatus.RUNNING

    asyncio.run(scenario())


def test_terminal_job_cap_prunes_oldest_without_removing_active_job():
    async def scenario():
        service = JobService(retention_seconds=3600, max_terminal_jobs=1)
        oldest = await service.create_job("analyze")
        active = await service.create_job("classify")
        newest = await service.create_job("train")
        await service.update_job(oldest.job_id, status=JobStatus.COMPLETED)
        oldest.updated_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        await service.update_job(active.job_id, status=JobStatus.RUNNING)
        await service.update_job(newest.job_id, status=JobStatus.COMPLETED)

        assert await service.get_job(oldest.job_id) is None
        assert (await service.get_job(active.job_id)).status == JobStatus.RUNNING
        assert (await service.get_job(newest.job_id)).status == JobStatus.COMPLETED

    asyncio.run(scenario())


def test_pending_job_pins_its_dependency_contexts():
    async def scenario():
        service = JobService()
        job = await service.create_job("classify", depends_on=["analysis-id", "model-id"])
        assert service.protected_context_ids() == {job.job_id, "analysis-id", "model-id"}
        await service.update_job(job.job_id, status=JobStatus.COMPLETED)
        assert service.protected_context_ids() == set()

    asyncio.run(scenario())


def test_result_cache_cap_keeps_active_and_new_contexts_then_prunes_oldest(monkeypatch):
    monkeypatch.setattr(analysis_service, "_result_cache", {})
    monkeypatch.setattr(analysis_service, "_result_cache_created", {})
    monkeypatch.setattr(analysis_service, "MAX_RESULT_CACHE_ENTRIES", 1)
    monkeypatch.setattr(analysis_service.job_service, "protected_context_ids", lambda: {"pinned"})

    analysis_service.store_result("pinned", {"value": "active dependency"})
    analysis_service.store_result("new", {"value": "new result"})
    assert analysis_service.get_result("pinned") is not None
    assert analysis_service.get_result("new") is not None

    monkeypatch.setattr(analysis_service.job_service, "protected_context_ids", lambda: set())
    analysis_service._cleanup_result_cache()
    assert analysis_service.get_result("pinned") is None
    assert analysis_service.get_result("new") == {"value": "new result"}


def test_result_cache_expiration_preserves_active_context(monkeypatch):
    monkeypatch.setattr(analysis_service, "_result_cache", {"active": {"value": 1}, "old": {"value": 2}})
    monkeypatch.setattr(analysis_service, "_result_cache_created", {"active": 0.0, "old": 0.0})
    monkeypatch.setattr(analysis_service, "RESULT_RETENTION_SECONDS", 10)
    monkeypatch.setattr(analysis_service.job_service, "protected_context_ids", lambda: {"active"})

    analysis_service._cleanup_result_cache(now=20.0)

    assert analysis_service.get_result("active") == {"value": 1}
    assert analysis_service.get_result("old") is None


def test_missing_classification_context_records_a_clear_job_failure(monkeypatch):
    updates = AsyncMock()
    monkeypatch.setattr(analysis_service, "get_result", lambda _: None)
    monkeypatch.setattr(analysis_service.job_service, "update_job", updates)
    request = ClassifyRequest(analyze_job_id="expired-analysis", model_id="expired-model")

    asyncio.run(analysis_service.run_classify(Job("classify-job", "classify"), request))

    failure = updates.await_args_list[-1].kwargs
    assert failure["status"] == JobStatus.FAILED
    assert "unavailable or expired" in failure["error"]


def test_results_route_distinguishes_expired_job_from_unknown_job(monkeypatch):
    route_path = Path(__file__).resolve().parents[1] / "app" / "api" / "routes_results.py"
    spec = importlib.util.spec_from_file_location("isolated_routes_results", route_path)
    routes_results = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(routes_results)
    monkeypatch.setattr(routes_results.job_service, "get_job", AsyncMock(return_value=None))
    monkeypatch.setattr(routes_results.job_service, "was_expired", lambda _: True)
    monkeypatch.setattr(routes_results, "cleanup_result_cache", lambda: None)

    with pytest.raises(HTTPException, match="expired from the in-memory demo retention window"):
        asyncio.run(routes_results.get_job_result("expired-job"))
