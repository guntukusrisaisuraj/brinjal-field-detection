"""
Geospatial vector utilities:
  - GeoJSON validation
  - Training polygon parsing
  - Classification result polygonization
  - Field-level aggregation / minimum-mapping-unit filter
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import numpy as np
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from app.utils.logger import logger


# ---------------------------------------------------------------------------
# GeoJSON validation
# ---------------------------------------------------------------------------

ALLOWED_GEOM_TYPES = {
    "Point", "MultiPoint",
    "LineString", "MultiLineString",
    "Polygon", "MultiPolygon",
    "GeometryCollection",
}


def validate_geojson(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate a GeoJSON dict.

    Raises
    ------
    ValueError
        If the structure is invalid.
    """
    if not isinstance(data, dict):
        raise ValueError("GeoJSON must be a JSON object (dict)")

    gtype = data.get("type")

    if gtype == "FeatureCollection":
        features = data.get("features", [])
        if not isinstance(features, list):
            raise ValueError("FeatureCollection.features must be a list")
        for i, feat in enumerate(features):
            if feat.get("type") != "Feature":
                raise ValueError(f"features[{i}].type must be 'Feature'")
            geom = feat.get("geometry", {})
            if geom and geom.get("type") not in ALLOWED_GEOM_TYPES:
                raise ValueError(
                    f"features[{i}].geometry.type "
                    f"'{geom.get('type')}' is not a valid GeoJSON geometry type"
                )
    elif gtype == "Feature":
        geom = data.get("geometry", {})
        if geom and geom.get("type") not in ALLOWED_GEOM_TYPES:
            raise ValueError(
                f"geometry.type '{geom.get('type')}' is not a valid GeoJSON geometry type"
            )
    elif gtype in ALLOWED_GEOM_TYPES:
        pass  # bare geometry is fine
    else:
        raise ValueError(
            f"GeoJSON type '{gtype}' is not supported. "
            "Must be Feature, FeatureCollection, or a geometry type."
        )

    # Try constructing shapely geometry to catch coordinate errors
    try:
        _to_shapely(data)
    except Exception as exc:
        raise ValueError(f"Invalid GeoJSON coordinates: {exc}") from exc

    return data


def _to_shapely(geojson: Dict[str, Any]):
    """Convert GeoJSON dict to shapely geometry."""
    gtype = geojson.get("type")
    if gtype == "FeatureCollection":
        geoms = [shape(f["geometry"]) for f in geojson["features"] if f.get("geometry")]
        return unary_union(geoms)
    elif gtype == "Feature":
        return shape(geojson["geometry"])
    else:
        return shape(geojson)


# ---------------------------------------------------------------------------
# Training polygon parser
# ---------------------------------------------------------------------------

def parse_training_geojson(geojson_str: str) -> List[Dict[str, Any]]:
    """
    Parse an uploaded training GeoJSON string.

    Expected format:
    {
      "type": "FeatureCollection",
      "features": [
        {
          "type": "Feature",
          "geometry": { ... polygon ... },
          "properties": { "crop_class": "brinjal" }
        }, ...
      ]
    }

    Returns list of dicts with 'geometry' and 'crop_class'.
    """
    data = json.loads(geojson_str)
    validate_geojson(data)

    features = []
    if data["type"] == "FeatureCollection":
        raw_features = data["features"]
    elif data["type"] == "Feature":
        raw_features = [data]
    else:
        raise ValueError("Training GeoJSON must be a Feature or FeatureCollection")

    for feat in raw_features:
        props = feat.get("properties") or {}
        supplied_label_source = props.get("label_source")
        if supplied_label_source and supplied_label_source != "ground_truth":
            raise ValueError(
                "Only manually verified ground_truth polygons can be used for model training. "
                "Candidate/pseudo-label or model-predicted polygons must be field-verified and relabelled ground_truth first."
            )
        crop_class = props.get("crop_class") or props.get("class") or props.get("label")
        if not crop_class:
            logger.warning("[Vector] Skipping feature without 'crop_class' property")
            continue
        geom = feat.get("geometry")
        if not geom:
            logger.warning("[Vector] Skipping feature without geometry")
            continue
        features.append({
            "geometry": geom,
            "crop_class": str(crop_class).lower().strip(),
            "label_source": "ground_truth",
        })

    if not features:
        raise ValueError(
            "No valid training features found. "
            "Each feature must have a 'crop_class' property and a geometry."
        )

    return features


# ---------------------------------------------------------------------------
# Minimum Mapping Unit filter
# ---------------------------------------------------------------------------

def apply_minimum_mapping_unit(
    features: List[Dict[str, Any]],
    min_area_ha: float = 0.05,
) -> List[Dict[str, Any]]:
    """
    Remove polygons smaller than min_area_ha hectares.

    Parameters
    ----------
    features : list of GeoJSON Feature dicts
    min_area_ha : float

    Returns
    -------
    list of filtered GeoJSON Feature dicts
    """
    min_area_m2 = min_area_ha * 10_000
    filtered = []
    removed = 0
    for feat in features:
        try:
            geom = shape(feat.get("geometry") or feat)
            if geom.area >= min_area_m2:
                filtered.append(feat)
            else:
                removed += 1
        except Exception:
            filtered.append(feat)  # keep if geometry check fails

    logger.info(
        f"[Vector] MMU filter: kept {len(filtered)}, removed {removed} "
        f"(< {min_area_ha} ha)"
    )
    return filtered


def compute_area_ha(geojson_feature: Dict[str, Any]) -> float:
    """Compute polygon area in hectares (WGS84 approximation)."""
    try:
        geom = shape(geojson_feature.get("geometry") or geojson_feature)
        # For lat/lon geometries, 1 degree ≈ 111_319 m at equator
        # Use a simple lat-dependent correction
        bounds = geom.bounds
        lat_center = (bounds[1] + bounds[3]) / 2
        cos_lat = np.cos(np.radians(lat_center))
        area_deg2 = geom.area
        area_m2 = area_deg2 * (111_319 ** 2) * cos_lat
        return area_m2 / 10_000
    except Exception:
        return 0.0
