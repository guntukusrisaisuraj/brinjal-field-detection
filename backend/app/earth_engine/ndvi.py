"""
Vegetation index calculation for Sentinel-2 imagery.

All calculations run server-side in Google Earth Engine.

Indices implemented:
  - NDVI  (Normalized Difference Vegetation Index)
  - EVI   (Enhanced Vegetation Index)
  - NDWI  (Normalized Difference Water Index)
  - SAVI  (Soil-Adjusted Vegetation Index)
  - NDBI  (Normalized Difference Built-up Index)
  - NDRE  (Normalized Difference Red Edge)  — uses S2 red-edge bands
"""
from __future__ import annotations

import ee

# ---------------------------------------------------------------------------
# Per-image index calculators
# ---------------------------------------------------------------------------

def add_ndvi(image: ee.Image) -> ee.Image:
    """
    NDVI = (B8 - B4) / (B8 + B4)
    NIR = B8, RED = B4
    """
    ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
    return image.addBands(ndvi)


def add_evi(image: ee.Image) -> ee.Image:
    """
    EVI = 2.5 * (NIR - RED) / (NIR + 6*RED - 7.5*BLUE + 1)
    """
    evi = image.expression(
        "2.5 * ((NIR - RED) / (NIR + 6.0 * RED - 7.5 * BLUE + 1.0))",
        {
            "NIR": image.select("B8"),
            "RED": image.select("B4"),
            "BLUE": image.select("B2"),
        },
    ).rename("EVI")
    return image.addBands(evi)


def add_ndwi(image: ee.Image) -> ee.Image:
    """
    NDWI = (B3 - B8) / (B3 + B8)
    GREEN = B3, NIR = B8
    """
    ndwi = image.normalizedDifference(["B3", "B8"]).rename("NDWI")
    return image.addBands(ndwi)


def add_savi(image: ee.Image, L: float = 0.5) -> ee.Image:
    """
    SAVI = ((NIR - RED) / (NIR + RED + L)) * (1 + L)
    """
    savi = image.expression(
        "((NIR - RED) / (NIR + RED + L)) * (1.0 + L)",
        {
            "NIR": image.select("B8"),
            "RED": image.select("B4"),
            "L": L,
        },
    ).rename("SAVI")
    return image.addBands(savi)


def add_ndbi(image: ee.Image) -> ee.Image:
    """
    NDBI = (B11 - B8) / (B11 + B8)
    SWIR1 = B11, NIR = B8
    """
    ndbi = image.normalizedDifference(["B11", "B8"]).rename("NDBI")
    return image.addBands(ndbi)


def add_ndre(image: ee.Image) -> ee.Image:
    """
    NDRE = (B8A - B5) / (B8A + B5)
    Uses Sentinel-2 red-edge bands for improved crop discrimination.
    """
    ndre = image.normalizedDifference(["B8A", "B5"]).rename("NDRE")
    return image.addBands(ndre)


def add_all_indices(image: ee.Image) -> ee.Image:
    """Add NDVI, EVI, NDWI, SAVI, NDBI, NDRE to a single image."""
    image = add_ndvi(image)
    image = add_evi(image)
    image = add_ndwi(image)
    image = add_savi(image)
    image = add_ndbi(image)
    image = add_ndre(image)
    return image


# ---------------------------------------------------------------------------
# Low-NDVI mask
# ---------------------------------------------------------------------------

def apply_low_ndvi_mask(image: ee.Image, threshold: float = 0.25) -> ee.Image:
    """
    Mask pixels where NDVI < threshold (low/no vegetation).

    IMPORTANT: This mask identifies non-vegetated areas only.
    It does NOT classify brinjal. Brinjal classification requires
    the trained Random Forest model operating on spectral + temporal features.

    Parameters
    ----------
    image : ee.Image
        Must contain an 'NDVI' band.
    threshold : float
        Pixels with NDVI < threshold are masked out.

    Returns
    -------
    ee.Image
        Image with low-NDVI pixels masked.
    """
    ndvi = image.select("NDVI")
    vegetation_mask = ndvi.gte(threshold)
    return image.updateMask(vegetation_mask).set(
        "ndvi_threshold", threshold
    )


def make_ndvi_category_mask(image: ee.Image, threshold: float = 0.25) -> ee.Image:
    """
    Create a categorical NDVI layer:
      0 = Low vegetation / non-vegetated (NDVI < threshold)
      1 = Potential vegetation (NDVI >= threshold)

    Used for visualization, NOT for crop classification.
    """
    ndvi = image.select("NDVI")
    cat = ndvi.gte(threshold).rename("ndvi_category")
    return cat


# ---------------------------------------------------------------------------
# Temporal NDVI statistics
# ---------------------------------------------------------------------------

def temporal_ndvi_stats(collection: ee.ImageCollection) -> ee.Image:
    """
    Compute temporal NDVI statistics over the full collection period.

    Returns an image with bands:
      NDVI_mean, NDVI_max, NDVI_min, NDVI_stdDev, NDVI_median
    """
    ndvi_col = collection.map(add_ndvi).select("NDVI")
    stats = ee.Image.cat([
        ndvi_col.mean().rename("NDVI_mean"),
        ndvi_col.max().rename("NDVI_max"),
        ndvi_col.min().rename("NDVI_min"),
        ndvi_col.reduce(ee.Reducer.stdDev()).rename("NDVI_stdDev"),
        ndvi_col.median().rename("NDVI_median"),
        ndvi_col.reduce(ee.Reducer.percentile([25])).rename("NDVI_p25"),
        ndvi_col.reduce(ee.Reducer.percentile([75])).rename("NDVI_p75"),
    ])
    return stats


def temporal_evi_stats(collection: ee.ImageCollection) -> ee.Image:
    """Temporal EVI statistics."""
    evi_col = collection.map(add_evi).select("EVI")
    stats = ee.Image.cat([
        evi_col.mean().rename("EVI_mean"),
        evi_col.max().rename("EVI_max"),
        evi_col.reduce(ee.Reducer.stdDev()).rename("EVI_stdDev"),
    ])
    return stats


def temporal_ndre_stats(collection: ee.ImageCollection) -> ee.Image:
    """Temporal red-edge statistics (important for crop discrimination)."""
    ndre_col = collection.map(add_ndre).select("NDRE")
    stats = ee.Image.cat([
        ndre_col.mean().rename("NDRE_mean"),
        ndre_col.max().rename("NDRE_max"),
        ndre_col.reduce(ee.Reducer.stdDev()).rename("NDRE_stdDev"),
    ])
    return stats
