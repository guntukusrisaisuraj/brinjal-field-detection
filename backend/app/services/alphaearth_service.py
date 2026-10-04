"""Google Satellite Embedding (AlphaEarth) access through Earth Engine."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict

import ee
from app.earth_engine.feature_extraction import ALPHAEARTH_FEATURE_BANDS
from app.utils.logger import logger

ALPHA_EARTH_COLLECTION = "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"
ALPHA_EARTH_DIMS = 64
VISUALIZATION_BANDS = ["A01", "A16", "A09"]
VISUALIZATION_MIN = -0.3
VISUALIZATION_MAX = 0.3


def build_alphaearth_feature_image(aoi: ee.Geometry, year: int) -> ee.Image:
    """Build the clipped, neutral-named 64-D feature image for ML sampling."""
    start, end = f"{year}-01-01", f"{year + 1}-01-01"
    try:
        collection = (
            ee.ImageCollection(ALPHA_EARTH_COLLECTION)
            .filterDate(start, end)
            .filterBounds(aoi)
        )
        count = int(collection.size().getInfo())
        if count == 0:
            raise ValueError(
                f"No AlphaEarth annual embedding is available for {year} in the AOI."
            )
        image = collection.mosaic()
        source_bands = image.bandNames().getInfo()
        if len(source_bands) != len(ALPHAEARTH_FEATURE_BANDS):
            raise ValueError(
                f"Expected 64 AlphaEarth dimensions for {year}; received {len(source_bands)}."
            )
        return image.select(source_bands).rename(ALPHAEARTH_FEATURE_BANDS).clip(aoi)
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError(
            "Could not load AlphaEarth embeddings. Confirm Google Earth Engine access "
            "and dataset allowlisting, or disable AlphaEarth features. "
            f"Details: {exc}"
        ) from exc


def get_alphaearth_info(
    aoi: ee.Geometry,
    year: int,
    requested_date_from: str,
    requested_date_to: str,
) -> Dict[str, Any]:
    """Get a real annual embedding image, display tile, and AOI metadata.

    The requested date range selects the annual period containing its end date.
    It is not a temporal filter over observations: each selected image summarizes
    one calendar year, as documented for the public collection.
    """
    period_start = date(year, 1, 1).isoformat()
    period_end = date(year + 1, 1, 1).isoformat()
    result: Dict[str, Any] = {
        "accessible": False,
        "dataset": ALPHA_EARTH_COLLECTION,
        "source": "Google Satellite Embedding",
        "resolution_m": 10,
        "embedding_dims": ALPHA_EARTH_DIMS,
        "year": year,
        "annual_period_start": period_start,
        "annual_period_end": period_end,
        "requested_date_from": requested_date_from,
        "requested_date_to": requested_date_to,
        "date_selection": "Annual embedding selected by the year containing date_to; the image summarizes that full calendar year.",
        "tile_url": None,
        "visualization_label": "AlphaEarth Embedding RGB (axes A01, A16, A09)",
        "visualization_available": False,
        "visualization_message": "Visualization is unavailable until a real embedding tile is generated.",
        "aoi_bounds": None,
        "n_images": 0,
        "n_embedding_bands": 0,
        "band_names": [],
        "error": None,
    }

    try:
        collection = (
            ee.ImageCollection(ALPHA_EARTH_COLLECTION)
            .filterDate(period_start, period_end)
            .filterBounds(aoi)
        )
        image_count = int(collection.size().getInfo())
        result["n_images"] = image_count
        if image_count == 0:
            result["error"] = (
                f"No AlphaEarth annual embedding is available for {year} in the selected AOI. "
                "Choose a date ending in a year represented by the Earth Engine collection."
            )
            return result

        # Each annual image is a spatial tile. Mosaic matching tiles then clip
        # the actual embedding bands to this request's AOI.
        image = collection.mosaic().clip(aoi)
        band_names = image.bandNames().getInfo()
        result["band_names"] = band_names
        result["n_embedding_bands"] = len(band_names)
        if len(band_names) != ALPHA_EARTH_DIMS:
            result["error"] = (
                f"Expected {ALPHA_EARTH_DIMS} AlphaEarth embedding bands, "
                f"but Earth Engine returned {len(band_names)}."
            )
            return result

        # Verify pixels are available across the embedding dimensions in the AOI.
        counts = image.select(band_names).reduceRegion(
            reducer=ee.Reducer.count(),
            geometry=aoi,
            scale=10,
            maxPixels=1e8,
        ).getInfo() or {}
        if not all(counts.get(name) is not None and counts[name] > 0 for name in band_names):
            result["error"] = f"No complete AlphaEarth embedding pixels are available in the AOI for {year}."
            return result

        if all(name in band_names for name in VISUALIZATION_BANDS):
            try:
                # This RGB axis selection and display stretch follow Google's
                # Earth Engine catalog visualization example; axes are not
                # spectral indices or independently interpretable measurements.
                vis_image = image.visualize(
                    bands=VISUALIZATION_BANDS,
                    min=VISUALIZATION_MIN,
                    max=VISUALIZATION_MAX,
                )
                map_id = vis_image.getMapId()
                mapid, token = map_id["mapid"], map_id.get("token", "")
                result["tile_url"] = (
                    f"https://earthengine.googleapis.com/map/{mapid}/{{z}}/{{x}}/{{y}}?token={token}"
                    if token
                    else f"https://earthengine.googleapis.com/v1alpha/{mapid}/tiles/{{z}}/{{x}}/{{y}}"
                )
                result["visualization_available"] = True
                result["visualization_message"] = None
            except Exception as exc:
                logger.warning(f"[AlphaEarth] Visualization tile unavailable: {exc}")
                result["visualization_message"] = f"Embedding data is available, but its map tile could not be generated: {exc}"
        else:
            result["visualization_message"] = (
                "Embedding data is available, but the documented RGB axes are missing; no tile was generated."
            )

        result["accessible"] = True
        try:
            result["aoi_bounds"] = aoi.bounds().getInfo()
        except Exception as exc:
            logger.warning(f"[AlphaEarth] AOI bounds unavailable: {exc}")
        return result
    except ee.EEException as exc:
        logger.error(f"[AlphaEarth] Earth Engine error: {exc}")
        result["error"] = (
            "Earth Engine could not access or process the AlphaEarth collection. "
            "Confirm dataset access/allowlisting and try again. " + str(exc)
        )
        return result
    except Exception as exc:
        logger.exception(f"[AlphaEarth] Unexpected error: {exc}")
        result["error"] = f"AlphaEarth processing failed: {exc}"
        return result
