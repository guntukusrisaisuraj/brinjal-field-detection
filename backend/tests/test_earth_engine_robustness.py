from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from app.earth_engine import feature_extraction, sentinel2
from app.earth_engine.feature_extraction import FEATURE_BANDS
from app.models.schemas import AnalyzeRequest, JobStatus
from app.services import analysis_service
from app.services.job_service import Job


class FakeCollection:
    def __init__(self, count=1, bands=None):
        self.count = count
        self.bands = bands or ["SCL", "B2"]
        self.map_callback = None

    def filterBounds(self, _):
        return self

    def filterDate(self, *_):
        return self

    def filter(self, *_):
        return self

    def size(self):
        return Mock(getInfo=Mock(return_value=self.count))

    def first(self):
        return Mock(bandNames=Mock(return_value=Mock(getInfo=Mock(return_value=self.bands))))

    def map(self, callback):
        self.map_callback = callback
        return self


def test_collection_without_qa60_uses_scl_masking(monkeypatch):
    collection = FakeCollection(bands=["SCL", "B2"])
    monkeypatch.setattr(sentinel2.ee, "ImageCollection", Mock(return_value=collection))
    monkeypatch.setattr(sentinel2.ee.Filter, "lte", Mock(return_value=object()))
    calls = []
    monkeypatch.setattr(
        sentinel2,
        "mask_clouds",
        lambda image, use_qa60=True: calls.append(use_qa60) or image,
    )

    loaded = sentinel2.load_sentinel2_collection(object(), "2025-01-01", "2025-01-02")
    loaded.map_callback(object())

    assert calls == [False]


def test_qa60_mask_falls_back_to_scl_where_qa_is_masked(monkeypatch):
    class Expression:
        def __init__(self):
            self.unmask_calls = 0

        def bitwiseAnd(self, _):
            return self

        def eq(self, _):
            return self

        def And(self, _):
            return self

        def Or(self, _):
            return self

        def Not(self):
            return self

        def mask(self):
            return self

        def reduce(self, _):
            return self

        def unmask(self, _):
            self.unmask_calls += 1
            return self

    class Image:
        def __init__(self):
            self.qa = Expression()
            self.scl = Expression()
            self.selected = []

        def select(self, bands):
            self.selected.append(bands)
            if bands == "QA60":
                return self.qa
            if bands == "SCL":
                return self.scl
            return self

        def updateMask(self, _):
            return self

        def multiply(self, _):
            return self

        def addBands(self, *_args, **_kwargs):
            return self

    monkeypatch.setattr(sentinel2.ee.Reducer, "min", Mock(return_value=object()))
    image = Image()

    sentinel2.mask_clouds(image, use_qa60=True)

    assert image.qa.unmask_calls == 2
    assert "SCL" in image.selected
    assert "QA60" in image.selected


def test_feature_validation_is_bounded_and_uses_requested_scale(monkeypatch):
    missing_band = FEATURE_BANDS[-1]
    counts = {band: 5 for band in FEATURE_BANDS}
    counts[missing_band] = 0
    region_reduction = Mock(getInfo=Mock(return_value=counts))
    image = Mock()
    image.select.return_value.reduceRegion.return_value = region_reduction
    monkeypatch.setattr(feature_extraction.ee.Reducer, "count", Mock(return_value=object()))

    with pytest.raises(ValueError, match=missing_band):
        feature_extraction.validate_feature_image(image, object(), scale_meters=60)

    kwargs = image.select.return_value.reduceRegion.call_args.kwargs
    assert kwargs["scale"] == 60
    assert kwargs["maxPixels"] == 100_000
    assert kwargs["bestEffort"] is True


def test_feature_validation_identifies_no_pixels_after_masking(monkeypatch):
    image = Mock()
    image.select.return_value.reduceRegion.return_value.getInfo.return_value = {
        band: 0 for band in FEATURE_BANDS
    }
    monkeypatch.setattr(feature_extraction.ee.Reducer, "count", Mock(return_value=object()))

    with pytest.raises(ValueError, match="after cloud masking"):
        feature_extraction.validate_feature_image(image, object(), scale_meters=30)


