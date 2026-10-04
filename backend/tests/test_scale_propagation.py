from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import numpy as np

from app.earth_engine.feature_extraction import FEATURE_BANDS
from app.models.schemas import AnalyzeRequest, ClassifyRequest
from app.api import routes_results
from app.services import analysis_service
from app.services.job_service import Job


def test_run_analyze_stores_requested_scale(monkeypatch):
    aoi = Mock()
    aoi.bounds.return_value.getInfo.return_value = {"type": "Polygon"}
    feature_image = Mock()
    collection = object()
    cached_results = {}

    monkeypatch.setattr(analysis_service.EEClient, "is_ready", lambda: True)
    monkeypatch.setattr(analysis_service, "aoi_from_request", lambda _: aoi)
    monkeypatch.setattr(analysis_service, "load_sentinel2_collection", lambda *args: collection)
    monkeypatch.setattr(analysis_service, "collection_info", lambda _: {"image_count": 1})
    monkeypatch.setattr(analysis_service, "build_feature_image", lambda *_: feature_image)
    monkeypatch.setattr(analysis_service, "aoi_index_means", lambda *_: {name: 0.1 for name in ("NDVI", "EVI", "SAVI", "NDWI", "NDRE", "NDBI")})
    validate = Mock()
    monkeypatch.setattr(analysis_service, "validate_feature_image", validate)
    monkeypatch.setattr(analysis_service, "get_ndvi_tile_url", lambda *_: {"ndvi_url": "tiles"})
    monkeypatch.setattr(analysis_service, "store_result", lambda key, value: cached_results.update({key: value}))
    monkeypatch.setattr(analysis_service.job_service, "update_job", AsyncMock())

    request = AnalyzeRequest(
        aoi={"latitude": 18.5, "longitude": 73.8},
        date_from="2025-01-01",
        date_to="2025-01-02",
        scale_meters=60,
    )

    import asyncio
    asyncio.run(analysis_service.run_analyze(Job("analysis", "analyze"), request))

    assert cached_results["analysis"]["scale_meters"] == 60
    assert cached_results["analysis"]["scale_meters"] == analysis_service.job_service.update_job.await_args_list[-1].kwargs["result"]["scale_meters"]
    validate.assert_called_once_with(feature_image, aoi, 60)


def test_training_extraction_uses_analysis_scale(monkeypatch):
    sampled_scales = []
    cache = {"_feature_image": object(), "scale_meters": 60}

    monkeypatch.setattr(analysis_service, "get_result", lambda _: cache)
    monkeypatch.setattr(
        analysis_service,
        "sample_training_features",
        lambda image, features, scale, limit: sampled_scales.append(scale) or [1, 2],
    )
    monkeypatch.setattr(analysis_service, "get_feature_array", lambda _: (np.zeros((2, 1)), np.zeros(2)))
    monkeypatch.setattr(analysis_service, "class_sample_report", lambda _: {})
    monkeypatch.setattr(analysis_service, "store_result", lambda *_: None)
    monkeypatch.setattr(analysis_service.job_service, "update_job", AsyncMock())

    import asyncio
    asyncio.run(analysis_service.run_extract_training(
        Job("training", "extract_training"), "analysis", []
    ))

    assert sampled_scales == [60]


def test_classification_uses_analysis_scale_and_area_per_pixel(monkeypatch):
    scales = []
    feature_image = Mock()
    feature = {
        "properties": {name: 1.0 for name in FEATURE_BANDS},
        "geometry": {"type": "Point", "coordinates": [73.8, 18.5]},
    }
    feature["properties"]["NDVI"] = 0.6
    sample_result = Mock()
    sample_result.getInfo.return_value = {"features": [feature]}

    def sample(**kwargs):
        scales.append(kwargs["scale"])
        return sample_result

    feature_image.sample.side_effect = sample
    model = SimpleNamespace(
        predict=lambda _: np.array([0]),
        brinjal_probability=lambda _: np.array([0.9]),
        confidence_level=lambda *args, **kwargs: "high",
    )
    scaler = SimpleNamespace(transform=lambda values: values)
    caches = {
        "analysis": {
            "_feature_image": feature_image,
            "_aoi": object(),
            "scale_meters": 60,
            "date_from": "2025-01-01",
            "date_to": "2025-01-02",
        },
        "model": {"_model": model, "_scaler": scaler},
    }
    stored = {}
    monkeypatch.setattr(analysis_service, "get_result", lambda key: caches.get(key))
    monkeypatch.setattr(analysis_service, "store_result", lambda key, value: stored.update({key: value}))
    monkeypatch.setattr(analysis_service.job_service, "update_job", AsyncMock())

    request = ClassifyRequest(analyze_job_id="analysis", model_id="model")

    import asyncio
    asyncio.run(analysis_service.run_classify(Job("classify", "classify"), request))

    assert scales == [60]
    update_calls = analysis_service.job_service.update_job.await_args_list
    completed_result = next(
        call.kwargs["result"]
        for call in reversed(update_calls)
        if call.kwargs.get("status") == analysis_service.JobStatus.COMPLETED
    )
    stats = completed_result["statistics"]
    assert stats["scale_meters"] == 60
    assert stats["total_area_ha"] == 0.36
    assert stats["predicted_brinjal_ha"] == 0.36

    async def completed_job(_):
        return SimpleNamespace()

    monkeypatch.setattr(routes_results.job_service, "get_job", completed_job)
    monkeypatch.setattr(routes_results, "get_result", lambda key: stored.get(key))
    layer = asyncio.run(routes_results.get_probability_layer("classify"))
    assert layer["points"] == [{"latitude": 18.5, "longitude": 73.8, "probability": 0.9}]


def test_low_ndvi_class_mask_keeps_random_forest_probability(monkeypatch):
    feature = {
        "properties": {name: 1.0 for name in FEATURE_BANDS},
        "geometry": {"type": "Point", "coordinates": [73.8, 18.5]},
    }
    feature["properties"]["NDVI"] = 0.1
    sample = Mock()
    sample.getInfo.return_value = {"features": [feature]}
    feature_image = Mock()
    feature_image.sample.return_value = sample
    stored = {}
    caches = {
        "analysis": {"_feature_image": feature_image, "_aoi": object(), "scale_meters": 10},
        "model": {
            "_model": SimpleNamespace(
                predict=lambda _: np.array([0]),
                brinjal_probability=lambda _: np.array([0.83]),
                confidence_level=lambda *args, **kwargs: "high",
            ),
            "_scaler": SimpleNamespace(transform=lambda values: values),
        },
    }
    monkeypatch.setattr(analysis_service, "get_result", lambda key: caches.get(key))
    monkeypatch.setattr(analysis_service, "store_result", lambda key, value: stored.update({key: value}))
    monkeypatch.setattr(analysis_service.job_service, "update_job", AsyncMock())

    import asyncio
    asyncio.run(analysis_service.run_classify(
        Job("low-ndvi-classify", "classify"),
        ClassifyRequest(analyze_job_id="analysis", model_id="model"),
    ))

    prediction = stored["low-ndvi-classify"]["_predictions"][0]
    assert prediction["predicted_class"] == "low_vegetation"
    assert prediction["brinjal_probability"] == 0.83
