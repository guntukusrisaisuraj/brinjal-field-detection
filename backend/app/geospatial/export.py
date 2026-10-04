"""
Export utilities: CSV, GeoJSON, and summary report generation.
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from app.utils.logger import logger


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def export_csv(predictions: List[Dict[str, Any]]) -> bytes:
    """
    Convert a list of prediction records to CSV bytes.

    Each record should have: latitude, longitude, predicted_class,
    brinjal_probability, ndvi, date.
    """
    df = pd.DataFrame(predictions)
    cols = [
        "latitude", "longitude", "predicted_class",
        "brinjal_probability", "confidence_level",
        "ndvi", "date",
    ]
    for col in cols:
        if col not in df.columns:
            df[col] = None

    buf = io.StringIO()
    df[cols].to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# GeoJSON export
# ---------------------------------------------------------------------------

def export_geojson(
    prediction_features: List[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    Export predicted brinjal polygons as a GeoJSON FeatureCollection.

    Each feature includes properties:
      - predicted_class
      - brinjal_probability
      - confidence_level
      - area_ha
      - date_from / date_to
    """
    fc = {
        "type": "FeatureCollection",
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "description": (
                "Predicted Brinjal Fields – AI-Based Brinjal Crop Detection. "
                "Results represent model predictions, NOT confirmed ground truth."
            ),
            **(metadata or {}),
        },
        "features": prediction_features,
    }
    return json.dumps(fc, indent=2).encode("utf-8")


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------

def export_summary_report(
    statistics: Dict[str, Any],
    model_metrics: Optional[Dict[str, Any]] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    Generate a human-readable text/markdown summary report.
    """
    lines = [
        "# AI-Based Brinjal Crop Detection – Summary Report",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
        "## IMPORTANT DISCLAIMER",
        "Results are labelled as 'Predicted Brinjal Fields'.",
        "Sentinel-2 imagery does NOT inherently identify brinjal.",
        "Classification is performed by a Random Forest model trained on",
        "ground-truth data supplied by the user.",
        "Accuracy depends on training data quality and cloud-free image availability.",
        "",
        "---",
        "",
        "## Analysis Parameters",
    ]

    if parameters:
        for k, v in parameters.items():
            lines.append(f"- **{k}**: {v}")

    lines += [
        "",
        "## Area Statistics",
        f"- Total Analyzed Area: {statistics.get('total_area_ha', 0):.2f} ha "
        f"({statistics.get('total_area_km2', 0):.2f} km²)",
        f"- Vegetated Area: {statistics.get('vegetated_area_ha', 0):.2f} ha "
        f"({statistics.get('vegetated_area_pct', 0):.1f}%)",
        f"- Low-NDVI Area: {statistics.get('low_ndvi_area_ha', 0):.2f} ha "
        f"({statistics.get('low_ndvi_area_pct', 0):.1f}%)",
        f"- Predicted Brinjal Area: {statistics.get('predicted_brinjal_ha', 0):.2f} ha "
        f"({statistics.get('predicted_brinjal_pct', 0):.1f}%)",
        f"- Predicted Other Crop Area: {statistics.get('predicted_other_crop_ha', 0):.2f} ha",
        f"- Number of Predicted Brinjal Fields: {statistics.get('num_brinjal_fields', 0)}",
        f"- Avg Brinjal Confidence: {statistics.get('avg_brinjal_confidence', 0):.3f}",
    ]

    if model_metrics:
        lines += [
            "",
            "## Model Metrics",
            f"- Model Type: {model_metrics.get('model_type', 'Random Forest')}",
            f"- Training Samples: {model_metrics.get('n_training_samples', 0)}",
            f"- Validation Samples: {model_metrics.get('n_validation_samples', 0)}",
            f"- Overall Accuracy: {model_metrics.get('overall_accuracy', 0):.4f}",
            f"- Macro Precision: {model_metrics.get('macro_precision', 0):.4f}",
            f"- Macro Recall: {model_metrics.get('macro_recall', 0):.4f}",
            f"- Macro F1: {model_metrics.get('macro_f1', 0):.4f}",
        ]

    lines += [
        "",
        "---",
        "",
        "## Scientific Limitations",
        "- Brinjal spectral signature overlaps with other broadleaf crops.",
        "- Reliable detection requires high-quality ground-truth data.",
        "- Results may be less accurate at field boundaries.",
        "- Cloud cover may reduce image availability in monsoon season.",
        "- Minimum detectable field size: ~0.05 ha at 10 m Sentinel-2 resolution.",
    ]

    return "\n".join(lines).encode("utf-8")
