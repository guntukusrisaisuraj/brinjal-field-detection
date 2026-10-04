from __future__ import annotations

from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.api.routes_landsat import LandsatAnalyzeRequest
from app.services import landsat_service


@pytest.mark.parametrize("bad", ["2025-02-29", "2024-13-01", "2024-2-01", "not-a-date"])
def test_landsat_rejects_invalid_calendar_dates(bad):
    with pytest.raises(ValidationError):
        LandsatAnalyzeRequest.model_validate({
            "aoi": {"latitude": 18.5, "longitude": 73.8},
            "date_from": bad,
            "date_to": "2025-03-01",
        })


@pytest.mark.parametrize("start,end", [("2025-01-02", "2025-01-01"), ("2025-01-01", "2025-01-01")])
def test_landsat_requires_start_before_end(start, end):
    with pytest.raises(ValidationError, match="date_from must be earlier than date_to"):
        LandsatAnalyzeRequest.model_validate({
            "aoi": {"latitude": 18.5, "longitude": 73.8},
            "date_from": start,
            "date_to": end,
        })


def test_collection_merges_landsat_8_and_9_with_cloud_filter_and_inclusive_dates(monkeypatch):
    calls = []

    class Collection:
        def __init__(self, collection_id):
            self.collection_id = collection_id

        def filterBounds(self, aoi):
            calls.append((self.collection_id, "bounds", aoi))
            return self

        def filterDate(self, start, end):
            calls.append((self.collection_id, "dates", start, end))
            return self

        def filter(self, filter_obj):
            calls.append((self.collection_id, "filter", filter_obj))
            return self

        def map(self, fn):
            calls.append((self.collection_id, "map", fn))
            return self

        def merge(self, other):
            calls.append((self.collection_id, "merge", other.collection_id))
            return (self, other)

    monkeypatch.setattr(landsat_service.ee, "ImageCollection", Collection)
    cloud_filter = object()
    monkeypatch.setattr(landsat_service.ee.Filter, "lte", Mock(return_value=cloud_filter))
    merged = landsat_service.load_landsat_collection(object(), "2024-02-28", "2024-02-29", 17)

    assert [item.collection_id for item in merged] == [
        landsat_service.L8_COLLECTION,
        landsat_service.L9_COLLECTION,
    ]
    assert [(c[0], c[2], c[3]) for c in calls if c[1] == "dates"] == [
        (landsat_service.L8_COLLECTION, "2024-02-28", "2024-03-01"),
        (landsat_service.L9_COLLECTION, "2024-02-28", "2024-03-01"),
    ]
    assert len([c for c in calls if c[1] == "map"]) == 2


def test_qa_mask_uses_documented_collection_2_condition_bits(monkeypatch):
    class QA:
        def __init__(self):
            self.masks = []

        def bitwiseAnd(self, mask):
            self.masks.append(mask)
            return self

        def eq(self, value):
            assert value == 0
            return self

        def And(self, other):
            return self

    class Image:
        def __init__(self):
            self.qa = QA()

        def select(self, band):
            return self.qa if band == "QA_PIXEL" else self

        def multiply(self, value):
            return self

        def add(self, value):
            return self

        def addBands(self, *_args, **_kwargs):
            return self

        def updateMask(self, mask):
            return self

    image = Image()
    landsat_service._mask_landsat_clouds(image)
    assert image.qa.masks == [1 << bit for bit in (0, 1, 2, 3, 4, 5)]


def test_analysis_keeps_missing_statistics_null_and_returns_bounds_and_tiles(monkeypatch):
    class Info:
        def __init__(self, result):
            self.result = result

        def getInfo(self):
            return self.result

    class Visualization:
        def __init__(self, map_id):
            self.map_id = map_id

        def getMapId(self):
            return {"mapid": self.map_id, "token": "tile-token"}

    class Composite:
        def __init__(self):
            self.reductions = 0
            self.visualizations = 0

        def select(self, bands):
            return self

        def clip(self, aoi):
            return self

        def reduceRegion(self, **kwargs):
            self.reductions += 1
            if self.reductions == 1:
                return Info({"NDVI": None, "EVI": 0.2, "NDWI": None, "SAVI": 0.1, "NDBI": None})
            return Info({
                "SR_B4_min": 0.01, "SR_B3_min": 0.02, "SR_B2_min": 0.03,
                "SR_B4_max": 0.25, "SR_B3_max": 0.26, "SR_B2_max": 0.27,
            })

        def visualize(self, **kwargs):
            self.visualizations += 1
            return Visualization(f"map-{self.visualizations}")

    class Collection:
        def size(self):
            return Info(2)

        def aggregate_array(self, prop):
            assert prop == "SPACECRAFT_ID"
            return self

        def distinct(self):
            return self

        def getInfo(self):
            return ["LANDSAT_8", "LANDSAT_9"]

        def map(self, fn):
            return self

        def median(self):
            return Composite()

    polygon = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
    aoi = Mock()
    aoi.bounds.return_value = Info(polygon)
    collection = Collection()
    monkeypatch.setattr(landsat_service, "load_landsat_collection", lambda *_: collection)
    monkeypatch.setattr(landsat_service.ee.Reducer, "mean", Mock(return_value=object()))
    monkeypatch.setattr(landsat_service.ee.Reducer, "minMax", Mock(return_value=object()))

    result = landsat_service.analyze_landsat(aoi, "2024-01-01", "2024-02-01")

    assert result["index_stats"] == {"NDVI": None, "EVI": 0.2, "NDWI": None, "SAVI": 0.1, "NDBI": None}
    assert result["aoi_bounds"] == polygon
    assert result["sensor"] == "LC08+LC09"
    assert result["tile_urls"]["ndvi_url"]
    assert result["tile_urls"]["true_color_url"]
