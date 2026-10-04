import asyncio
from types import SimpleNamespace

from app.api import routes_results


def test_probability_layer_uses_stored_probabilities_and_computes_bounds(monkeypatch):
    records = [
        {"latitude": 18.5, "longitude": 73.8, "brinjal_probability": 0.91},
        {"latitude": 18.6, "longitude": 73.9, "brinjal_probability": 0.27},
        {"latitude": 0, "longitude": 0, "brinjal_probability": float("nan")},
    ]
    async def get_job(_):
        return SimpleNamespace()
    monkeypatch.setattr(routes_results.job_service, "get_job", get_job)
    monkeypatch.setattr(routes_results, "get_result", lambda _: {"_predictions": records})

    result = asyncio.run(routes_results.get_probability_layer("classify-id"))

    assert result["layer_type"] == "brinjal_probability"
    assert result["source"] == "random_forest_prediction_records"
    assert result["points"] == [
        {"latitude": 18.5, "longitude": 73.8, "probability": 0.91},
        {"latitude": 18.6, "longitude": 73.9, "probability": 0.27},
    ]
    assert result["bounds"] == {"south": 18.5, "west": 73.8, "north": 18.6, "east": 73.9}


def test_probability_layer_returns_empty_layer_without_filling_missing_pixels(monkeypatch):
    async def get_job(_):
        return SimpleNamespace()
    monkeypatch.setattr(routes_results.job_service, "get_job", get_job)
    monkeypatch.setattr(routes_results, "get_result", lambda _: {"_predictions": []})

    result = asyncio.run(routes_results.get_probability_layer("empty-classify-id"))

    assert result["points"] == []
    assert result["count"] == 0
    assert result["bounds"] is None
