"""
Agricultural / Brinjal Field Score service.

Computes a composite spectral suitability index from Sentinel-2 or Landsat
vegetation indices.

IMPORTANT: This score is a **prototype suitability/classification metric**.
It is derived from spectral indices that correlate with dense vegetation
and healthy crop canopies. It does NOT confirm brinjal (eggplant) presence.
Ground-truth verification is required for operational use.

Formula (documented):
──────────────────────────────────────────────────────────────────────────
Let each index be clipped to its expected range and normalised to [0, 1]:

  NDVI_norm  = clamp(NDVI, 0.0, 1.0)   — vegetation density
  EVI_norm   = clamp(EVI,  0.0, 0.8) / 0.8  — canopy structure (less noise)
  SAVI_norm  = clamp(SAVI, 0.0, 0.8) / 0.8  — soil-adjusted vegetation
  NDWI_inv   = 1 – clamp(NDWI, -0.5, 0.5) / 1.0 (rescaled) — lower water = better
  NDRE_norm  = clamp(NDRE, 0.0, 0.8) / 0.8  — chlorophyll (crop health)
  NDBI_inv   = 1 – clamp(NDBI, -0.5, 0.5) (rescaled) — penalise built-up land

Score = (
    0.35 × NDVI_norm
  + 0.20 × EVI_norm
  + 0.15 × SAVI_norm
  + 0.15 × NDWI_inv
  + 0.10 × NDRE_norm
  + 0.05 × NDBI_inv
) × 100

Output: float in [0, 100]
Interpretation:
  0–30  → Low suitability (sparse vegetation, built-up, water)
  30–55 → Moderate suitability (mixed vegetation)
  55–75 → High suitability (dense crop canopy)
  75+   → Very high suitability (indicator of intensive agriculture)
──────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _safe(value: Optional[float], fallback: float = 0.0) -> float:
    """Return value if valid float, else fallback."""
    if value is None:
        return fallback
    try:
        f = float(value)
        return f if f == f else fallback  # NaN check
    except (TypeError, ValueError):
        return fallback


def compute_score(
    ndvi: Optional[float],
    evi: Optional[float] = None,
    savi: Optional[float] = None,
    ndwi: Optional[float] = None,
    ndre: Optional[float] = None,
    ndbi: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Compute the Agricultural / Brinjal Field Score.

    Parameters
    ----------
    ndvi : float
        Normalized Difference Vegetation Index (range ~-1 to 1).
    evi : float, optional
        Enhanced Vegetation Index.
    savi : float, optional
        Soil-Adjusted Vegetation Index.
    ndwi : float, optional
        Normalized Difference Water Index.
    ndre : float, optional
        Normalized Difference Red Edge.
    ndbi : float, optional
        Normalized Difference Built-up Index.

    Returns
    -------
    dict with:
      - score       : float [0, 100]
      - grade       : str (A / B / C / D)
      - label       : str (human-readable category)
      - components  : dict of normalised sub-scores with weights
      - disclaimer  : str
    """
    # ── Normalise each component ──────────────────────────────────────────
    ndvi_raw  = _safe(ndvi)
    evi_raw   = _safe(evi, ndvi_raw * 0.9)     # fallback: estimate from NDVI
    savi_raw  = _safe(savi, ndvi_raw * 0.85)   # fallback
    ndwi_raw  = _safe(ndwi, -0.1)              # fallback: slightly dry land
    ndre_raw  = _safe(ndre, ndvi_raw * 0.7)    # fallback
    ndbi_raw  = _safe(ndbi, -0.1)              # fallback: non-built

    ndvi_norm = _clamp(ndvi_raw, 0.0, 1.0)
    evi_norm  = _clamp(evi_raw, 0.0, 0.8) / 0.8
    savi_norm = _clamp(savi_raw, 0.0, 0.8) / 0.8

    # NDWI: lower value → drier soil → more suitable for brinjal (drip irrigated)
    # Rescale NDWI from [-0.5, 0.5] → [0, 1], then invert
    ndwi_scaled = (_clamp(ndwi_raw, -0.5, 0.5) + 0.5)  # [0, 1]
    ndwi_inv    = 1.0 - ndwi_scaled  # invert (dry land preferred)

    ndre_norm = _clamp(ndre_raw, 0.0, 0.8) / 0.8

    # NDBI: lower (negative) → not built-up → better agricultural land
    ndbi_scaled = (_clamp(ndbi_raw, -0.5, 0.5) + 0.5)  # [0, 1]
    ndbi_inv    = 1.0 - ndbi_scaled  # invert

    # ── Weighted composite ────────────────────────────────────────────────
    weights = {
        "ndvi": 0.35,
        "evi":  0.20,
        "savi": 0.15,
        "ndwi": 0.15,
        "ndre": 0.10,
        "ndbi": 0.05,
    }
    norms = {
        "ndvi": ndvi_norm,
        "evi":  evi_norm,
        "savi": savi_norm,
        "ndwi": ndwi_inv,
        "ndre": ndre_norm,
        "ndbi": ndbi_inv,
    }
    raw_score = sum(weights[k] * norms[k] for k in weights) * 100.0
    score = round(raw_score, 2)

    # ── Grade + label ─────────────────────────────────────────────────────
    if score >= 75:
        grade, label = "A", "Very High Suitability"
    elif score >= 55:
        grade, label = "B", "High Suitability"
    elif score >= 30:
        grade, label = "C", "Moderate Suitability"
    else:
        grade, label = "D", "Low Suitability"

    components = {
        k: {
            "raw_value": round(locals().get(f"{k}_raw", 0.0), 4),
            "normalised": round(norms[k], 4),
            "weight": weights[k],
            "contribution": round(weights[k] * norms[k] * 100, 2),
        }
        for k in weights
    }

    return {
        "score": score,
        "grade": grade,
        "label": label,
        "components": components,
        "formula": (
            "Score = (0.35×NDVI + 0.20×EVI + 0.15×SAVI + "
            "0.15×(1-NDWI) + 0.10×NDRE + 0.05×(1-NDBI)) × 100"
        ),
        "disclaimer": (
            "Prototype suitability index. High scores indicate dense vegetation "
            "consistent with intensive agriculture. This metric does NOT confirm "
            "brinjal (eggplant) cultivation. Ground-truth verification required."
        ),
    }
