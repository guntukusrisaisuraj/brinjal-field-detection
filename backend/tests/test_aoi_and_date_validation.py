from __future__ import annotations

from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.earth_engine import sentinel2
from app.models.schemas import AOIRequest, AnalyzeRequest, NDVIRequest


POLYGON = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
}


@pytest.mark.parametrize(
    "aoi",
    [
        {"geojson": POLYGON},
        {"geojson": {"type": "Feature", "geometry": POLYGON, "properties": {}}},
        {"geojson": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": POLYGON, "properties": {}}
        ]}},
        {"state": "Maharashtra"},
        {"state": "Maharashtra", "district": "Pune"},
        {"latitude": 18.5, "longitude": 73.8},
        {"latitude": 18.5, "longitude": 73.8, "radius_km": 5},
    ],
)
def test_accepts_supported_aoi_forms(aoi):
    assert AOIRequest.model_validate(aoi)


def test_accepts_minimum_point_radius_of_001_km():
    request = AOIRequest.model_validate({
        "latitude": 18.5,
        "longitude": 73.8,
        "radius_km": 0.01,
    })
    assert request.radius_km == 0.01


@pytest.mark.parametrize("radius", [0, -0.01])
def test_rejects_nonpositive_point_radius(radius):
    with pytest.raises(ValidationError):
        AOIRequest.model_validate({
            "latitude": 18.5,
            "longitude": 73.8,
            "radius_km": radius,
        })


@pytest.mark.parametrize(
    ("aoi", "message"),
    [
        ({}, "exactly one AOI form"),
        ({"latitude": 1}, "latitude and longitude"),
        ({"longitude": 1}, "latitude and longitude"),
        ({"district": "Pune"}, "state is required"),
        ({"latitude": 1, "longitude": 2, "state": "Maharashtra"}, "exactly one AOI form"),
        ({"geojson": POLYGON, "state": "Maharashtra"}, "exactly one AOI form"),
        ({"radius_km": 3}, "radius_km may only be provided"),
        ({"geojson": {"type": "FeatureCollection", "features": []}}, "at least one feature"),
        ({"geojson": {"type": "Polygon", "coordinates": [[1, 2]]}}, "invalid"),
        ({"geojson": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}, "must be a GeoJSON"),
    ],
)
def test_rejects_missing_conflicting_or_malformed_aoi(aoi, message):
    with pytest.raises(ValidationError, match=message):
        AOIRequest.model_validate(aoi)


def test_feature_collection_is_converted_to_earth_engine_geometry(monkeypatch):
    geometry = Mock(name="geometry")
    collection = Mock()
    collection.geometry.return_value = geometry
    feature_collection = Mock(return_value=collection)
    monkeypatch.setattr(sentinel2.ee, "FeatureCollection", feature_collection)
    geojson = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": POLYGON, "properties": {}}
    ]}

    assert sentinel2.aoi_from_request({"geojson": geojson}) is geometry
    feature_collection.assert_called_once_with(geojson)
    collection.geometry.assert_called_once_with()


def test_aoi_helper_fails_closed_without_fallback():
    with pytest.raises(ValueError, match="exactly one AOI form"):
        sentinel2.aoi_from_request({})


@pytest.mark.parametrize("request_model", [AnalyzeRequest, NDVIRequest])
@pytest.mark.parametrize("bad_date", ["2025-02-29", "2024-13-01", "2024-04-31"])
def test_rejects_impossible_calendar_dates(request_model, bad_date):
    with pytest.raises(ValidationError):
        request_model.model_validate({
            "aoi": {"latitude": 18.5, "longitude": 73.8},
            "date_from": bad_date,
            "date_to": "2025-03-01",
        })


@pytest.mark.parametrize("request_model", [AnalyzeRequest, NDVIRequest])
def test_rejects_reversed_date_range(request_model):
    with pytest.raises(ValidationError, match="date_to must be on or after date_from"):
        request_model.model_validate({
            "aoi": {"latitude": 18.5, "longitude": 73.8},
            "date_from": "2025-01-02",
            "date_to": "2025-01-01",
        })


def test_filter_date_treats_api_end_date_as_inclusive(monkeypatch):
    collection = Mock()
    collection.filterBounds.return_value = collection
    collection.filterDate.return_value = collection
    collection.filter.return_value = collection
    collection.map.return_value = collection
    collection.size.return_value.getInfo.return_value = 1
    collection.first.return_value.bandNames.return_value.getInfo.return_value = ["QA60"]
    monkeypatch.setattr(sentinel2.ee, "ImageCollection", Mock(return_value=collection))
    monkeypatch.setattr(sentinel2.ee.Filter, "lte", Mock(return_value=object()))

    sentinel2.load_sentinel2_collection(Mock(), "2024-02-28", "2024-02-29")

    collection.filterDate.assert_called_once_with("2024-02-28", "2024-03-01")
