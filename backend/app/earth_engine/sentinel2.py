"""
Sentinel-2 Surface Reflectance imagery utilities.

Uses:
  - COPERNICUS/S2_SR_HARMONIZED (Level-2A harmonised surface reflectance)
  - QA60 band for cloud/cloud-shadow masking
  - SCL (Scene Classification Layer) for additional masking

All processing runs server-side in Google Earth Engine.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

# pyrefly: ignore [missing-import]
import ee
from app.models.schemas import AOIRequest
from app.utils.logger import logger


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
COLLECTION_ID = "COPERNICUS/S2_SR_HARMONIZED"

BAND_NAMES = ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"]
BAND_LABELS = {
    "B2": "Blue",
    "B3": "Green",
    "B4": "Red",
    "B5": "RedEdge1",
    "B6": "RedEdge2",
    "B7": "RedEdge3",
    "B8": "NIR",
    "B8A": "NarrowNIR",
    "B11": "SWIR1",
    "B12": "SWIR2",
}

# Scale factor applied to DN values in S2 SR Harmonized
SCALE_FACTOR = 0.0001


# ---------------------------------------------------------------------------
# Cloud masking
# ---------------------------------------------------------------------------

def _mask_clouds_qa60(image: ee.Image) -> ee.Image:
    """
    Mask clouds and cirrus using the QA60 bitmask band.
    Bit 10 = opaque clouds, Bit 11 = cirrus clouds.
    """
    qa = image.select("QA60")
    cloud_bit_mask = 1 << 10
    cirrus_bit_mask = 1 << 11

    qa_clear = (
        qa.bitwiseAnd(cloud_bit_mask).eq(0)
        .And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
    ).unmask(0)
    # Where QA60 is masked/unusable, defer to the SCL mask rather than
    # masking otherwise valid SCL pixels.
    qa_valid = qa.mask().reduce(ee.Reducer.min()).unmask(0)
    mask = qa_clear.Or(qa_valid.Not())
    return image.updateMask(mask)


def _mask_clouds_scl(image: ee.Image) -> ee.Image:
    """
    Additional masking using Scene Classification Layer (SCL).
    SCL values to exclude:
      1 = Saturated/defective
      3 = Cloud shadows
      8 = Cloud medium probability
      9 = Cloud high probability
      10 = Thin cirrus
      11 = Snow / Ice (optional)
    """
    scl = image.select("SCL")
    bad_pixels = scl.eq(1).Or(scl.eq(3)).Or(scl.eq(8)).Or(scl.eq(9)).Or(scl.eq(10))
    return image.updateMask(bad_pixels.Not())


def mask_clouds(image: ee.Image, use_qa60: bool = True) -> ee.Image:
    """Apply SCL masking and QA60 masking when the collection provides it."""
    image = _mask_clouds_scl(image)
    if use_qa60:
        image = _mask_clouds_qa60(image)
    # Scale reflectance bands
    scaled = image.select(BAND_NAMES).multiply(SCALE_FACTOR)
    return image.addBands(scaled, overwrite=True)


# ---------------------------------------------------------------------------
# Collection loading
# ---------------------------------------------------------------------------

def load_sentinel2_collection(
    aoi: ee.Geometry,
    date_from: str,
    date_to: str,
    cloud_threshold: float = 20.0,
) -> ee.ImageCollection:
    """
    Load a cloud-filtered Sentinel-2 SR Harmonized collection.

    Parameters
    ----------
    aoi : ee.Geometry
        Area of interest.
    date_from : str
        Start date 'YYYY-MM-DD'.
    date_to : str
        End date 'YYYY-MM-DD'.
    cloud_threshold : float
        Maximum scene-level cloud cover percentage (0–100).

    Returns
    -------
    ee.ImageCollection
        Cloud-masked, band-scaled Sentinel-2 image collection.
    """
    logger.info(
        f"[Sentinel2] Loading collection {date_from} → {date_to}, "
        f"cloud ≤ {cloud_threshold}%"
    )

    collection = (
        ee.ImageCollection(COLLECTION_ID)
        .filterBounds(aoi)
        # The API's date_to is inclusive; Earth Engine filterDate uses an
        # exclusive end, so advance it by one day.
        .filterDate(date_from, (date.fromisoformat(date_to) + timedelta(days=1)).isoformat())
        .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", cloud_threshold))
    )

    # The harmonized collection normally has a stable band schema. Inspect
    # one image so collections without QA60 can use SCL-only masking without
    # constructing invalid QA60 selects inside the mapped function.
    try:
        if collection.size().getInfo() == 0:
            use_qa60 = False
        else:
            bands = collection.first().bandNames().getInfo()
            use_qa60 = "QA60" in bands
    except Exception as exc:
        raise RuntimeError(f"Unable to inspect Sentinel-2 collection bands: {exc}") from exc

    return collection.map(lambda image: mask_clouds(image, use_qa60=use_qa60))


def create_median_composite(
    collection: ee.ImageCollection,
    aoi: ee.Geometry,
    bands: Optional[List[str]] = None,
) -> ee.Image:
    """
    Create a cloud-free median composite clipped to the AOI.

    Parameters
    ----------
    collection : ee.ImageCollection
    aoi : ee.Geometry
    bands : list of str, optional
        Subset of bands. Defaults to BAND_NAMES.

    Returns
    -------
    ee.Image
    """
    bands = bands or BAND_NAMES
    composite = collection.select(bands).median().clip(aoi)
    return composite


def collection_info(collection: ee.ImageCollection) -> Dict[str, Any]:
    """Return metadata about the collection (image count, date range)."""
    size = collection.size().getInfo()
    if size == 0:
        return {"image_count": 0, "date_range": None}

    dates = collection.aggregate_array("system:time_start").getInfo()
    import datetime as dt
    date_strs = [
        dt.datetime.utcfromtimestamp(d / 1000).strftime("%Y-%m-%d")
        for d in sorted(dates)
    ]
    return {
        "image_count": size,
        "date_range": {"first": date_strs[0], "last": date_strs[-1]},
        "dates": date_strs,
    }


# ---------------------------------------------------------------------------
# AOI helpers
# ---------------------------------------------------------------------------

def aoi_from_request(aoi_dict: Dict[str, Any]) -> ee.Geometry:
    """
    Convert the AOI portion of an AnalyzeRequest into an ee.Geometry.

    Exactly one valid AOI form is required. Request schemas enforce this for
    API calls; this function also fails closed for direct callers.
    """
    aoi_dict = AOIRequest.model_validate(aoi_dict).model_dump()
    geojson = aoi_dict.get("geojson")
    if geojson:
        if geojson.get("type") == "FeatureCollection":
            return ee.FeatureCollection(geojson).geometry()
        return ee.Geometry(geojson.get("geometry", geojson))

    state = aoi_dict.get("state")
    district = aoi_dict.get("district")
    if state:
        return _aoi_from_india_admin(state, district)

    lat = aoi_dict.get("latitude")
    lon = aoi_dict.get("longitude")
    radius_km = aoi_dict.get("radius_km") or 10.0
    if lat is not None and lon is not None:
        return ee.Geometry.Point([lon, lat]).buffer(radius_km * 1000)

    # Fall back to entire India bounding box
    raise ValueError("provide exactly one AOI form: geojson, state/district, or latitude/longitude")


def _aoi_from_india_admin(state: str, district: Optional[str] = None) -> ee.Geometry:
    """
    Use the FAO GAUL Level-1 (state) or Level-2 (district) dataset
    to derive an AOI for Indian administrative units.
    """
    if district:
        gaul2 = ee.FeatureCollection("FAO/GAUL/2015/level2")
        filtered = gaul2.filter(
            ee.Filter.And(
                ee.Filter.eq("ADM1_NAME", state),
                ee.Filter.eq("ADM2_NAME", district),
            )
        )
        return filtered.geometry()
    else:
        gaul1 = ee.FeatureCollection("FAO/GAUL/2015/level1")
        filtered = gaul1.filter(ee.Filter.eq("ADM1_NAME", state))
        return filtered.geometry()
