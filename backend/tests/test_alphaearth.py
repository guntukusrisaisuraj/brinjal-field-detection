from __future__ import annotations

from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.api.routes_satellite import AlphaEarthRequest, AlphaEarthResponse
from app.services import alphaearth_service


POLYGON = {
    "type": "Polygon",
    "coordinates": [[[73.8, 18.5], [73.81, 18.5], [73.81, 18.51], [73.8, 18.5]]],
}


@pytest.mark.parametrize(
    "aoi",
    [
        {"latitude": 18.5, "longitude": 73.8, "radius_km": 0.01},
        {"geojson": POLYGON},
    ],
)
def test_alphaearth_accepts_supported_aoi_forms(aoi):
    request = AlphaEarthRequest.model_validate({
        "aoi": aoi,
        "date_from": "2023-10-01",
        "date_to": "2024-02-28",
    })
    assert request.aoi


@pytest.mark.parametrize("aoi", [{}, {"latitude": 18.5}, {"latitude": 18.5, "longitude": 73.8, "radius_km": 0.009}, {"geojson": {"type": "Point", "coordinates": [1, 2]}}])
def test_alphaearth_rejects_invalid_aoi(aoi):
    with pytest.raises(ValidationError):
        AlphaEarthRequest.model_validate({
            "aoi": aoi,
            "date_from": "2023-10-01",
            "date_to": "2024-02-28",
        })


@pytest.mark.parametrize(
    ("start", "end"),
    [("2024-02-30", "2024-03-01"), ("2024-03-01", "2024-02-29")],
)
def test_alphaearth_rejects_invalid_or_reversed_dates(start, end):
    with pytest.raises(ValidationError):
        AlphaEarthRequest.model_validate({
            "aoi": {"latitude": 18.5, "longitude": 73.8, "radius_km": 0.01},
            "date_from": start,
            "date_to": end,
        })


def test_alphaearth_response_schema_describes_annual_embedding_without_fake_metrics():
    response = AlphaEarthResponse.model_validate({
        "accessible": True,
        "dataset": alphaearth_service.ALPHA_EARTH_COLLECTION,
        "source": "Google Satellite Embedding",
        "resolution_m": 10,
        "embedding_dims": 64,
        "year": 2024,
        "annual_period_start": "2024-01-01",
        "annual_period_end": "2025-01-01",
        "requested_date_from": "2023-10-01",
        "requested_date_to": "2024-02-28",
        "date_selection": "Annual embedding selected by the year containing date_to; the image summarizes that full calendar year.",
        "tile_url": None,
        "visualization_label": "AlphaEarth Embedding RGB (axes A01, A16, A09)",
        "visualization_available": False,
        "visualization_message": "Not available",
        "aoi_bounds": None,
        "n_images": 0,
        "n_embedding_bands": 0,
        "band_names": [],
        "error": "No embedding available",
    })
    serialized = response.model_dump()
    assert serialized["tile_url"] is None
    assert serialized["aoi_bounds"] is None
    assert "embedding_mean_mag" not in serialized
    assert serialized["dataset"] == "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"


def test_service_returns_unavailable_without_fabricated_result_when_year_has_no_images(monkeypatch):
    class Info:
        def getInfo(self):
            return 0

    class Collection:
        def filterDate(self, start, end):
            assert (start, end) == ("2025-01-01", "2026-01-01")
            return self

        def filterBounds(self, aoi):
            return self

        def size(self):
            return Info()

    monkeypatch.setattr(alphaearth_service.ee, "ImageCollection", lambda collection: Collection())
    result = alphaearth_service.get_alphaearth_info(
        Mock(), 2025, "2024-10-01", "2025-02-28"
    )
    assert result["accessible"] is False
    assert result["tile_url"] is None
    assert result["n_images"] == 0
    assert "embedding_mean_mag" not in result
    assert "No AlphaEarth annual embedding" in result["error"]


def test_service_filters_year_clips_embedding_and_generates_documented_rgb_tile(monkeypatch):
    band_names = [f"A{i:02d}" for i in range(64)]
    polygon = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}

    class Info:
        def __init__(self, value):
            self.value = value

        def getInfo(self):
            return self.value

    class Tile:
        def getMapId(self):
            return {"mapid": "real-map-id", "token": "real-token"}

    class Image:
        clipped = False

        def bandNames(self):
            return Info(band_names)

        def clip(self, aoi):
            self.clipped = True
            return self

        def select(self, names):
            assert names == band_names
            return self

        def reduceRegion(self, **kwargs):
            return Info({name: 10 for name in band_names})

        def visualize(self, **kwargs):
            assert kwargs == {"bands": ["A01", "A16", "A09"], "min": -0.3, "max": 0.3}
            return Tile()

    image = Image()

    class Collection:
        def filterDate(self, start, end):
            assert (start, end) == ("2024-01-01", "2025-01-01")
            return self

        def filterBounds(self, aoi):
            return self

        def size(self):
            return Info(1)

        def mosaic(self):
            return image

    aoi = Mock()
    aoi.bounds.return_value = Info(polygon)
    monkeypatch.setattr(alphaearth_service.ee, "ImageCollection", lambda collection: Collection())
    monkeypatch.setattr(alphaearth_service.ee.Reducer, "count", Mock(return_value=object()))

    result = alphaearth_service.get_alphaearth_info(aoi, 2024, "2023-10-01", "2024-02-28")

    assert image.clipped
    assert result["accessible"] is True
    assert result["year"] == 2024
    assert result["aoi_bounds"] == polygon
    assert result["visualization_available"] is True
    assert result["tile_url"].startswith("https://earthengine.googleapis.com/map/real-map-id/")
    assert "embedding_mean_mag" not in result
