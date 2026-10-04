import pytest
from pydantic import ValidationError
from pathlib import Path

from app.earth_engine.feature_extraction import ALPHAEARTH_FEATURE_BANDS, FEATURE_BANDS, feature_names_for
from app.models.schemas import AOIRequest, StateDiscoveryRequest
from app.ml.random_forest import BrinjalRandomForest
from app.services import state_discovery_service as discovery
from app.services.analysis_service import training_label_source
from app.geospatial.vector import parse_training_geojson
from app.api import routes_state_discovery


def request(**overrides):
    values = {
        "state": "Andhra Pradesh",
        "date_from": "2023-10-01",
        "date_to": "2024-02-28",
        "cloud_threshold": 20,
        "ndvi_threshold": 0.25,
        "alphaearth_enabled": False,
        "model_id": "model-1",
    }
    values.update(overrides)
    return StateDiscoveryRequest.model_validate(values)


def feature(area=0.82, probability=0.914, centroid=(80.123456, 16.654321)):
    return {
        "geometry": {"type": "Polygon", "coordinates": [[[80, 16], [81, 16], [81, 17], [80, 16]]]},
        "properties": {"area_ha": area, "centroid": list(centroid), "NDVI_mean": 0.7, "candidate_class": 1},
    }


def test_state_discovery_accepts_state_without_user_coordinates():
    parsed = request()
    assert parsed.state == "Andhra Pradesh"
    assert not hasattr(parsed, "latitude")
    assert not hasattr(parsed, "radius_km")


def test_state_discovery_rejects_blank_or_bad_state_and_dates():
    with pytest.raises(ValidationError):
        request(state="  ")
    with pytest.raises(ValidationError):
        request(date_from="2024-02-29", date_to="2024-02-28")


def test_valid_state_is_resolved_from_gaul_names(monkeypatch):
    monkeypatch.setattr(discovery, "_state_names", ["Andhra Pradesh", "Maharashtra"])
    monkeypatch.setattr(discovery, "_state_boundary_names", {
        "Andhra Pradesh": ["Andhra Pradesh"], "Maharashtra": ["Maharashtra"],
    })
    assert discovery.canonical_state_name("andhra pradesh") == "Andhra Pradesh"
    assert discovery.boundary_names_for_state("Andhra Pradesh") == ["Andhra Pradesh"]
    with pytest.raises(ValueError, match="Unsupported Indian state"):
        discovery.canonical_state_name("Atlantis")


def test_backend_selector_list_contains_28_states_and_8_union_territories():
    gaul_names = list(discovery.INDIA_ADMIN_UNITS)
    mapped = discovery.map_gaul_state_names(gaul_names)
    labels = list(mapped)
    assert len(labels[:28]) == 28
    assert len(labels[28:]) == 8
    assert labels == list(discovery.INDIA_ADMIN_UNITS)
    assert "Andhra Pradesh" in labels


def test_gaul_aliases_keep_user_facing_names_clean():
    mapped = discovery.map_gaul_state_names([
        "Andhra Pradesh", "Orissa", "Uttaranchal", "NCT of Delhi",
        "Pondicherry", "Dadra & Nagar Haveli", "Daman & Diu",
        "Andaman & Nicobar Islands",
    ])
    assert mapped["Odisha"] == ["Orissa"]
    assert mapped["Uttarakhand"] == ["Uttaranchal"]
    assert mapped["Delhi"] == ["NCT of Delhi"]
    assert mapped["Puducherry"] == ["Pondicherry"]
    assert mapped["Dadra and Nagar Haveli and Daman and Diu"] == ["Dadra & Nagar Haveli", "Daman & Diu"]
    assert mapped["Andaman and Nicobar Islands"] == ["Andaman & Nicobar Islands"]


def test_states_endpoint_returns_india_and_authoritative_options(monkeypatch):
    monkeypatch.setattr(routes_state_discovery.EEClient, "is_ready", lambda: True)
    monkeypatch.setattr(routes_state_discovery, "available_indian_states", lambda: list(discovery.INDIA_ADMIN_UNITS))
    import asyncio
    result = asyncio.run(routes_state_discovery.list_discovery_states())
    assert result["country"] == "India"
    assert len(result["states"]) == 36
    assert result["states"][0] == "Andhra Pradesh"


