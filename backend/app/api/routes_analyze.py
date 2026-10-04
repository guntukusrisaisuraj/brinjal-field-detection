"""POST /api/analyze – load Sentinel-2 data and build feature image."""
from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.models.schemas import AnalyzeRequest, JobResponse, JobStatus
from app.services.job_service import job_service
from app.services.analysis_service import run_analyze
from app.earth_engine.ee_client import EEClient
import asyncio
from datetime import datetime, timezone

router = APIRouter()


@router.post("/analyze", response_model=JobResponse, status_code=202)
async def analyze(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
) -> JobResponse:
    """
    Start a Sentinel-2 analysis job.

    Loads the collection, applies cloud masking, computes NDVI and all
    spectral features. Returns a job_id for polling.

    Long-running – use GET /api/results/{job_id} to check progress.
    """
    if not EEClient.is_ready():
        raise HTTPException(
            status_code=503,
            detail=(
                "Google Earth Engine is not authenticated. "
                "Configure GEE_SERVICE_ACCOUNT_EMAIL + GEE_PRIVATE_KEY_FILE in .env, "
                "or run `earthengine authenticate` before starting the server."
            ),
        )

    job = await job_service.create_job("analyze")
    background_tasks.add_task(run_analyze, job, request)

    return JobResponse(
        job_id=job.job_id,
        status=JobStatus.PENDING,
        message="Analysis job queued. Poll /api/results/{job_id} for status.",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
