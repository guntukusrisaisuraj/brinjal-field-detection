"""POST /api/train – train the Random Forest classifier."""
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.models.schemas import TrainRequest, JobResponse, JobStatus
from app.services.job_service import job_service
from app.services.analysis_service import get_result, run_train

router = APIRouter()


@router.post("/train", response_model=JobResponse, status_code=202)
async def train_model(
    request: TrainRequest,
    background_tasks: BackgroundTasks,
) -> JobResponse:
    """
    Train the Random Forest classifier using extracted training features.

    Requires:
    - analyze_job_id: a completed /api/analyze job
    - training_job_id: a completed /api/training-data job

    Returns a job_id; poll /api/results/{job_id} for metrics.
    """
    # Verify prerequisite jobs
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

    training_job = await job_service.get_job(request.training_job_id)
    if training_job is None:
        raise HTTPException(
            status_code=404,
            detail=job_service.missing_job_detail(request.training_job_id, "Training-data"),
        )
    if training_job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=404,
            detail=f"Training-data job '{request.training_job_id}' has not completed yet.",
        )
    if get_result(request.training_job_id) is None:
        raise HTTPException(
            status_code=404,
            detail=(f"Extracted training data for job '{request.training_job_id}' "
                    "is unavailable or expired. Upload training data again."),
        )

    job = await job_service.create_job("train", depends_on=[request.training_job_id])
    background_tasks.add_task(run_train, job, request)

    return JobResponse(
        job_id=job.job_id,
        status=JobStatus.PENDING,
        message=(
            f"Model training queued. "
            f"RF with {request.n_estimators} trees. "
            "Poll /api/results/{job_id} for accuracy metrics."
        ),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