def test_post_state_discovery_endpoint_still_queues_a_job(monkeypatch):
    from fastapi import BackgroundTasks
    from types import SimpleNamespace
    import asyncio

    model = BrinjalRandomForest()
    model.feature_names = list(FEATURE_BANDS)
    monkeypatch.setattr(routes_state_discovery.EEClient, "is_ready", lambda: True)
    monkeypatch.setattr(routes_state_discovery, "canonical_state_name", lambda name: name)
    monkeypatch.setattr(routes_state_discovery, "get_result", lambda _: {"_model": model, "_scaler": object()})
    bg = BackgroundTasks()
    response = asyncio.run(routes_state_discovery.start_state_discovery(
        request(), bg,
    ))
    assert response.status.value == "pending"
    assert response.message.startswith("State discovery queued for Andhra Pradesh")
    assert bg.tasks


def test_state_discovery_still_requires_an_available_trained_model(monkeypatch):
    from fastapi import BackgroundTasks, HTTPException
    import asyncio

    monkeypatch.setattr(routes_state_discovery.EEClient, "is_ready", lambda: True)
    monkeypatch.setattr(routes_state_discovery, "canonical_state_name", lambda name: name)
    monkeypatch.setattr(routes_state_discovery, "get_result", lambda _: None)
    with pytest.raises(HTTPException) as error:
        asyncio.run(routes_state_discovery.start_state_discovery(request(), BackgroundTasks()))
    assert error.value.status_code == 404
    assert "trained model" in error.value.detail


def test_state_discovery_rejects_alphaearth_schema_mismatch_clearly(monkeypatch):
    from fastapi import BackgroundTasks, HTTPException
    import asyncio

    model = BrinjalRandomForest(alphaearth_enabled=True)
    model.feature_names = feature_names_for(True)
    monkeypatch.setattr(routes_state_discovery.EEClient, "is_ready", lambda: True)
    monkeypatch.setattr(routes_state_discovery, "canonical_state_name", lambda name: name)
    monkeypatch.setattr(routes_state_discovery, "get_result", lambda _: {"_model": model, "_scaler": object()})
    with pytest.raises(HTTPException) as error:
        asyncio.run(routes_state_discovery.start_state_discovery(request(alphaearth_enabled=False), BackgroundTasks()))
    assert error.value.status_code == 422
    assert "AlphaEarth setting" in error.value.detail


def test_analysis_portal_training_prompt_status_focus_and_dates_are_wired():
    analysis_page = Path(__file__).parents[2] / "frontend" / "src" / "pages" / "AnalysisPage.tsx"
    source = analysis_page.read_text(encoding="utf-8")
    assert "preloadedLoc?.date_from || '2025-01-01'" in source
    assert "preloadedLoc?.date_to || '2025-03-31'" in source
    assert "A trained Random Forest model is required. Train the model in Detailed AOI workflow first." in source
    assert "Go to Model Training" in source
    assert "detailedAoiRef.current?.setAttribute('open', '')" in source
    assert "trainingSectionRef.current?.scrollIntoView" in source
    assert "state.modelId ? 'Ready' : 'Not trained'" in source
    assert "setModelResult(job_id, metrics.model_id, metrics)" in source
    assert "discoverySectionRef.current?.scrollIntoView" in source
    assert '<details ref={detailedAoiRef}' in source
    assert "checked={alphaearthMlEnabled}" in source
    assert "useState(false);" in source


def test_state_boundary_lookup_uses_gaul_internal_names(monkeypatch):
    monkeypatch.setattr(discovery, "_state_names", list(discovery.INDIA_ADMIN_UNITS))
    monkeypatch.setattr(discovery, "_state_boundary_names", {
        "Andhra Pradesh": ["Andhra Pradesh"], "Odisha": ["Orissa"],
    })

    class Geometry:
        pass

    class Features:
        def filter(self, *_): return self
        def size(self): return SimpleSize()
        def geometry(self): return geometry

    class SimpleSize:
        def getInfo(self): return 1

    geometry = Geometry()
    monkeypatch.setattr(discovery.ee, "FeatureCollection", lambda _: Features())
    monkeypatch.setattr(discovery.ee.Filter, "eq", lambda *_: object())
    monkeypatch.setattr(discovery.ee.Filter, "inList", lambda *_: object())
    assert discovery.state_boundary_geometry("Odisha") is geometry


def test_legacy_point_aoi_and_001_km_radius_remain_supported():
    old_request = AOIRequest.model_validate({
        "latitude": 16.5, "longitude": 80.5, "radius_km": 0.01,
    })
    assert old_request.radius_km == 0.01


def test_sentinel_and_alphaearth_schemas_are_ordered_and_unchanged():
    assert feature_names_for(False) == list(FEATURE_BANDS)
    assert feature_names_for(True) == list(FEATURE_BANDS) + ALPHAEARTH_FEATURE_BANDS
    assert ALPHAEARTH_FEATURE_BANDS == [f"AE_{index:02d}" for index in range(1, 65)]


