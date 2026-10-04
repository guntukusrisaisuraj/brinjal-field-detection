"""
Pydantic schemas for request / response validation.
"""
from __future__ import annotations

from enum import Enum
from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from shapely.geometry import shape


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class CropClass(str, Enum):
    BRINJAL = "brinjal"
    OTHER_CROP = "other_crop"
    BARE_SOIL = "bare_soil"
    BUILT_UP = "built_up"
    WATER = "water"
    OTHER_VEGETATION = "other_vegetation"


class ConfidenceLevel(str, Enum):
    HIGH = "high"        # >= 0.75
    MEDIUM = "medium"    # 0.50 – 0.74
    LOW = "low"          # < 0.50


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class LayerType(str, Enum):
    NDVI = "ndvi"
    LOW_NDVI_MASK = "low_ndvi_mask"
    VEGETATION_MASK = "vegetation_mask"
    BRINJAL_PROBABILITY = "brinjal_probability"
    BRINJAL_PREDICTION = "brinjal_prediction"
    OTHER_CROP = "other_crop"
    COMPOSITE = "composite"


# ---------------------------------------------------------------------------
# Shared geometry helpers
# ---------------------------------------------------------------------------

class GeoJSONGeometry(BaseModel):
    type: str
    coordinates: Any


class AOIRequest(BaseModel):
    """Area of Interest specification (exactly one form must be provided)."""
    state: Optional[str] = Field(None, description="Indian state name")
    district: Optional[str] = Field(None, description="District name within state")
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    radius_km: Optional[float] = Field(None, ge=0.01, le=500,
                                        description="Radius around lat/lon in km")
    geojson: Optional[Dict[str, Any]] = Field(
        None, description="Custom GeoJSON FeatureCollection or Feature")

    @field_validator("geojson")
    @classmethod
    def validate_geojson(cls, v: Optional[Dict]) -> Optional[Dict]:
        if v is not None:
            kind = v.get("type")
            if kind == "FeatureCollection":
                features = v.get("features")
                if not isinstance(features, list) or not features:
                    raise ValueError("geojson FeatureCollection must contain at least one feature")
                geometries = []
                for index, feature in enumerate(features):
                    if not isinstance(feature, dict) or feature.get("type") != "Feature":
                        raise ValueError(f"geojson features[{index}] must be a GeoJSON Feature")
                    geometries.append(feature.get("geometry"))
            elif kind == "Feature":
                geometries = [v.get("geometry")]
            elif kind in ("Polygon", "MultiPolygon"):
                geometries = [v]
            else:
                raise ValueError("geojson must be a GeoJSON Feature, FeatureCollection, "
                                 "Polygon, or MultiPolygon")

            for index, geometry in enumerate(geometries):
                try:
                    if not isinstance(geometry, dict) or geometry.get("type") not in (
                        "Polygon", "MultiPolygon"
                    ):
                        raise ValueError("geometry must be a Polygon or MultiPolygon")
                    parsed = shape(geometry)
                    if parsed.is_empty or not parsed.is_valid:
                        raise ValueError("geometry is empty or invalid")
                except Exception as exc:
                    prefix = (f"geojson features[{index}].geometry" if kind == "FeatureCollection"
                              else "geojson geometry")
                    raise ValueError(f"{prefix} is invalid: {exc}") from exc
        return v

    @field_validator("state", "district")
    @classmethod
    def validate_admin_name(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("state and district names must not be blank")
        return value

    @model_validator(mode="after")
    def validate_aoi_choice(self) -> "AOIRequest":
        has_lat = self.latitude is not None
        has_lon = self.longitude is not None
        if has_lat != has_lon:
            raise ValueError("latitude and longitude must be provided together")
        if self.district is not None and self.state is None:
            raise ValueError("state is required when district is provided")

        has_point = has_lat and has_lon
        has_state = self.state is not None
        has_geojson = self.geojson is not None
        if "radius_km" in self.model_fields_set and not has_point:
            raise ValueError("radius_km may only be provided with latitude and longitude")
        if sum((has_point, has_state, has_geojson)) != 1:
            raise ValueError("provide exactly one AOI form: geojson, state/district, or latitude/longitude")
        return self


# ---------------------------------------------------------------------------
# Analysis / NDVI
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    aoi: AOIRequest
    date_from: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$",
                           description="Start date YYYY-MM-DD")
    date_to: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$",
                         description="End date YYYY-MM-DD")
    cloud_threshold: float = Field(20.0, ge=0, le=100,
                                   description="Maximum cloud cover percentage")
    ndvi_threshold: float = Field(0.25, ge=0.0, le=1.0,
                                  description="Low-NDVI mask threshold")
    scale_meters: int = Field(30, ge=10, le=100,
                              description="GEE export scale in metres")

    @model_validator(mode="after")
    def validate_date_range(self) -> "AnalyzeRequest":
        _validate_date_range(self.date_from, self.date_to)
        return self


