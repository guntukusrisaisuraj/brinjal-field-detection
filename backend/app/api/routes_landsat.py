"""
Landsat analysis endpoint.

POST /api/landsat/analyze – load Landsat 8/9 imagery, compute indices, return tile URLs.
GET  /api/landsat/info    – return supported sensors and bands

Requires GEE to be authenticated.
"""
from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from app.earth_engine.ee_client import EEClient
from app.earth_engine.sentinel2 import aoi_from_request
from app.models.schemas import AOIRequest, JobResponse, JobStatus
from app.services.job_service import job_service
from app.utils.logger import logger

router = APIRouter()


class LandsatAnalyzeRequest(BaseModel):
    aoi: AOIRequest
    date_from: str
    date_to: str
    cloud_threshold: float = Field(20.0, ge=0, le=100)

    @field_validator("date_from", "date_to")
    @classmethod
    def validate_calendar_date(cls, value: str) -> str:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Date must use YYYY-MM-DD format.")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Invalid calendar date: {value}.") from exc
        return value

    @model_validator(mode="after")
    def validate_range(self):
        if date.fromisoformat(self.date_from) >= date.fromisoformat(self.date_to):
            raise ValueError("date_from must be earlier than date_to for Landsat analysis.")
        return self


@router.get("/landsat/info")
async def landsat_info():
    """Return Landsat sensor information."""
    return {
        "sensors": [
            {
                "id": "LC09",
                "name": "Landsat 9",
                "collection": "LANDSAT/LC09/C02/T1_L2",
                "launch_date": "2021-09-27",
                "resolution_m": 30,
                "bands": {
                    "SR_B2": "Blue",
                    "SR_B3": "Green",
                    "SR_B4": "Red",
                    "SR_B5": "NIR",
                    "SR_B6": "SWIR1",
                    "SR_B7": "SWIR2",
                },
                "revisit_days": 16,
            },
            {
                "id": "LC08",
                "name": "Landsat 8",
                "collection": "LANDSAT/LC08/C02/T1_L2",
                "launch_date": "2013-02-11",
                "resolution_m": 30,
                "bands": {
                    "SR_B2": "Blue",
                    "SR_B3": "Green",
                    "SR_B4": "Red",
                    "SR_B5": "NIR",
                    "SR_B6": "SWIR1",
                    "SR_B7": "SWIR2",
                },
                "revisit_days": 16,
            },
        ],
                "indices": ["NDVI", "EVI", "NDWI", "SAVI", "NDBI"],
        "note": "Landsat does not have red-edge bands; NDRE is not available.",
    }


async def _run_landsat_job(job, request: LandsatAnalyzeRequest):
    """Background task: run Landsat analysis."""
    loop = asyncio.get_running_loop()
    try:
        await job_service.update_job(job.job_id, status=JobStatus.RUNNING,
                                      progress=10, message="Resolving AOI")
        if not EEClient.is_ready():
            raise RuntimeError("Earth Engine not initialised")

        aoi_dict = request.aoi.model_dump()
        aoi = await loop.run_in_executor(None, aoi_from_request, aoi_dict)

        await job_service.update_job(job.job_id, progress=30,
                                      message="Loading Landsat imagery")

        from app.services.landsat_service import analyze_landsat
        result = await loop.run_in_executor(
            None, analyze_landsat,
            aoi, request.date_from, request.date_to, request.cloud_threshold,
        )

        await job_service.update_job(
            job.job_id, status=JobStatus.COMPLETED, progress=100,
            message=f"Landsat analysis complete ({result['image_count']} images, sensor={result['sensor']})",
            result=result,
        )
    except Exception as exc:
        logger.exception(f"[LandsatRoute] Job {job.job_id} failed: {exc}")
        await job_service.update_job(
            job.job_id, status=JobStatus.FAILED,
            message="Landsat analysis failed", error=str(exc),
        )


@router.post("/landsat/analyze", response_model=JobResponse, status_code=202)
async def landsat_analyze(
    request: LandsatAnalyzeRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start a Landsat 8/9 analysis job.

    Loads cloud-masked Landsat imagery, creates a median composite,
    and computes NDVI, EVI, NDWI, SAVI, NDBI. Returns a tile URL for the map.
    """
    if not EEClient.is_ready():
        raise HTTPException(
            status_code=503,
            detail=(
                "Google Earth Engine is not authenticated. "
                "Configure GEE credentials before using Landsat analysis."
            ),
        )
    job = await job_service.create_job("landsat_analyze")
    background_tasks.add_task(_run_landsat_job, job, request)
    return JobResponse(
        job_id=job.job_id,
        status=JobStatus.PENDING,
        message="Landsat analysis queued. Poll /api/results/{job_id} for status.",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
