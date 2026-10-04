import numpy as np
import pandas as pd
import pytest

from app.earth_engine.feature_extraction import (
    ALPHAEARTH_FEATURE_BANDS,
    FEATURE_BANDS,
    feature_names_for,
    get_feature_array,
)
from app.ml.random_forest import BrinjalRandomForest
from app.services import alphaearth_service


def test_alphaearth_feature_names_are_exact_neutral_dimensions():
    assert ALPHAEARTH_FEATURE_BANDS == [f"AE_{i:02d}" for i in range(1, 65)]
    assert all(not name.startswith(("B", "ND", "EVI", "SAVI")) for name in ALPHAEARTH_FEATURE_BANDS)


def test_alphaearth_feature_values_are_numeric_and_preserve_sentinel_features():
    names = feature_names_for(True)
    row = {name: float(index) for index, name in enumerate(names)}
    row.update(crop_class="brinjal", class_id=0)
    frame = pd.DataFrame([row])
    frame.attrs["feature_names"] = names
    X, y = get_feature_array(frame)
    assert names[:len(FEATURE_BANDS)] == list(FEATURE_BANDS)
    assert names[-64:] == ALPHAEARTH_FEATURE_BANDS
    assert X.shape == (1, len(FEATURE_BANDS) + 64)
    assert np.issubdtype(X.dtype, np.number)
    assert y.tolist() == [0]


def test_training_and_classification_schema_share_canonical_order():
    assert feature_names_for(True) == list(FEATURE_BANDS) + ALPHAEARTH_FEATURE_BANDS
    assert feature_names_for(False) == list(FEATURE_BANDS)


def test_alphaearth_model_records_collection_dimension_and_names():
    model = BrinjalRandomForest(alphaearth_enabled=True)
    X = np.arange(12 * (len(FEATURE_BANDS) + 64), dtype=np.float32).reshape(12, -1)
    y = np.array([0, 1] * 6)
    names = feature_names_for(True)
    model.train(X, y, names)
    assert model.alphaearth_enabled is True
    assert model.alphaearth_collection == "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"
    assert model.alphaearth_dimensions == 64
    assert model.alphaearth_feature_names == ALPHAEARTH_FEATURE_BANDS
    assert model.feature_names == names


def test_legacy_sentinel_only_model_schema_remains_supported():
    model = BrinjalRandomForest()
    del model.alphaearth_enabled  # models serialized before this field existed
    assert getattr(model, "alphaearth_enabled", False) is False
    assert feature_names_for(getattr(model, "alphaearth_enabled", False)) == list(FEATURE_BANDS)


def test_alphaearth_missing_annual_data_fails_with_clear_coverage_error(monkeypatch):
    class Collection:
        def filterDate(self, *_): return self
        def filterBounds(self, *_): return self
        def size(self): return self
        def getInfo(self): return 0

    monkeypatch.setattr(alphaearth_service.ee, "ImageCollection", lambda _: Collection())
    with pytest.raises(ValueError, match="No AlphaEarth annual embedding"):
        alphaearth_service.build_alphaearth_feature_image(object(), 2024)


def test_alphaearth_schema_never_assigns_wavelength_semantics():
    assert len(ALPHAEARTH_FEATURE_BANDS) == 64
    assert ALPHAEARTH_FEATURE_BANDS[0] == "AE_01"
    assert ALPHAEARTH_FEATURE_BANDS[-1] == "AE_64"
    assert not any(name in {"B1", "B2", "B3", "NDVI", "EVI", "NDWI", "SAVI", "NDBI"}
                   for name in ALPHAEARTH_FEATURE_BANDS)
