"""
Agricultural / Brinjal Field Score endpoint.

POST /api/score  – compute the composite suitability score from spectral indices.

This score is a prototype calibrated metric. See score_service.py for the
full documented formula. The endpoint does NOT claim to confirm brinjal presence.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.score_service import compute_score

router = APIRouter()


class ScoreRequest(BaseModel):
    ndvi: float = Field(..., ge=-1.0, le=1.0,
                        description="Normalized Difference Vegetation Index")
    evi: Optional[float] = Field(None, ge=-1.0, le=2.0,
                                  description="Enhanced Vegetation Index")
    savi: Optional[float] = Field(None, ge=-1.0, le=2.0,
                                   description="Soil-Adjusted Vegetation Index")
    ndwi: Optional[float] = Field(None, ge=-1.0, le=1.0,
                                   description="Normalized Difference Water Index")
    ndre: Optional[float] = Field(None, ge=-1.0, le=1.0,
                                   description="Normalized Difference Red Edge")
    ndbi: Optional[float] = Field(None, ge=-1.0, le=1.0,
                                   description="Normalized Difference Built-up Index")


@router.post("/score")
async def compute_field_score(request: ScoreRequest):
    """
    Compute the Agricultural / Brinjal Field Score.

    Accepts spectral index values and returns a composite suitability score [0, 100]
    with per-component breakdown and a documented formula.

    **Prototype metric** — does not confirm brinjal cultivation.
    Ground-truth verification is required for operational conclusions.
    """
    result = compute_score(
        ndvi=request.ndvi,
        evi=request.evi,
        savi=request.savi,
        ndwi=request.ndwi,
        ndre=request.ndre,
        ndbi=request.ndbi,
    )
    return result


@router.get("/score/formula")
async def get_score_formula():
    """Return the documented score formula and weight breakdown."""
    return {
        "formula": "Score = (0.35×NDVI + 0.20×EVI + 0.15×SAVI + 0.15×(1-NDWI) + 0.10×NDRE + 0.05×(1-NDBI)) × 100",
        "weights": {
            "NDVI":  {"weight": 0.35, "rationale": "Primary vegetation density indicator"},
            "EVI":   {"weight": 0.20, "rationale": "Canopy structure, less saturated than NDVI"},
            "SAVI":  {"weight": 0.15, "rationale": "Soil-adjusted vegetation, better for sparse fields"},
            "NDWI":  {"weight": 0.15, "rationale": "Inverted — drier soil preferred for drip-irrigated brinjal"},
            "NDRE":  {"weight": 0.10, "rationale": "Chlorophyll/crop health via red-edge (Sentinel-2 only)"},
            "NDBI":  {"weight": 0.05, "rationale": "Inverted — penalises built-up / impervious land"},
        },
        "scale": "[0, 100]",
        "grades": {
            "A (75-100)": "Very High Suitability — intensive agriculture signature",
            "B (55-75)":  "High Suitability — dense crop canopy",
            "C (30-55)":  "Moderate Suitability — mixed vegetation",
            "D (0-30)":   "Low Suitability — sparse/no vegetation, built-up, or water",
        },
        "disclaimer": (
            "Prototype metric. Does not confirm brinjal (eggplant) presence. "
            "Spectral similarity to brinjal may be shared by other crops. "
            "Use in conjunction with Random Forest classification and ground-truth data."
        ),
    }
