"""
Satellite sources and intelligence endpoints.

GET  /api/satellite/sources          – list all satellite sources with credential/access status
POST /api/satellite/planet/check     – check Planet API key validity
POST /api/satellite/alphaearth       – get AlphaEarth embedding for an AOI
"""
from __future__ import annotations

import os
import asyncio
from datetime import date
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.earth_engine.ee_client import EEClient
from app.models.schemas import AOIRequest, _validate_date_range
from app.utils.logger import logger

router = APIRouter()


# ---------------------------------------------------------------------------
# Sources manifest
# ---------------------------------------------------------------------------

@router.get("/satellite/sources")
async def get_satellite_sources():
    """
    Return all supported satellite data sources with their status,
    specifications, and capability description.
    """
    gee_ready = EEClient.is_ready()
    planet_key = bool(os.getenv("PLANET_API_KEY", "").strip())

    return {
        "sources": [
            {
                "id": "sentinel2",
                "name": "Sentinel-2",
                "agency": "ESA / Copernicus",
                "resolution_m": 10,
                "bands": 13,
                "revisit_days": 5,
                "available": gee_ready,
                "requires_credentials": "Google Earth Engine",
                "credential_configured": gee_ready,
                "collection": "COPERNICUS/S2_SR_HARMONIZED",
                "description": (
                    "10m optical imagery. The primary data source for NDVI, EVI, "
                    "NDWI, SAVI, NDBI, NDRE computation and Random Forest classification."
                ),
                "indices": ["NDVI", "EVI", "NDWI", "SAVI", "NDBI", "NDRE"],
            },
            {
                "id": "landsat",
                "name": "Landsat 8 / 9",
                "agency": "NASA / USGS",
                "resolution_m": 30,
                "bands": 8,
                "revisit_days": 16,
                "available": gee_ready,
                "requires_credentials": "Google Earth Engine",
                "credential_configured": gee_ready,
                "collection": "LANDSAT/LC09/C02/T1_L2",
                "description": (
                    "30m optical imagery with 50+ years of archive (1972-present). "
                    "Useful for historical analysis and long-term land-cover change detection."
                ),
                "indices": ["NDVI", "EVI", "NDWI", "SAVI", "NDBI"],
            },
            {
                "id": "planet",
                "name": "Planet",
                "agency": "Planet Labs",
                "resolution_m": 3,
                "bands": 8,
                "revisit_days": 1,
                "available": planet_key,
                "requires_credentials": "Planet API Key (PLANET_API_KEY in .env)",
                "credential_configured": planet_key,
                "collection": "PSScene (Planet Scope)",
                "description": (
                    "3–5m daily imagery with 8 spectral bands. Enables field-level "
                    "crop monitoring and sub-parcel analysis. Requires a Planet "
                    "subscription. Configure PLANET_API_KEY in backend/.env."
                ),
                "indices": ["NDVI", "EVI"],
                "credential_note": (
                    None if planet_key
                    else "PLANET_API_KEY not configured. Set it in backend/.env to enable Planet."
                ),
            },
            {
                "id": "alphaearth",
                "name": "AlphaEarth (Google)",
                "agency": "Google DeepMind / Earth Engine",
                "resolution_m": 10,
                "bands": 64,
                "revisit_days": 365,
                "available": gee_ready,
                "requires_credentials": "Google Earth Engine + dataset access",
                "credential_configured": gee_ready,
                "collection": "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL",
                "description": (
                    "64-dimensional annual satellite embeddings at 10m resolution. "
                    "Dense representations learned from global satellite imagery, "
                    "enabling downstream land-cover classification, crop mapping, "
                    "and change detection without task-specific labels."
                ),
                "embedding_dims": 64,
                "use_cases": [
                    "Crop type classification",
                    "Land cover mapping",
                    "Agricultural change detection",
                    "Field boundary delineation",
                ],
                "credential_note": (
                    "Requires GEE project access to GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL. "
                    "May need allowlisting. See https://earthengine.google.com/noncommercial/"
                ),
            },
        ]
    }


# ---------------------------------------------------------------------------
# Planet check
# ---------------------------------------------------------------------------

@router.post("/satellite/planet/check")
async def check_planet():
    """
    Validate the configured Planet API key and list accessible item types.
    Returns real status — never mocks data.
    """
    from app.services.planet_service import check_planet_access
    result = await check_planet_access()
    return result


# ---------------------------------------------------------------------------
# AlphaEarth embedding
# ---------------------------------------------------------------------------

class AlphaEarthRequest(BaseModel):
    aoi: AOIRequest
    date_from: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_to: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")

    @model_validator(mode="after")
    def validate_dates(self):
        _validate_date_range(self.date_from, self.date_to)
        return self


class AlphaEarthResponse(BaseModel):
    accessible: bool
    dataset: str
    source: str
    resolution_m: int
    embedding_dims: int
    year: int
    annual_period_start: str
    annual_period_end: str
    requested_date_from: str
    requested_date_to: str
    date_selection: str
    tile_url: Optional[str]
    visualization_label: str
    visualization_available: bool
    visualization_message: Optional[str]
    aoi_bounds: Optional[Dict[str, Any]]
    n_images: int
    n_embedding_bands: int
    band_names: list[str]
    error: Optional[str]


@router.post("/satellite/alphaearth", response_model=AlphaEarthResponse)
async def get_alphaearth_embedding(request: AlphaEarthRequest):
    """
    Request AlphaEarth embedding statistics for an AOI.

    Uses GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL — a 64-dimensional dense
    satellite embedding at 10m resolution.

    Requires GEE access and dataset allowlisting.
    Returns clear error if not accessible.
    """
    if not EEClient.is_ready():
        raise HTTPException(
            status_code=503,
            detail=(
                "Google Earth Engine is not authenticated. "
                "AlphaEarth requires GEE credentials."
            ),
        )

    from app.earth_engine.sentinel2 import aoi_from_request
    from app.services.alphaearth_service import get_alphaearth_info

    # The annual image for date_to's calendar year is returned. AlphaEarth
    # summarizes a full year; the requested range is not a temporal composite.
    resolved_year = date.fromisoformat(request.date_to).year

    loop = asyncio.get_running_loop()
    try:
        aoi_dict = request.aoi.model_dump()
        aoi = await loop.run_in_executor(None, aoi_from_request, aoi_dict)
        result = await loop.run_in_executor(
            None,
            get_alphaearth_info,
            aoi,
            resolved_year,
            request.date_from,
            request.date_to,
        )
        return result
    except Exception as exc:
        logger.exception(f"[SatelliteRoute] AlphaEarth error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
