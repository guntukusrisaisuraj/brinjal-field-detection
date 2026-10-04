"""State-wide candidate brinjal field discovery endpoints."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.earth_engine.ee_client import EEClient
from app.models.schemas import JobResponse, JobStatus, StateDiscoveryRequest
from app.services.analysis_service import get_result
from app.services.job_service import job_service
from app.services.state_discovery_service import (
    _valid_model_schema,
    available_indian_states,
    canonical_state_name,
    run_state_discovery,
)

router = APIRouter()


@router.get("/state-discovery/states")
async def list_discovery_states():
    """Return state names directly from the existing FAO GAUL Level-1 source."""
    if not EEClient.is_ready():
        raise HTTPException(status_code=503, detail="Earth Engine is not authenticated.")
    try:
        states = await asyncio.get_running_loop().run_in_executor(None, available_indian_states)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not load state boundaries: {exc}") from exc
    return {"country": "India", "states": states, "source": "FAO/GAUL/2015/level1"}


@router.post("/state-discovery/analyze", response_model=JobResponse, status_code=202)
async def start_state_discovery(
    request: StateDiscoveryRequest,
    background_tasks: BackgroundTasks,
) -> JobResponse:
    """Queue a state scan; poll the normal /api/results/{job_id} endpoint."""
    if not EEClient.is_ready():
        raise HTTPException(status_code=503, detail="Earth Engine is not authenticated.")
    try:
        state_name = await asyncio.get_running_loop().run_in_executor(
            None, canonical_state_name, request.state
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not validate the state boundary: {exc}") from exc

    model_cache = get_result(request.model_id)
    if not model_cache or "_model" not in model_cache or "_scaler" not in model_cache:
        raise HTTPException(status_code=404, detail="The selected trained model is unavailable or expired.")
    model = model_cache["_model"]
    try:
        _valid_model_schema(model, request.alphaearth_enabled)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    request.state = state_name
    job = await job_service.create_job("state_discovery")
    background_tasks.add_task(run_state_discovery, job, request)
    return JobResponse(
        job_id=job.job_id,
        status=JobStatus.PENDING,
        message=f"State discovery queued for {state_name}. Poll /api/results/{job.job_id} for progress.",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
