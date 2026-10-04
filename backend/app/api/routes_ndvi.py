"""POST /api/ndvi – compute NDVI for a given AOI (lighter weight endpoint)."""
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.models.schemas import NDVIRequest, JobResponse, JobStatus
from app.services.job_service import job_service
from app.services.analysis_service import run_analyze
from app.earth_engine.ee_client import EEClient
from app.models.schemas import AnalyzeRequest

router = APIRouter()


@router.post("/ndvi", response_model=JobResponse, status_code=202)
async def compute_ndvi(
    request: NDVIRequest,
    background_tasks: BackgroundTasks,
) -> JobResponse:
    """
    Compute NDVI for the given AOI and date range.

    Internally runs the same pipeline as /analyze but is
    exposed as a separate endpoint for clarity.
    """
    if not EEClient.is_ready():
        raise HTTPException(status_code=503,
                            detail="Google Earth Engine not authenticated.")

    # Reuse AnalyzeRequest structure
    analyze_req = AnalyzeRequest(
        aoi=request.aoi,
        date_from=request.date_from,
        date_to=request.date_to,
        cloud_threshold=request.cloud_threshold,
        ndvi_threshold=request.ndvi_threshold,
        scale_meters=request.scale_meters,
    )

    job = await job_service.create_job("ndvi")
    background_tasks.add_task(run_analyze, job, analyze_req)

    return JobResponse(
        job_id=job.job_id,
        status=JobStatus.PENDING,
        message="NDVI computation queued.",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
