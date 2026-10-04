"""
Landsat service – loads Landsat 8/9 Surface Reflectance imagery via GEE
and computes the same vegetation indices as the Sentinel-2 pipeline.

Collections used:
  - LANDSAT/LC09/C02/T1_L2  (Landsat 9, ~2022-present)
  - LANDSAT/LC08/C02/T1_L2  (Landsat 8, ~2013-2022)

Bands used:
  SR_B2=Blue, SR_B3=Green, SR_B4=Red, SR_B5=NIR, SR_B6=SWIR1, SR_B7=SWIR2
  QA_PIXEL for cloud masking

All processing runs server-side in Google Earth Engine.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict

import ee
from app.utils.logger import logger


# ---------------------------------------------------------------------------
# Collection IDs
# ---------------------------------------------------------------------------
L9_COLLECTION = "LANDSAT/LC09/C02/T1_L2"
L8_COLLECTION = "LANDSAT/LC08/C02/T1_L2"

# Scale factors for Landsat Collection 2 L2 products
LANDSAT_SCALE = 0.0000275
LANDSAT_OFFSET = -0.2


# ---------------------------------------------------------------------------
# Cloud masking
# ---------------------------------------------------------------------------

QA_PIXEL_BITS = {
    "fill": 0,
    "dilated_cloud": 1,
    "cirrus": 2,
    "cloud": 3,
    "cloud_shadow": 4,
    "snow": 5,
}


def _mask_landsat_clouds(image: ee.Image) -> ee.Image:
    """
    Mask cloud and cloud-shadow pixels using QA_PIXEL.
    Landsat 8/9 Collection 2 QA_PIXEL bits 0-5 flag fill, dilated cloud,
    cirrus, cloud, cloud shadow, and snow, respectively (USGS definitions).
    """
    qa = image.select("QA_PIXEL")
    mask = qa.bitwiseAnd(1 << QA_PIXEL_BITS["fill"]).eq(0)
    for condition in ("dilated_cloud", "cirrus", "cloud", "cloud_shadow", "snow"):
        mask = mask.And(qa.bitwiseAnd(1 << QA_PIXEL_BITS[condition]).eq(0))

    # Apply scale factors to surface reflectance bands
    optical = (
        image.select("SR_B.+")
        .multiply(LANDSAT_SCALE)
        .add(LANDSAT_OFFSET)
    )
    return image.addBands(optical, overwrite=True).updateMask(mask)


# ---------------------------------------------------------------------------
# Collection loading
# ---------------------------------------------------------------------------

def load_landsat_collection(
    aoi: ee.Geometry,
    date_from: str,
    date_to: str,
    cloud_threshold: float = 20.0,
) -> ee.ImageCollection:
    """
    Load a unified, cloud-filtered Landsat 8 and 9 collection.
    """
    logger.info(f"[Landsat] Loading Landsat 8/9 {date_from} → {date_to}")
    # Earth Engine's filterDate end is exclusive; accept inclusive API dates.
    inclusive_end = (date.fromisoformat(date_to) + timedelta(days=1)).isoformat()
    collections = []
    for collection_id in (L8_COLLECTION, L9_COLLECTION):
        collection = (
            ee.ImageCollection(collection_id)
            .filterBounds(aoi)
            .filterDate(date_from, inclusive_end)
            .filter(ee.Filter.lte("CLOUD_COVER", cloud_threshold))
            .map(_mask_landsat_clouds)
        )
        collections.append(collection)
    return collections[0].merge(collections[1])


# ---------------------------------------------------------------------------
# Index calculation (Landsat band names)
# ---------------------------------------------------------------------------

def _add_landsat_indices(image: ee.Image) -> ee.Image:
    """
    Compute vegetation indices using Landsat band names.
    SR_B4=Red, SR_B5=NIR, SR_B6=SWIR1, SR_B3=Green, SR_B2=Blue.
    """
    # NDVI
    ndvi = image.normalizedDifference(["SR_B5", "SR_B4"]).rename("NDVI")

    # EVI
    evi = image.expression(
        "2.5 * ((NIR - RED) / (NIR + 6.0 * RED - 7.5 * BLUE + 1.0))",
        {
            "NIR":  image.select("SR_B5"),
            "RED":  image.select("SR_B4"),
            "BLUE": image.select("SR_B2"),
        },
    ).rename("EVI")

    # NDWI
    ndwi = image.normalizedDifference(["SR_B3", "SR_B5"]).rename("NDWI")

    # SAVI (L=0.5)
    savi = image.expression(
        "((NIR - RED) / (NIR + RED + 0.5)) * 1.5",
        {
            "NIR": image.select("SR_B5"),
            "RED": image.select("SR_B4"),
        },
    ).rename("SAVI")

    # NDBI
    ndbi = image.normalizedDifference(["SR_B6", "SR_B5"]).rename("NDBI")

    return image.addBands([ndvi, evi, ndwi, savi, ndbi])


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------

def analyze_landsat(
    aoi: ee.Geometry,
    date_from: str,
    date_to: str,
    cloud_threshold: float = 20.0,
) -> Dict[str, Any]:
    """
    Full Landsat analysis for an AOI: load, composite, indices, tile URLs.

    Returns
    -------
    dict with:
      - image_count   : int
      - sensor        : str (LC08 / LC09)
      - tile_urls     : dict (ndvi_url, evi_url)
      - index_stats   : dict of mean values per index
    """
    col = load_landsat_collection(aoi, date_from, date_to, cloud_threshold)
    size = col.size().getInfo()

    if size == 0:
        raise ValueError(
            f"No Landsat images found for the AOI and date range "
            f"({date_from} → {date_to}) with cloud threshold ≤ {cloud_threshold}%."
        )

    # Identify all contributing sensors from the actual filtered collection.
    sensor_ids = col.aggregate_array("SPACECRAFT_ID").distinct().getInfo()
    sensor_ids = sorted(
        "LC09" if "LANDSAT_9" in item else "LC08"
        for item in sensor_ids
        if item in ("LANDSAT_8", "LANDSAT_9")
    )
    sensor = "+".join(sensor_ids)

    # Median composite with indices
    composite = col.map(_add_landsat_indices).median().clip(aoi)

    # Index stats
    stats = composite.select(["NDVI", "EVI", "NDWI", "SAVI", "NDBI"]).reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=aoi,
        scale=30,
        maxPixels=1e9,
    ).getInfo()

    # Per-band observed AOI range keeps RGB rendering data-driven without a
    # fixed reflectance stretch.
    rgb = composite.select(["SR_B4", "SR_B3", "SR_B2"])
    rgb_limits = rgb.reduceRegion(
        reducer=ee.Reducer.minMax(),
        geometry=aoi,
        scale=30,
        maxPixels=1e9,
    ).getInfo()
    rgb_min = [rgb_limits.get(f"{band}_min") for band in ("SR_B4", "SR_B3", "SR_B2")]
    rgb_max = [rgb_limits.get(f"{band}_max") for band in ("SR_B4", "SR_B3", "SR_B2")]
    rgb_url = ""
    if all(value is not None for value in (*rgb_min, *rgb_max)) and all(
        high > low for low, high in zip(rgb_min, rgb_max)
    ):
        rgb_vis = rgb.visualize(min=rgb_min, max=rgb_max)
        rgb_map = rgb_vis.getMapId()
        rgb_mid, rgb_token = rgb_map["mapid"], rgb_map.get("token", "")
        rgb_url = (
            f"https://earthengine.googleapis.com/map/{rgb_mid}/{{z}}/{{x}}/{{y}}?token={rgb_token}"
            if rgb_token else f"https://earthengine.googleapis.com/v1alpha/{rgb_mid}/tiles/{{z}}/{{x}}/{{y}}"
        )

    # NDVI tile URL
    ndvi_vis = composite.select("NDVI").visualize(
        min=-0.2, max=0.9,
        palette=["#d73027", "#fdae61", "#d9ef8b", "#1a9850"],
    )
    try:
        map_id = ndvi_vis.getMapId()
        mid = map_id["mapid"]
        tok = map_id.get("token", "")
        if tok:
            ndvi_url = f"https://earthengine.googleapis.com/map/{mid}/{{z}}/{{x}}/{{y}}?token={tok}"
        else:
            ndvi_url = f"https://earthengine.googleapis.com/v1alpha/{mid}/tiles/{{z}}/{{x}}/{{y}}"
    except Exception as exc:
        logger.warning(f"[Landsat] Tile URL failed: {exc}")
        ndvi_url = ""

    return {
        "image_count": size,
        "sensor": sensor,
        "date_from": date_from,
        "date_to": date_to,
        "cloud_threshold": cloud_threshold,
        "tile_urls": {"ndvi_url": ndvi_url, "true_color_url": rgb_url},
        "index_stats": {
            key: round(value, 4) if value is not None else None
            for key, value in ((key, stats.get(key)) for key in ("NDVI", "EVI", "NDWI", "SAVI", "NDBI"))
        },
        "aoi_bounds": aoi.bounds().getInfo(),
    }
