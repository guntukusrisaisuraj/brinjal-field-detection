"""State-wide candidate discovery using Earth Engine vector regions and the saved RF."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
import re
from typing import Any

import ee
import numpy as np

from app.earth_engine.feature_extraction import (
    FEATURE_BANDS,
    build_feature_image,
    feature_names_for,
)
from app.earth_engine.sentinel2 import load_sentinel2_collection
from app.models.schemas import StateDiscoveryRequest
from app.services.alphaearth_service import (
    ALPHA_EARTH_COLLECTION,
    build_alphaearth_feature_image,
)
from app.services.analysis_service import get_result, store_result
from app.services.job_service import Job, JobStatus, job_service
from app.utils.logger import logger

GAUL_LEVEL1 = "FAO/GAUL/2015/level1"
DYNAMIC_WORLD = "GOOGLE/DYNAMICWORLD/V1"
DISCOVERY_SCALE_METERS = 30
VECTOR_PAGE_SIZE = 500
SCREEN_CLASS_NON_FIELD = 0
SCREEN_CLASS_HEALTHY_CANDIDATE = 1
SCREEN_CLASS_YOUNG_STRESSED_CANDIDATE = 2
SPECTRAL_CANDIDATE_RULES = {
    "healthy": {"NDVI": 0.40, "EVI": 0.20, "SAVI": 0.30, "NDRE": 0.25},
    "young_stressed": {"NDVI": 0.25, "EVI": 0.10, "SAVI": 0.20, "NDRE": 0.15},
}
_state_names: list[str] | None = None
_state_boundary_names: dict[str, list[str]] = {}

INDIA_ADMIN_UNITS = (
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
    "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
    "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir",
    "Ladakh", "Lakshadweep", "Puducherry",
)
_STATE_GAUL_ALIASES = {
    "Andaman and Nicobar Islands": ["Andaman and Nicobar Islands", "Andaman & Nicobar Islands"],
    "Dadra and Nagar Haveli and Daman and Diu": [
        "Dadra and Nagar Haveli and Daman and Diu",
        "Dadra and Nagar Haveli", "Daman and Diu",
    ],
    "Delhi": ["Delhi", "NCT of Delhi", "National Capital Territory of Delhi"],
    "Odisha": ["Odisha", "Orissa"],
    "Puducherry": ["Puducherry", "Pondicherry"],
    "Uttarakhand": ["Uttarakhand", "Uttaranchal"],
}


def map_gaul_state_names(gaul_names: list[str]) -> dict[str, list[str]]:
    """Map clean official Indian names to the actual GAUL ADM1 name(s)."""
    def normalize(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", name.casefold().replace("&", " and ")).strip()

    available = {normalize(str(name).strip()): str(name).strip() for name in gaul_names}
    mapping: dict[str, list[str]] = {}
    for display_name in INDIA_ADMIN_UNITS:
        aliases = _STATE_GAUL_ALIASES.get(display_name, [display_name])
        matches = [available[normalize(alias)] for alias in aliases if normalize(alias) in available]
        if display_name == "Dadra and Nagar Haveli and Daman and Diu":
            combined = [name for name in matches if normalize(name) == normalize(display_name)]
            if combined:
                matches = combined
            elif not all(normalize(name) in available for name in aliases[1:]):
                matches = []
        if matches:
            mapping[display_name] = list(dict.fromkeys(matches))
    return mapping


def available_indian_states() -> list[str]:
    """Return clean selector labels backed by names from the existing GAUL source."""
    global _state_names, _state_boundary_names
    if _state_names is None:
        collection = ee.FeatureCollection(GAUL_LEVEL1).filter(
            ee.Filter.eq("ADM0_NAME", "India")
        )
        names = collection.aggregate_array("ADM1_NAME").distinct().sort().getInfo()
        if not names:
            raise RuntimeError("Earth Engine returned no Indian state names from the GAUL boundary dataset.")
        gaul_names = [str(name) for name in names]
        _state_boundary_names = map_gaul_state_names(gaul_names)
        # Keep the selector complete and canonical. For unchanged GAUL names,
        # identity mapping is the safe fallback; aliases above handle known renames.
        for display_name in INDIA_ADMIN_UNITS:
            _state_boundary_names.setdefault(
                display_name,
                _STATE_GAUL_ALIASES.get(display_name, [display_name])[1:]
                if display_name == "Dadra and Nagar Haveli and Daman and Diu"
                else [display_name],
            )
        _state_names = list(INDIA_ADMIN_UNITS)
        missing = set(INDIA_ADMIN_UNITS).difference(_state_boundary_names)
        if missing:
            logger.warning(f"[StateDiscovery] GAUL has no recognized boundary mapping for: {sorted(missing)}")
    return list(_state_names)


def canonical_state_name(state: str) -> str:
    """Validate and return the clean label used by the selector and response."""
    requested = state.strip().casefold()
    match = next((name for name in available_indian_states() if name.casefold() == requested), None)
    if match is None:
        # Keep accepting a previously returned GAUL name during API transitions.
        match = next((display for display, names in _state_boundary_names.items()
                      if any(name.casefold() == requested for name in names)), None)
    if match is None:
        raise ValueError(f"Unsupported Indian state '{state}'. Select a state returned by the state list endpoint.")
    return match


def boundary_names_for_state(state: str) -> list[str]:
    """Resolve a selector label to its one or more GAUL ADM1 boundary names."""
    display_name = canonical_state_name(state)
    if not _state_boundary_names:
        # Supports injected authoritative names in tests and warm-process cache resets.
        _state_boundary_names.update(map_gaul_state_names(_state_names or []))
    names = _state_boundary_names.get(display_name)
    if not names:
        names = (
            ["Dadra and Nagar Haveli", "Daman and Diu"]
            if display_name == "Dadra and Nagar Haveli and Daman and Diu"
            else _STATE_GAUL_ALIASES.get(display_name, [display_name])
        )
    return list(names)


def state_boundary_geometry(state: str) -> ee.Geometry:
    """Look up the boundary using mapped GAUL name(s), including merged UT parts."""
    boundary_names = boundary_names_for_state(state)
    features = (
        ee.FeatureCollection(GAUL_LEVEL1)
        .filter(ee.Filter.eq("ADM0_NAME", "India"))
        .filter(ee.Filter.inList("ADM1_NAME", boundary_names))
    )
    if int(features.size().getInfo()) == 0:
        raise ValueError(
            f"The GAUL boundary source has no matching geometry for {canonical_state_name(state)} "
            f"(looked for {', '.join(boundary_names)})."
        )
    return features.geometry()


def _valid_model_schema(model: Any, alphaearth_enabled: bool) -> list[str]:
    enabled = bool(getattr(model, "alphaearth_enabled", False))
    if enabled != alphaearth_enabled:
        raise ValueError(
            "The selected model's AlphaEarth setting does not match this discovery request. "
            "Choose a model trained with the requested feature sources."
        )
    names = list(getattr(model, "feature_names", FEATURE_BANDS))
    if names != feature_names_for(enabled):
        raise ValueError("The saved model feature schema is unsupported for state discovery.")
    return names


def _candidate_screen_class(ndvi: float, evi: float, savi: float, ndre: float) -> int:
    """Return a preliminary spectral pseudo-class; this is never ground truth."""
    values = np.asarray([ndvi, evi, savi, ndre], dtype=float)
    if not np.isfinite(values).all() or ndvi < 0.20:
        return SCREEN_CLASS_NON_FIELD
    healthy = SPECTRAL_CANDIDATE_RULES["healthy"]
    if (ndvi >= healthy["NDVI"] and evi >= healthy["EVI"]
            and savi >= healthy["SAVI"] and ndre >= healthy["NDRE"]):
        return SCREEN_CLASS_HEALTHY_CANDIDATE
    young = SPECTRAL_CANDIDATE_RULES["young_stressed"]
    if (ndvi >= young["NDVI"] and evi >= young["EVI"]
            and savi >= young["SAVI"] and ndre >= young["NDRE"]):
        return SCREEN_CLASS_YOUNG_STRESSED_CANDIDATE
    return SCREEN_CLASS_NON_FIELD


def _candidate_screen_class_image(feature_image: ee.Image) -> ee.Image:
    """Create 0/1/2 preliminary candidate classes from the four supplied indices."""
    ndvi = feature_image.select("NDVI")
    evi = feature_image.select("EVI")
    savi = feature_image.select("SAVI")
    ndre = feature_image.select("NDRE")
    healthy = (
        ndvi.gte(0.40).And(evi.gte(0.20))
        .And(savi.gte(0.30)).And(ndre.gte(0.25))
    )
    young_stressed = (
        ndvi.gte(0.25).And(evi.gte(0.10))
        .And(savi.gte(0.20)).And(ndre.gte(0.15))
    )
    return ndvi.multiply(0).toInt8().where(young_stressed, 2).where(healthy, 1).rename(
        "candidate_screening_class"
    )


def _candidate_regions(
    state_geometry: ee.Geometry,
    date_from: str,
    date_to: str,
    feature_image: ee.Image,
    min_area_ha: float,
):
    """Build connected crop-label regions server-side; these are not parcel boundaries."""
    collection = (
        ee.ImageCollection(DYNAMIC_WORLD)
        .filterBounds(state_geometry)
        .filterDate(date_from, (date.fromisoformat(date_to) + timedelta(days=1)).isoformat())
        .select("label")
    )
    if int(collection.size().getInfo()) == 0:
        raise ValueError("Dynamic World has no crop-label observations for this state and date range.")
    label = collection.reduce(ee.Reducer.mode()).rename("label")
    native_projection = label.projection()
    label_30m = label.reduceResolution(
        reducer=ee.Reducer.mode(), maxPixels=1024
    ).reproject(crs=native_projection, scale=DISCOVERY_SCALE_METERS)
    # Dynamic World crop regions remain the agricultural prefilter. The spectral
    # classes below are candidate/pseudo-labels only; Random Forest predicts final class.
    screening_class = _candidate_screen_class_image(feature_image)
    crop_mask = (
        screening_class.updateMask(label_30m.eq(4).And(screening_class.gt(0)))
        .selfMask()
        .clip(state_geometry)
    )
    regions = crop_mask.reduceToVectors(
        reducer=ee.Reducer.countEvery(),
        geometry=state_geometry,
        scale=DISCOVERY_SCALE_METERS,
        geometryType="polygon",
        eightConnected=True,
        labelProperty="candidate_class",
        maxPixels=10**13,
        tileScale=8,
    )
    regions = regions.map(
        lambda feature: feature.set({
            "area_ha": feature.geometry().area(maxError=1).divide(10_000),
            "centroid": feature.geometry().centroid(maxError=1).coordinates(),
            "label_source": "spectral_pseudo_label",
            "screening_label_source": "spectral_pseudo_label",
            "screening_label_type": "candidate/pseudo-label",
        })
    )
    return regions.filter(ee.Filter.gte("area_ha", min_area_ha))


def _get_feature_properties(properties: dict[str, Any], names: list[str]) -> list[float] | None:
    values = []
    for name in names:
        value = properties.get(name)
        if value is None:
            value = properties.get(f"{name}_mean")
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not np.isfinite(number):
            return None
        values.append(number)
    return values


def _state_bounds(geometry: ee.Geometry) -> dict[str, Any]:
    return geometry.bounds(maxError=1).getInfo()


def _candidate_field_record(
    sequence: int,
    feature: dict[str, Any],
    probability: float,
    confidence: str,
    date_to: str,
    min_area_ha: float,
    feature_values: dict[str, float] | None = None,
) -> dict[str, Any] | None:
    """Validate a real vector result and derive its center from the EE geometry."""
    geometry = feature.get("geometry")
    properties = feature.get("properties") or {}
    centroid = properties.get("centroid")
    try:
        area_ha = float(properties["area_ha"])
        probability = float(probability)
        latitude, longitude = float(centroid[1]), float(centroid[0])
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    if (
        not geometry
        or not np.all(np.isfinite([area_ha, probability, latitude, longitude]))
        or area_ha < min_area_ha
        or not 0 <= probability <= 1
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        return None
    try:
        screening_class = int(properties.get("candidate_class"))
    except (TypeError, ValueError):
        screening_class = None
    screening_class_name = {
        SCREEN_CLASS_HEALTHY_CANDIDATE: "possible healthy brinjal-like field",
        SCREEN_CLASS_YOUNG_STRESSED_CANDIDATE: "possible young/stressed brinjal-like field",
    }.get(screening_class, "possible crop candidate")
    return {
        "field_id": f"BR-{sequence:06d}",
        "latitude": latitude,
        "longitude": longitude,
        "area_hectares": area_ha,
        "area_ha": area_ha,
        "brinjal_probability": probability,
        "confidence": confidence,
        "confidence_level": confidence,
        "crop_class": "brinjal",
        "predicted_class": "brinjal",
        "label_source": "spectral_pseudo_label",
        "label_type": "candidate/pseudo-label",
        "screening_label_source": "spectral_pseudo_label",
        "screening_class": screening_class,
        "screening_class_name": screening_class_name,
        "prediction_source": "random_forest",
        "feature_values": feature_values or {},
        "extended_index_statistics": {
            index_name: {
                "min": None, "max": None, "mean": None, "median": None, "std": None,
                "status": "disabled: exact project formula and band mapping required",
            }
            for index_name in ("LCA", "MDRRL")
        },
        "mdlca_status": "disabled: exact project definition required",
        "geometry": geometry,
        "geometry_source": "connected Dynamic World crop region; not a cadastral field boundary",
        "ndvi": properties.get("NDVI_mean", properties.get("NDVI_mean_mean")),
        "is_low_ndvi": False,
        "date": date_to,
    }


async def run_state_discovery(job: Job, request: StateDiscoveryRequest) -> None:
    """Background state scan; EE raster work and candidate aggregation stay server-side."""
    loop = asyncio.get_running_loop()
    try:
        await job_service.update_job(job.job_id, status=JobStatus.RUNNING,
            progress=5, message="Validating state and loading the trained model")
        state_name = await loop.run_in_executor(None, canonical_state_name, request.state)
        model_cache = get_result(request.model_id)
        if not model_cache or "_model" not in model_cache or "_scaler" not in model_cache:
            raise ValueError("The selected model is unavailable or expired; train or load it again.")
        model = model_cache["_model"]
        scaler = model_cache["_scaler"]
        feature_names = _valid_model_schema(model, request.alphaearth_enabled)

        await job_service.update_job(job.job_id, progress=12, message=f"Loading {state_name} boundary")
        state_geometry = await loop.run_in_executor(None, state_boundary_geometry, state_name)
        bounds = await loop.run_in_executor(None, _state_bounds, state_geometry)

        await job_service.update_job(job.job_id, progress=25,
            message="Preparing cloud-filtered Sentinel-2 features at 30 m")
        collection = await loop.run_in_executor(
            None, lambda: load_sentinel2_collection(
                state_geometry, request.date_from, request.date_to, request.cloud_threshold
            )
        )
        feature_image = await loop.run_in_executor(
            None, lambda: build_feature_image(collection, state_geometry)
        )
        if request.alphaearth_enabled:
            embedding_year = date.fromisoformat(request.date_to).year
            alpha_image = await loop.run_in_executor(
                None, lambda: build_alphaearth_feature_image(state_geometry, embedding_year)
            )
            feature_image = feature_image.addBands(alpha_image).select(feature_names)

        await job_service.update_job(job.job_id, progress=45,
            message="Finding Dynamic World crop regions and reducing features server-side")
        regions = await loop.run_in_executor(
            None, lambda: _candidate_regions(
                state_geometry,
                request.date_from,
                request.date_to,
                feature_image,
                request.min_field_area_ha,
            )
        )
        summarized = await loop.run_in_executor(
            None, lambda: feature_image.reduceRegions(
                collection=regions,
                reducer=ee.Reducer.mean(),
                scale=DISCOVERY_SCALE_METERS,
                tileScale=8,
            )
        )
        region_count = int(await loop.run_in_executor(None, lambda: summarized.size().getInfo()))
        fields: list[dict[str, Any]] = []
        field_sequence = 0
        skipped_incomplete = 0
        for offset in range(0, region_count, VECTOR_PAGE_SIZE):
            await job_service.update_job(
                job.job_id,
                progress=min(90, 50 + int(38 * (offset / max(region_count, 1)))),
                message=f"Classifying candidate crop regions ({min(offset + VECTOR_PAGE_SIZE, region_count)} of {region_count})",
            )
            page = await loop.run_in_executor(
                None, lambda offset=offset: summarized.toList(VECTOR_PAGE_SIZE, offset).getInfo()
            )
            accepted: list[tuple[dict[str, Any], list[float]]] = []
            for feature in page:
                props = feature.get("properties") or {}
                row = _get_feature_properties(props, feature_names)
                if row is None:
                    skipped_incomplete += 1
                else:
                    accepted.append((feature, row))
            if not accepted:
                continue

            X = np.asarray([row for _, row in accepted], dtype=np.float32)
            X_scaled = scaler.transform(X)
            predicted = model.predict(X_scaled)
            probabilities = model.brinjal_probability(X_scaled)
            for index, (feature, row) in enumerate(accepted):
                class_id = int(predicted[index])
                if class_id != 0:
                    continue
                probability = float(probabilities[index])
                if not np.isfinite(probability) or probability < 0 or probability > 1:
                    continue
                field_sequence += 1
                confidence = model.confidence_level(probability)
                record = _candidate_field_record(
                    field_sequence, feature, probability, confidence,
                    request.date_to, request.min_field_area_ha,
                    dict(zip(feature_names, row)),
                )
                if record is not None:
                    fields.append(record)

        total_area = sum(field["area_hectares"] for field in fields)
        average_probability = (
            sum(field["brinjal_probability"] for field in fields) / len(fields)
            if fields else None
        )
        summary = {
            "state": state_name,
            "candidate_field_count": len(fields),
            "total_candidate_area_ha": total_area,
            "average_brinjal_probability": average_probability,
            "high_confidence_count": sum(f["confidence"] == "high" for f in fields),
            "medium_confidence_count": sum(f["confidence"] == "medium" for f in fields),
            "low_confidence_count": sum(f["confidence"] == "low" for f in fields),
            "date_from": request.date_from,
            "date_to": request.date_to,
            "cloud_threshold": request.cloud_threshold,
            "ndvi_threshold": request.ndvi_threshold,
            "min_field_area_ha": request.min_field_area_ha,
            "candidate_screening_guidance": {
                "purpose": "preliminary spectral pseudo-label screening only; Random Forest determines final classification",
                "healthy_rule": SPECTRAL_CANDIDATE_RULES["healthy"],
                "young_stressed_rule": SPECTRAL_CANDIDATE_RULES["young_stressed"],
                "young_stressed_false_positive_risk": "higher; weeds and other crops may also match",
                "ndwi_ndbi_are_screening_gates": False,
            },
            "candidate_source": DYNAMIC_WORLD,
            "processing_scale_meters": DISCOVERY_SCALE_METERS,
            "feature_sources": ["Sentinel-2", "AlphaEarth embeddings (64)"] if request.alphaearth_enabled else ["Sentinel-2"],
            "alphaearth_enabled": request.alphaearth_enabled,
            "alphaearth_collection": ALPHA_EARTH_COLLECTION,
            "alphaearth_year": date.fromisoformat(request.date_to).year if request.alphaearth_enabled else None,
            "incomplete_regions_skipped": skipped_incomplete,
            "boundary_note": "Connected crop-label regions are candidate areas, not cadastral farm boundaries.",
            "validation_note": "Initial brinjal candidate screening uses preliminary spectral-index guidance. Candidate regions are not confirmed brinjal cultivation. Final classification requires labelled field data and model validation.",
        }
        result = {
            "job_id": job.job_id,
            "state": state_name,
            "state_bounds": bounds,
            **summary,
            "fields": fields,
            "message": (
                "No candidate brinjal fields were detected for the selected state and analysis period."
                if not fields else f"Detected {len(fields)} candidate brinjal field regions."
            ),
        }
        store_result(job.job_id, {
            **result,
            "_predictions": fields,
            "_statistics": summary,
            "_state_geometry": state_geometry,
        })
        await job_service.update_job(job.job_id, status=JobStatus.COMPLETED,
            progress=100, message=result["message"], result=result)
    except Exception as exc:
        logger.exception(f"[StateDiscovery] Job {job.job_id} failed: {exc}")
        await job_service.update_job(job.job_id, status=JobStatus.FAILED,
            message="State discovery failed", error=str(exc))