class NDVIRequest(BaseModel):
    aoi: AOIRequest
    date_from: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_to: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    cloud_threshold: float = Field(20.0, ge=0, le=100)
    ndvi_threshold: float = Field(0.25, ge=0.0, le=1.0)
    scale_meters: int = Field(30, ge=10, le=100)

    @model_validator(mode="after")
    def validate_date_range(self) -> "NDVIRequest":
        _validate_date_range(self.date_from, self.date_to)
        return self


def _validate_date_range(date_from: str, date_to: str) -> None:
    """Require real ISO calendar dates and a non-reversed inclusive range."""
    try:
        start = date.fromisoformat(date_from)
    except ValueError as exc:
        raise ValueError("date_from must be a real date in YYYY-MM-DD format") from exc
    try:
        end = date.fromisoformat(date_to)
    except ValueError as exc:
        raise ValueError("date_to must be a real date in YYYY-MM-DD format") from exc
    if start.isoformat() != date_from or end.isoformat() != date_to:
        raise ValueError("dates must use YYYY-MM-DD format")
    if end < start:
        raise ValueError("date_to must be on or after date_from")


# ---------------------------------------------------------------------------
# Training data
# ---------------------------------------------------------------------------

class TrainingFeature(BaseModel):
    """A single training polygon with class label."""
    geometry: GeoJSONGeometry
    crop_class: CropClass
    label: Optional[str] = None


class TrainingDataRequest(BaseModel):
    job_id: str = Field(..., description="Analyze job ID to extract features from")
    features: List[TrainingFeature] = Field(
        ..., min_length=1, description="Training polygons with class labels")

    @field_validator("features")
    @classmethod
    def at_least_two_classes(cls, v: List[TrainingFeature]) -> List[TrainingFeature]:
        classes = {f.crop_class for f in v}
        if len(classes) < 2:
            raise ValueError("Training data must contain at least 2 distinct classes")
        return v


# ---------------------------------------------------------------------------
# Model training
# ---------------------------------------------------------------------------

class TrainRequest(BaseModel):
    analyze_job_id: str
    training_job_id: str
    n_estimators: int = Field(200, ge=10, le=2000)
    max_depth: Optional[int] = Field(None, ge=1, le=100)
    min_samples_split: int = Field(5, ge=2, le=50)
    test_size: float = Field(0.25, ge=0.1, le=0.5,
                             description="Fraction for validation")
    random_state: int = Field(42)
    alphaearth_enabled: bool = False


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

class ClassifyRequest(BaseModel):
    analyze_job_id: str
    model_id: str
    confidence_high_threshold: float = Field(0.75, ge=0, le=1)
    confidence_medium_threshold: float = Field(0.50, ge=0, le=1)
    min_field_area_ha: float = Field(0.05, ge=0.001, le=100,
                                     description="Minimum mapping unit in hectares")
    ndvi_threshold: float = Field(0.25, ge=0, le=1)


class StateDiscoveryRequest(BaseModel):
    """State-wide candidate discovery; coordinates are generated outputs."""
    state: str = Field(..., min_length=2, max_length=100)
    date_from: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_to: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    cloud_threshold: float = Field(20.0, ge=0, le=100)
    ndvi_threshold: float = Field(0.25, ge=0, le=1)
    alphaearth_enabled: bool = False
    model_id: str = Field(..., min_length=1)
    min_field_area_ha: float = Field(0.05, ge=0.001, le=100)

    @field_validator("state", "model_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @model_validator(mode="after")
    def validate_state_discovery_dates(self) -> "StateDiscoveryRequest":
        _validate_date_range(self.date_from, self.date_to)
        return self


# ---------------------------------------------------------------------------
# Job / Results
# ---------------------------------------------------------------------------

class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str
    created_at: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str
    progress: int = Field(0, ge=0, le=100, description="Percentage complete")
    created_at: str
    updated_at: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

class AreaStatistics(BaseModel):
    total_area_ha: float
    total_area_km2: float
    vegetated_area_ha: float
    vegetated_area_pct: float
    low_ndvi_area_ha: float
    low_ndvi_area_pct: float
    predicted_brinjal_ha: float
    predicted_brinjal_pct: float
    predicted_other_crop_ha: float
    num_brinjal_fields: int
    avg_brinjal_confidence: float
    date_from: str
    date_to: str
    cloud_threshold: float
    ndvi_threshold: float


# ---------------------------------------------------------------------------
# Model Metrics
# ---------------------------------------------------------------------------

class ClassMetrics(BaseModel):
    crop_class: str
    precision: float
    recall: float
    f1_score: float
    support: int


class ModelMetrics(BaseModel):
    model_id: str
    model_type: str = "Random Forest"
    n_estimators: int
    overall_accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    n_training_samples: int
    n_validation_samples: int
    class_metrics: List[ClassMetrics]
    confusion_matrix: List[List[int]]
    class_names: List[str]
    feature_importances: Dict[str, float]
    trained_at: str


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class ExportFormat(str, Enum):
    CSV = "csv"
    GEOJSON = "geojson"
    REPORT = "report"


class ExportRequest(BaseModel):
    classify_job_id: str
    format: ExportFormat = ExportFormat.GEOJSON


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    gee_authenticated: bool
    version: str
    message: str