def test_old_and_alphaearth_models_must_match_request_schema():
    legacy = BrinjalRandomForest()
    del legacy.alphaearth_enabled
    legacy.feature_names = list(FEATURE_BANDS)
    assert discovery._valid_model_schema(legacy, False) == list(FEATURE_BANDS)
    alpha_model = BrinjalRandomForest(alphaearth_enabled=True)
    alpha_model.feature_names = feature_names_for(True)
    assert discovery._valid_model_schema(alpha_model, True) == feature_names_for(True)
    with pytest.raises(ValueError, match="does not match"):
        discovery._valid_model_schema(alpha_model, False)


def test_candidate_field_schema_has_generated_centroid_and_geometry():
    item = discovery._candidate_field_record(1, feature(), 0.914, "high", "2024-02-28", 0.05)
    assert item is not None
    assert item["field_id"] == "BR-000001"
    assert item["latitude"] == pytest.approx(16.654321)
    assert item["longitude"] == pytest.approx(80.123456)
    assert item["area_hectares"] == pytest.approx(0.82)
    assert item["brinjal_probability"] == pytest.approx(0.914)
    assert item["crop_class"] == "brinjal"
    assert item["geometry"] == feature()["geometry"]


def test_state_bounds_are_returned_from_boundary_geometry():
    expected = {"type": "Polygon", "coordinates": [[[80, 15], [82, 15], [82, 18], [80, 15]]]}

    class Bounds:
        def getInfo(self):
            return expected

    class Geometry:
        def bounds(self, **_):
            return Bounds()

    assert discovery._state_bounds(Geometry()) == expected


def test_incomplete_region_features_are_skipped_without_imputation():
    props = {name: 0.2 for name in feature_names_for(False)}
    assert discovery._get_feature_properties(props, feature_names_for(False)) is not None
    props.pop(FEATURE_BANDS[0])
    assert discovery._get_feature_properties(props, feature_names_for(False)) is None


@pytest.mark.parametrize("area", [0.01, 0.049])
def test_candidate_field_respects_existing_minimum_area(area):
    assert discovery._candidate_field_record(1, feature(area=area), 0.91, "high", "2024-02-28", 0.05) is None


@pytest.mark.parametrize("probability", [-0.1, 1.01, float("nan")])
def test_candidate_field_rejects_invalid_probability(probability):
    assert discovery._candidate_field_record(1, feature(), probability, "low", "2024-02-28", 0.05) is None


def test_candidate_field_confidence_classes_are_preserved():
    for confidence in ("high", "medium", "low"):
        record = discovery._candidate_field_record(1, feature(), 0.4, confidence, "2024-02-28", 0.05)
        assert record["confidence"] == confidence


def test_same_candidate_records_can_serve_farms_and_probability_points():
    record = discovery._candidate_field_record(1, feature(), 0.914, "high", "2024-02-28", 0.05)
    farms = [record]
    map_records = farms
    probability_records = [
        {"latitude": item["latitude"], "longitude": item["longitude"], "brinjal_probability": item["brinjal_probability"]}
        for item in map_records
    ]
    assert farms[0]["field_id"] == map_records[0]["field_id"]
    assert probability_records[0]["latitude"] == farms[0]["latitude"]
    assert probability_records[0]["brinjal_probability"] == farms[0]["brinjal_probability"]


def test_empty_results_have_no_candidate_statistics_to_fabricate():
    fields = []
    average = sum(row["brinjal_probability"] for row in fields) / len(fields) if fields else None
    assert average is None
    assert fields == []


def test_unsupported_crop_indices_are_not_in_feature_schema():
    all_features = set(feature_names_for(False) + feature_names_for(True))
    assert not {"MDRRL", "LCA", "PRI", "CAI"}.intersection(all_features)


@pytest.mark.parametrize("values", [
    (0.40, 0.20, 0.30, 0.25),
    (0.68, 0.55, 0.65, 0.55),
])
def test_healthy_candidate_rule_includes_exact_thresholds(values):
    assert discovery._candidate_screen_class(*values) == discovery.SCREEN_CLASS_HEALTHY_CANDIDATE


@pytest.mark.parametrize("values", [
    (0.25, 0.10, 0.20, 0.15),
    (0.39, 0.19, 0.29, 0.24),
])
def test_young_or_stressed_candidate_rule(values):
    assert discovery._candidate_screen_class(*values) == discovery.SCREEN_CLASS_YOUNG_STRESSED_CANDIDATE