def test_feature_validation_wraps_earth_engine_evaluation_errors(monkeypatch):
    image = Mock()
    image.select.return_value.reduceRegion.return_value.getInfo.side_effect = RuntimeError(
        "computation limit"
    )
    monkeypatch.setattr(feature_extraction.ee.Reducer, "count", Mock(return_value=object()))

    with pytest.raises(RuntimeError, match="bounded to 100,000 pixels") as error:
        feature_extraction.validate_feature_image(image, object(), scale_meters=60)

    assert "computation limit" in str(error.value)


def test_tile_url_fallback_raises_instead_of_returning_empty_url(monkeypatch):
    class Visualization:
        def getMapId(self):
            raise RuntimeError("primary tile request failed")

        def serialize(self):
            return "image-graph"

    class Image:
        def select(self, _):
            return self

        def visualize(self, **_):
            return Visualization()

        def gte(self, _):
            return self

        def rename(self, _):
            return self

    monkeypatch.setattr(
        feature_extraction.ee.data,
        "getMapId",
        Mock(side_effect=RuntimeError("fallback tile request failed")),
    )

    with pytest.raises(RuntimeError, match="failed to create an NDVI visualization tile URL"):
        feature_extraction.get_ndvi_tile_url(Image(), object())


def test_analyze_keeps_zero_image_check_and_fails_job_usefully(monkeypatch):
    updates = AsyncMock()
    monkeypatch.setattr(analysis_service.EEClient, "is_ready", lambda: True)
    monkeypatch.setattr(analysis_service, "aoi_from_request", lambda _: object())
    monkeypatch.setattr(analysis_service, "load_sentinel2_collection", lambda *_: object())
    monkeypatch.setattr(analysis_service, "collection_info", lambda _: {"image_count": 0})
    build = Mock()
    monkeypatch.setattr(analysis_service, "build_feature_image", build)
    monkeypatch.setattr(analysis_service.job_service, "update_job", updates)
    request = AnalyzeRequest(
        aoi={"latitude": 18.5, "longitude": 73.8},
        date_from="2025-01-01",
        date_to="2025-01-02",
    )

    asyncio.run(analysis_service.run_analyze(Job("empty", "analyze"), request))

    build.assert_not_called()
    failure = updates.await_args_list[-1].kwargs
    assert failure["status"] == JobStatus.FAILED
    assert "No Sentinel-2 images found" in failure["error"]


def test_analyze_reports_tile_generation_failure(monkeypatch):
    updates = AsyncMock()
    monkeypatch.setattr(analysis_service.EEClient, "is_ready", lambda: True)
    monkeypatch.setattr(analysis_service, "aoi_from_request", lambda _: object())
    monkeypatch.setattr(analysis_service, "load_sentinel2_collection", lambda *_: object())
    monkeypatch.setattr(analysis_service, "collection_info", lambda _: {"image_count": 1})
    monkeypatch.setattr(analysis_service, "build_feature_image", lambda *_: object())
    monkeypatch.setattr(analysis_service, "validate_feature_image", lambda *_: None)
    monkeypatch.setattr(analysis_service, "aoi_index_means", lambda *_: {})
    monkeypatch.setattr(
        analysis_service, "get_ndvi_tile_url", Mock(side_effect=RuntimeError("map service error"))
    )
    monkeypatch.setattr(analysis_service.job_service, "update_job", updates)
    request = AnalyzeRequest(
        aoi={"latitude": 18.5, "longitude": 73.8},
        date_from="2025-01-01",
        date_to="2025-01-02",
    )

    asyncio.run(analysis_service.run_analyze(Job("tile-failure", "analyze"), request))

    failure = updates.await_args_list[-1].kwargs
    assert failure["status"] == JobStatus.FAILED
    assert "could not generate NDVI map tiles" in failure["error"]
    assert "map service error" in failure["error"]
