"""POST /api/classify – run brinjal detection using trained model."""
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.models.schemas import ClassifyRequest, JobResponse, JobStatus
from app.services.job_service import job_service
from app.services.analysis_service import run_classify, get_result

router = APIRouter()


@router.post("/classify", response_model=JobResponse, status_code=202)
async def classify(
    request: ClassifyRequest,
    background_tasks: BackgroundTasks,
) -> JobResponse:
    """
    Run the brinjal classification pipeline over the AOI.

    Results are labelled as **'Predicted Brinjal Fields'** – not confirmed
    brinjal cultivation.

    Requires:
    - analyze_job_id: a completed /api/analyze job
    - model_id: a trained model ID from /api/train result

    Returns job_id; poll /api/results/{job_id} for classification output.
    """
    analyze_job = await job_service.get_job(request.analyze_job_id)
    if analyze_job is None:
        raise HTTPException(
            status_code=404,
            detail=job_service.missing_job_detail(request.analyze_job_id, "Analysis"),
        )
    if analyze_job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=404,
            detail=f"Analyze job '{request.analyze_job_id}' has not completed yet.",
        )

    if get_result(request.analyze_job_id) is None:
        raise HTTPException(
            status_code=404,
            detail=(f"Analysis context for job '{request.analyze_job_id}' is unavailable or expired. "
                    "Run the analysis again before classification."),
        )

    model_cache = get_result(request.model_id)
    if model_cache is None or "_model" not in model_cache:
        raise HTTPException(
            status_code=404,
            detail=(f"Model context '{request.model_id}' is unavailable or expired. "
                    "Train the model again before classification."),
        )

    job = await job_service.create_job(
        "classify", depends_on=[request.analyze_job_id, request.model_id]
    )
    background_tasks.add_task(run_classify, job, request)

    return JobResponse(
        job_id=job.job_id,
        status=JobStatus.PENDING,
        message="Brinjal classification queued. Poll /api/results/{job_id} for output.",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