def test_ndvi_below_point_20_is_non_field_even_when_other_indices_are_high():
    assert discovery._candidate_screen_class(0.1999, 0.9, 0.9, 0.9) == discovery.SCREEN_CLASS_NON_FIELD


def test_candidate_rule_has_inclusive_boundaries_and_ignores_ndwi_ndbi():
    assert discovery._candidate_screen_class(0.40, 0.20, 0.30, 0.25) == 1
    assert discovery._candidate_screen_class(0.25, 0.10, 0.20, 0.15) == 2
    assert set(discovery.SPECTRAL_CANDIDATE_RULES["healthy"]) == {"NDVI", "EVI", "SAVI", "NDRE"}
    assert set(discovery.SPECTRAL_CANDIDATE_RULES["young_stressed"]) == {"NDVI", "EVI", "SAVI", "NDRE"}


def test_candidate_screen_class_image_reads_only_the_four_gate_indices():
    class Expression:
        def gte(self, _): return self
        def And(self, _): return self
        def multiply(self, _): return self
        def toInt8(self): return self
        def where(self, *_): return self
        def rename(self, _): return self

    class Image:
        def __init__(self): self.selected = []
        def select(self, name):
            self.selected.append(name)
            return Expression()

    image = Image()
    discovery._candidate_screen_class_image(image)
    assert set(image.selected) == {"NDVI", "EVI", "SAVI", "NDRE"}
    assert "NDWI" not in image.selected and "NDBI" not in image.selected


def test_screening_pseudo_labels_are_separate_from_ground_truth():
    record = discovery._candidate_field_record(
        1, feature(), 0.91, "high", "2024-02-28", 0.05,
        {"NDVI": 0.5, "EVI": 0.4, "SAVI": 0.5, "NDRE": 0.4},
    )
    assert record["label_source"] == "spectral_pseudo_label"
    assert record["label_type"] == "candidate/pseudo-label"
    assert record["screening_class"] == 1
    assert record["prediction_source"] == "random_forest"
    assert record["crop_class"] == "brinjal"
    assert training_label_source("uploaded") == "ground_truth"
    assert training_label_source("demo") == "demonstration_data"


def test_spectral_candidate_geojson_is_blocked_from_ground_truth_training():
    import json
    candidate_geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
            "properties": {"crop_class": "brinjal", "label_source": "spectral_pseudo_label"},
        }],
    }
    with pytest.raises(ValueError, match="Only manually verified ground_truth"):
        parse_training_geojson(json.dumps(candidate_geojson))


def test_verified_training_geojson_is_marked_as_ground_truth():
    import json
    truth_geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
            "properties": {"crop_class": "brinjal", "label_source": "ground_truth"},
        }],
    }
    parsed = parse_training_geojson(json.dumps(truth_geojson))
    assert parsed[0]["label_source"] == "ground_truth"


def test_candidate_records_retain_all_real_model_feature_values():
    names = feature_names_for(False)
    values = {name: float(index + 0.125) for index, name in enumerate(names)}
    record = discovery._candidate_field_record(
        1, feature(), 0.91, "high", "2024-02-28", 0.05, values,
    )
    assert record["feature_values"] == values
    for required in ("NDVI", "EVI", "SAVI", "NDRE", "NDWI", "NDBI", "B2", "B8", "NDVI_mean", "EVI_stdDev", "NDRE_stdDev"):
        assert required in record["feature_values"]


def test_lca_mdrrl_mdlca_remain_disabled_without_confirmed_definitions():
    record = discovery._candidate_field_record(1, feature(), 0.91, "high", "2024-02-28", 0.05)
    assert not {"LCA", "MDRRL", "MDLCA"}.intersection(FEATURE_BANDS)
    assert all(metric is None for key in ("LCA", "MDRRL")
               for metric in record["extended_index_statistics"][key].values()
               if metric != record["extended_index_statistics"][key]["status"])
    assert "disabled" in record["mdlca_status"]


def test_random_forest_remains_separate_final_classifier():
    import inspect
    source = inspect.getsource(discovery.run_state_discovery)
    assert "predicted = model.predict(X_scaled)" in source
    assert "probabilities = model.brinjal_probability(X_scaled)" in source
    assert '"prediction_source": "random_forest"' in inspect.getsource(discovery._candidate_field_record)


def test_state_discovery_retains_its_dynamic_world_candidates_and_model_gate():
    import inspect
    source = inspect.getsource(discovery._candidate_regions)
    assert "DYNAMIC_WORLD" in source
    assert "label_30m.eq(4)" in source
    assert "screening_class.gt(0)" in source
