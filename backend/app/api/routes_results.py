"""
Results, statistics, model, and export endpoints.
"""
from __future__ import annotations

import math

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.geospatial.export import export_csv, export_geojson, export_summary_report
from app.models.schemas import ExportFormat
from app.services.analysis_service import cleanup_result_cache, get_result
from app.services.job_service import job_service

router = APIRouter()


def _missing_job_detail(job_id: str) -> str:
    if job_service.was_expired(job_id):
        return (
            f"Job '{job_id}' expired from the in-memory demo retention window. "
            "Submit the workflow again."
        )
    return f"Job '{job_id}' not found."


# ---------------------------------------------------------------------------
# Job status / results
# ---------------------------------------------------------------------------

@router.get("/results/{job_id}")
async def get_job_result(job_id: str):
    """Poll job status and result."""
    job = await job_service.get_job(job_id)
    cleanup_result_cache()
    if job is None:
        raise HTTPException(status_code=404, detail=_missing_job_detail(job_id))
    return job.to_dict()


# ---------------------------------------------------------------------------
# Predictions (JSON – used by the map)
# ---------------------------------------------------------------------------

@router.get("/predictions/{classify_job_id}")
async def get_predictions(classify_job_id: str):
    """
    Return prediction point records as JSON for map display.

    Each record contains: latitude, longitude, predicted_class,
    brinjal_probability, confidence_level, ndvi, is_low_ndvi, date.
    """
    job = await job_service.get_job(classify_job_id)
    if job is None:
        raise HTTPException(status_code=404,
                            detail=_missing_job_detail(classify_job_id))

    cached = get_result(classify_job_id)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail=("Prediction data for this job is unavailable or expired from in-memory "
                    "retention. Run classification again."),
        )

    predictions = cached.get("_predictions")
    if predictions is None:
        raise HTTPException(
            status_code=404,
            detail="Predictions not available. Is the classify job complete?",
        )
    return {"predictions": predictions, "count": len(predictions)}


@router.get("/probability-layer/{classify_job_id}")
async def get_probability_layer(classify_job_id: str):
    """Return a sparse, georeferenced layer from the classifier's stored RF probabilities."""
    job = await job_service.get_job(classify_job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=_missing_job_detail(classify_job_id))

    cached = get_result(classify_job_id)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail="Probability data for this job is unavailable or expired. Run classification again.",
        )
    predictions = cached.get("_predictions")
    if predictions is None:
        raise HTTPException(status_code=404, detail="Predictions not available. Is the classify job complete?")

    # Keep only valid stored prediction samples; no interpolation or synthetic fill is applied.
    points = []
    for record in predictions:
        try:
            lat = float(record["latitude"])
            lon = float(record["longitude"])
            probability = float(record["brinjal_probability"])
        except (KeyError, TypeError, ValueError):
            continue
        if not all(map(math.isfinite, (lat, lon, probability))):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 0 <= probability <= 1):
            continue
        points.append({"latitude": lat, "longitude": lon, "probability": probability})

    bounds = None
    if points:
        bounds = {
            "south": min(point["latitude"] for point in points),
            "west": min(point["longitude"] for point in points),
            "north": max(point["latitude"] for point in points),
            "east": max(point["longitude"] for point in points),
        }
    return {
        "job_id": classify_job_id,
        "layer_type": "brinjal_probability",
        "bounds": bounds,
        "points": points,
        "count": len(points),
        "source": "random_forest_prediction_records",
    }


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

@router.get("/statistics/{classify_job_id}")
async def get_statistics(classify_job_id: str):
    """Return area statistics for a completed classify job."""
    job = await job_service.get_job(classify_job_id)
    if job is None:
        raise HTTPException(status_code=404,
                            detail=_missing_job_detail(classify_job_id))

    cached = get_result(classify_job_id)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail=("Statistics for this job are unavailable or expired from in-memory "
                    "retention. Run classification again."),
        )

    stats = cached.get("_statistics")
    if stats is None:
        raise HTTPException(status_code=404,
                            detail="Statistics not available. Is the classify job complete?")
    return stats


# ---------------------------------------------------------------------------
# Model metrics
# ---------------------------------------------------------------------------

@router.get("/model/{train_job_id}")
async def get_model_metrics(train_job_id: str):
    """Return model evaluation metrics for a completed train job."""
    cached = get_result(train_job_id)
    if cached is None:
        raise HTTPException(status_code=404,
                            detail=(f"Training result for job '{train_job_id}' is unavailable "
                                    "or expired from in-memory retention. Train the model again."))
    # Remove internal underscore keys
    return {k: v for k, v in cached.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@router.get("/export/{classify_job_id}")
async def export_results(
    classify_job_id: str,
    format: ExportFormat = ExportFormat.GEOJSON,
):
    """
    Export classification results.

    format: csv | geojson | report
    """
    job = await job_service.get_job(classify_job_id)
    if job is None:
        raise HTTPException(status_code=404,
                            detail=_missing_job_detail(classify_job_id))

    cached = get_result(classify_job_id)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail=("Export data for this job is unavailable or expired from in-memory "
                    "retention. Run classification again."),
        )

    predictions = cached.get("_predictions", [])
    statistics = cached.get("_statistics", {})

    if format == ExportFormat.CSV:
        data = export_csv(predictions)
        return Response(
            content=data,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=brinjal_predictions_{classify_job_id[:8]}.csv"
            },
        )

    elif format == ExportFormat.GEOJSON:
        features = [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [p["longitude"], p["latitude"]],
                },
                "properties": {k: v for k, v in p.items()
                               if k not in ("latitude", "longitude")},
            }
            for p in predictions
            if p.get("latitude") and p.get("longitude")
        ]
        data = export_geojson(features, metadata=statistics)
        return Response(
            content=data,
            media_type="application/geo+json",
            headers={
                "Content-Disposition": f"attachment; filename=brinjal_predictions_{classify_job_id[:8]}.geojson"
            },
        )

    elif format == ExportFormat.REPORT:
        data = export_summary_report(statistics)
        return Response(
            content=data,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f"attachment; filename=brinjal_report_{classify_job_id[:8]}.md"
            },
        )

    raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")
