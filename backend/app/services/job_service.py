"""
Job service – lightweight in-memory async job store.
Suitable for college demo; replace with Redis/Celery for production.
"""
from __future__ import annotations

import asyncio
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from app.models.schemas import JobStatus
from app.utils.logger import logger

JOB_RETENTION_SECONDS = 24 * 60 * 60
MAX_TERMINAL_JOBS = 500
EXPIRED_ID_HISTORY = 1000


class Job:
    def __init__(
        self,
        job_id: str,
        job_type: str,
        depends_on: Optional[Iterable[str]] = None,
    ) -> None:
        self.job_id = job_id
        self.job_type = job_type
        self.status: JobStatus = JobStatus.PENDING
        self.progress: int = 0
        self.message: str = "Job queued"
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        # Internal cache pins; deliberately omitted from the API representation.
        self.depends_on = set(depends_on or ())
        now = datetime.now(timezone.utc).isoformat()
        self.created_at: str = now
        self.updated_at: str = now

    def update(
        self,
        status: Optional[JobStatus] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        if status is not None:
            self.status = status
        if progress is not None:
            self.progress = progress
        if message is not None:
            self.message = message
        if result is not None:
            self.result = result
        if error is not None:
            self.error = error
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class JobService:
    """Single-process demo job registry; state is lost on restart and is not shared across workers."""

    def __init__(
        self,
        retention_seconds: int = JOB_RETENTION_SECONDS,
        max_terminal_jobs: int = MAX_TERMINAL_JOBS,
    ) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = asyncio.Lock()
        self._retention_seconds = retention_seconds
        self._max_terminal_jobs = max_terminal_jobs
        self._expired_order: deque[str] = deque()
        self._expired_ids: set[str] = set()

    def _remember_expired(self, job_id: str) -> None:
        if job_id in self._expired_ids:
            return
        if len(self._expired_order) >= EXPIRED_ID_HISTORY:
            self._expired_ids.discard(self._expired_order.popleft())
        self._expired_order.append(job_id)
        self._expired_ids.add(job_id)

    def _cleanup_locked(self, now: datetime) -> None:
        """Prune only terminal jobs. Caller must hold ``_lock``."""
        terminal = [
            job for job in self._jobs.values()
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED)
        ]
        cutoff = now.timestamp() - self._retention_seconds
        expired = [
            job for job in terminal
            if datetime.fromisoformat(job.updated_at).timestamp() <= cutoff
        ]
        for job in expired:
            self._jobs.pop(job.job_id, None)
            self._remember_expired(job.job_id)

        terminal = [
            job for job in self._jobs.values()
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED)
        ]
        overflow = max(0, len(terminal) - self._max_terminal_jobs)
        for job in sorted(terminal, key=lambda item: item.updated_at)[:overflow]:
            self._jobs.pop(job.job_id, None)
            self._remember_expired(job.job_id)

    async def create_job(
        self, job_type: str, depends_on: Optional[Iterable[str]] = None
    ) -> Job:
        async with self._lock:
            self._cleanup_locked(datetime.now(timezone.utc))
            job_id = str(uuid.uuid4())
            job = Job(job_id=job_id, job_type=job_type, depends_on=depends_on)
            self._jobs[job_id] = job
            logger.info(f"[JobService] Created job {job_id} ({job_type})")
            return job

    async def get_job(self, job_id: str) -> Optional[Job]:
        async with self._lock:
            self._cleanup_locked(datetime.now(timezone.utc))
            return self._jobs.get(job_id)

    async def update_job(self, job_id: str, **kwargs: Any) -> Optional[Job]:
        async with self._lock:
            self._cleanup_locked(datetime.now(timezone.utc))
            job = self._jobs.get(job_id)
            if job:
                job.update(**kwargs)
                self._cleanup_locked(datetime.now(timezone.utc))
            return job

    async def list_jobs(self) -> list[Dict[str, Any]]:
        async with self._lock:
            self._cleanup_locked(datetime.now(timezone.utc))
            return [j.to_dict() for j in self._jobs.values()]

    def was_expired(self, job_id: str) -> bool:
        """Whether a recently pruned job ID is known to have expired."""
        return job_id in self._expired_ids

    def missing_job_detail(self, job_id: str, label: str) -> str:
        """Build a useful prerequisite error without changing job response data."""
        if self.was_expired(job_id):
            return (
                f"{label} job '{job_id}' expired from the in-memory demo retention window. "
                "Run the prerequisite workflow again."
            )
        return f"{label} job '{job_id}' not found."

    def protected_context_ids(self) -> set[str]:
        """Return job/context IDs referenced by pending or running jobs."""
        protected: set[str] = set()
        for job in self._jobs.values():
            if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                protected.add(job.job_id)
                protected.update(job.depends_on)
        return protected


# Module-level singleton – imported by all routes
job_service = JobService()
