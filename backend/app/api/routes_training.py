"""POST /api/training-data – upload / submit training polygon features."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from app.models.schemas import JobResponse, JobStatus, TrainingDataRequest
from app.services.analysis_service import get_result, run_extract_training
from app.services.job_service import job_service
from app.geospatial.vector import parse_training_geojson, validate_geojson

router = APIRouter()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


@router.post("/training-data", response_model=JobResponse, status_code=202)
async def upload_training_data(
    background_tasks: BackgroundTasks,
    analyze_job_id: str = Form(...),
    alphaearth_enabled: bool = Form(False),
    training_data_source: str = Form("uploaded"),
    file: UploadFile | None = File(None),
    geojson_body: str | None = Form(None),
) -> JobResponse:
    """
    Upload training polygons for feature extraction.

    Accepts either:
    - A GeoJSON file upload (`file` field), or
    - Inline GeoJSON string (`geojson_body` field)

    The GeoJSON must be a FeatureCollection where each Feature has
    a `crop_class` property (e.g., "brinjal", "other_crop", "bare_soil").
    """
    raw_geojson: str | None = None

    if file is not None:
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413,
                                detail="Uploaded file exceeds 50 MB limit.")
        raw_geojson = content.decode("utf-8", errors="replace")
    elif geojson_body:
        raw_geojson = geojson_body
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either a GeoJSON file or a geojson_body string.",
        )

    try:
        training_features = parse_training_geojson(raw_geojson)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Verify analyze job exists
    analyze_job = await job_service.get_job(analyze_job_id)
    if analyze_job is None:
        raise HTTPException(
            status_code=404,
            detail=job_service.missing_job_detail(analyze_job_id, "Analysis"),
        )
    if analyze_job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=404,
            detail=f"Analyze job '{analyze_job_id}' has not completed yet.",
        )
    if get_result(analyze_job_id) is None:
        raise HTTPException(
            status_code=404,
            detail=(f"Analysis context for job '{analyze_job_id}' is unavailable or expired. "
                    "Run the analysis again before uploading training data."),
        )

    if training_data_source not in {"uploaded", "demo"}:
        raise HTTPException(status_code=422, detail="training_data_source must be 'uploaded' or 'demo'.")

    job = await job_service.create_job("extract_training", depends_on=[analyze_job_id])
    background_tasks.add_task(
        run_extract_training,
        job,
        analyze_job_id,
        training_features,
        alphaearth_enabled=alphaearth_enabled,
        training_data_source=training_data_source,
    )

    return JobResponse(
        job_id=job.job_id,
        status=JobStatus.PENDING,
        message=f"Training data extraction queued ({len(training_features)} polygons).",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
