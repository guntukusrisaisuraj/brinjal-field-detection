"""
Feature extraction from Sentinel-2 imagery for ML training and classification.

Extracts the following features per pixel / sample point:
  - Raw Sentinel-2 bands: B2, B3, B4, B5, B6, B7, B8, B8A, B11, B12
  - Single-date indices: NDVI, EVI, NDWI, SAVI, NDBI, NDRE
  - Temporal NDVI stats: mean, max, min, stdDev, median, p25, p75
  - Temporal EVI stats: mean, max, stdDev
  - Temporal NDRE stats: mean, max, stdDev

All extraction runs server-side in GEE using sampleRegions / sampleRectangle.
"""
from __future__ import annotations

from typing import Any, Dict, List

import ee
import numpy as np
import pandas as pd

from app.earth_engine.ndvi import (
    add_all_indices,
    temporal_evi_stats,
    temporal_ndre_stats,
    temporal_ndvi_stats,
)
from app.earth_engine.sentinel2 import BAND_NAMES, create_median_composite
from app.utils.logger import logger

# All ML feature band names (must match extraction order)
FEATURE_BANDS = (
    BAND_NAMES  # 10 raw bands
    + ["NDVI", "EVI", "NDWI", "SAVI", "NDBI", "NDRE"]  # 6 indices
    + ["NDVI_mean", "NDVI_max", "NDVI_min", "NDVI_stdDev",
       "NDVI_median", "NDVI_p25", "NDVI_p75"]  # 7 temporal NDVI
    + ["EVI_mean", "EVI_max", "EVI_stdDev"]  # 3 temporal EVI
    + ["NDRE_mean", "NDRE_max", "NDRE_stdDev"]  # 3 temporal NDRE
)
# Total: 29 features

INDEX_BANDS = ["NDVI", "EVI", "SAVI", "NDWI", "NDRE", "NDBI"]
ALPHAEARTH_FEATURE_BANDS = [f"AE_{index:02d}" for index in range(1, 65)]


def feature_names_for(alphaearth_enabled: bool = False) -> list[str]:
    """Return the canonical ordered model columns for the selected sources."""
    return list(FEATURE_BANDS) + (ALPHAEARTH_FEATURE_BANDS if alphaearth_enabled else [])


def aoi_index_means(
    feature_image: ee.Image,
    aoi: ee.Geometry,
    scale_meters: int,
) -> Dict[str, float | None]:
    """Return actual AOI mean values for available index bands.

    Values are reduced from the same median-composite feature image used by
    analysis and are evaluated at the analysis request's scale. Missing bands
    and bands with no unmasked AOI pixels are represented as ``None``.
    """
    band_names = feature_image.bandNames().getInfo()
    available = [name for name in INDEX_BANDS if name in band_names]
    values: Dict[str, float | None] = {name: None for name in INDEX_BANDS}
    if not available:
        return values

    reduced = feature_image.select(available).reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=aoi,
        scale=scale_meters,
        maxPixels=1_000_000_000_000,
        tileScale=4,
    ).getInfo()
    for name in available:
        value = reduced.get(name) if reduced else None
        if value is not None:
            values[name] = float(value)
    return values


def validate_feature_image(
    feature_image: ee.Image,
    aoi: ee.Geometry,
    scale_meters: int,
    max_pixels: int = 100_000,
) -> None:
    """Check that all required feature bands have data using a bounded reduction."""
    try:
        counts = feature_image.select(FEATURE_BANDS).reduceRegion(
            reducer=ee.Reducer.count(),
            geometry=aoi,
            scale=scale_meters,
            maxPixels=max_pixels,
            bestEffort=True,
            tileScale=4,
        ).getInfo()
    except Exception as exc:
        raise RuntimeError(
            "Earth Engine could not validate feature data over the AOI "
            f"at {scale_meters} m resolution (bounded to {max_pixels:,} pixels). "
            "Try a smaller AOI or a coarser sampling scale. "
            f"Details: {exc}"
        ) from exc

    missing_bands = [
        band for band in FEATURE_BANDS
        if counts is None or counts.get(band) is None or counts.get(band, 0) <= 0
    ]
    if len(missing_bands) == len(FEATURE_BANDS):
        raise ValueError(
            "No usable Sentinel-2 feature pixels remain over the AOI after cloud masking. "
            "Try a wider date range or a higher cloud threshold."
        )
    if missing_bands:
        raise ValueError(
            "No valid data was found over the AOI for required feature band(s): "
            + ", ".join(missing_bands)
            + ". Try a wider date range or check cloud-free coverage."
        )


def build_feature_image(
    collection: ee.ImageCollection,
    aoi: ee.Geometry,
) -> ee.Image:
    """
    Build a multi-band feature image combining:
      - Median composite bands + indices (from the full collection period)
      - Temporal statistics

    Parameters
    ----------
    collection : ee.ImageCollection
        Cloud-masked Sentinel-2 collection.
    aoi : ee.Geometry

    Returns
    -------
    ee.Image
        Image with all feature bands. Each pixel has 29 features.
    """
    # ---- Median composite with all indices ----
    composite = create_median_composite(collection, aoi, BAND_NAMES)
    composite_with_indices = add_all_indices(composite)

    # ---- Temporal statistics ----
    ndvi_stats = temporal_ndvi_stats(collection).clip(aoi)
    evi_stats = temporal_evi_stats(collection).clip(aoi)
    ndre_stats = temporal_ndre_stats(collection).clip(aoi)

    # ---- Stack everything ----
    feature_image = (
        composite_with_indices
        .select(BAND_NAMES + ["NDVI", "EVI", "NDWI", "SAVI", "NDBI", "NDRE"])
        .addBands(ndvi_stats)
        .addBands(evi_stats)
        .addBands(ndre_stats)
    )
    return feature_image.select(FEATURE_BANDS)


def sample_training_features(
    feature_image: ee.Image,
    training_features: List[Dict[str, Any]],
    scale: int = 30,
    max_pixels_per_polygon: int = 100,
    additional_feature_image: ee.Image | None = None,
) -> pd.DataFrame:
    """
    Extract pixel features from training polygons.

    Parameters
    ----------
    feature_image : ee.Image
        Multi-band feature image from build_feature_image().
    training_features : list of dict
        Each dict has 'geometry' (GeoJSON) and 'crop_class' (str).
    scale : int
        Sampling scale in metres.
    max_pixels_per_polygon : int
        Max pixels sampled per polygon to keep within GEE limits.

    Returns
    -------
    pd.DataFrame
        One row per sampled pixel with feature columns + 'crop_class'.
    """
    class_map = {
        "brinjal": 0,
        "other_crop": 1,
        "bare_soil": 2,
        "built_up": 3,
        "water": 4,
        "other_vegetation": 5,
    }

    all_rows: List[Dict[str, Any]] = []
    feature_names = feature_names_for(additional_feature_image is not None)
    sampling_image = (
        feature_image.addBands(additional_feature_image)
        if additional_feature_image is not None else feature_image
    ).select(feature_names)

    for feat in training_features:
        geom_dict = feat["geometry"]
        crop_class = feat["crop_class"]
        class_id = class_map.get(crop_class, -1)

        try:
            ee_geom = ee.Geometry(geom_dict)
            fc = sampling_image.sample(
                region=ee_geom,
                scale=scale,
                numPixels=max_pixels_per_polygon,
                geometries=False,
                seed=42,
            )
            rows = fc.getInfo()["features"]
            for row in rows:
                props = row["properties"]
                props["crop_class"] = crop_class
                props["class_id"] = class_id
                all_rows.append(props)
        except ee.EEException as exc:
            logger.warning(f"[FeatureExtraction] Failed for class {crop_class}: {exc}")
            continue

    if not all_rows:
        raise ValueError("No training pixels could be extracted from the given polygons.")

    df = pd.DataFrame(all_rows)
    # Drop rows with any NaN feature
    df = df.dropna(subset=feature_names)
    if df.empty and additional_feature_image is not None:
        raise ValueError(
            "No training samples have complete AlphaEarth embeddings for this AOI/year. "
            "Check embedding coverage or disable AlphaEarth features to use Sentinel-2 only."
        )
    df.attrs["feature_names"] = feature_names
    logger.info(
        f"[FeatureExtraction] Extracted {len(df)} pixels "
        f"from {len(training_features)} polygons"
    )
    return df


def get_feature_array(df: pd.DataFrame):
    """Return (X, y) arrays using the supplied ordered feature columns."""
    feature_names = [name for name in df.columns if name != "crop_class" and name != "class_id"]
    # DataFrame source order is preserved, but canonical callers can attach it.
    feature_names = df.attrs.get("feature_names", feature_names)
    X = df[feature_names].values.astype(np.float32)
    y = df["class_id"].values.astype(np.int32)
    return X, y


def get_ndvi_tile_url(
    feature_image: ee.Image,
    aoi: ee.Geometry,
    ndvi_threshold: float = 0.25,
) -> Dict[str, str]:
    """
    Generate NDVI visualization tile URL for the frontend map.

    Compatible with earthengine-api >= 0.1.370 (tile_fetcher was removed).

    Returns dict with:
      - ndvi_url: continuous NDVI (red→yellow→green palette)
      - mask_url: binary low-NDVI mask (red=low, green=vegetated)
    """
    ndvi = feature_image.select("NDVI")

    # Continuous NDVI visualization
    ndvi_vis = ndvi.visualize(
        min=-0.2,
        max=0.9,
        palette=["#d73027", "#f46d43", "#fdae61", "#fee08b",
                 "#d9ef8b", "#a6d96a", "#66bd63", "#1a9850"],
    )

    # Binary mask: 0 = low vegetation, 1 = vegetated
    ndvi_mask = ndvi.gte(ndvi_threshold).rename("ndvi_mask")
    mask_vis = ndvi_mask.visualize(
        min=0,
        max=1,
        palette=["#d73027", "#1a9850"],
    )

    def _make_tile_url(vis_image: ee.Image) -> str:
        """Build a GEE tile URL compatible with all earthengine-api versions."""
        try:
            # earthengine-api >= 0.1.370: getMapId returns a plain dict
            map_id_dict = vis_image.getMapId()
            map_id = map_id_dict["mapid"]
            token = map_id_dict.get("token", "")
            if token:
                return (
                    f"https://earthengine.googleapis.com/map/{map_id}/{{z}}/{{x}}/{{y}}"
                    f"?token={token}"
                )
            return (
                f"https://earthengine.googleapis.com/v1alpha/{map_id}/tiles/{{z}}/{{x}}/{{y}}"
            )
        except Exception as exc:
            logger.warning(f"[FeatureExtraction] Tile URL fallback triggered: {exc}")
            # Last-resort: use ee.data.getTileUrl
            try:
                map_id_dict = ee.data.getMapId(
                    {"image": vis_image.serialize()}
                )
                return ee.data.getTileUrl(map_id_dict, 0, 0, 0).rsplit("/", 3)[0] + "/{z}/{x}/{y}"
            except Exception as fallback_exc:
                raise RuntimeError(
                    "Earth Engine failed to create an NDVI visualization tile URL."
                ) from fallback_exc

    ndvi_url = _make_tile_url(ndvi_vis)
    mask_url = _make_tile_url(mask_vis)

    return {"ndvi_url": ndvi_url, "mask_url": mask_url}
