# API Documentation

## Base URL

Development: `http://localhost:8000/api`

Interactive docs: `http://localhost:8000/api/docs` (Swagger UI)

---

## Authentication

All GEE operations use server-side authentication. No API keys are
required in frontend requests.

---

## Endpoints

### `GET /api/health`

Check system health and GEE authentication status.

**Response:**
```json
{
  "status": "ok",
  "gee_authenticated": true,
  "version": "1.0.0",
  "message": "Earth Engine ready. All systems operational."
}
```

---

### `POST /api/analyze`

Start a Sentinel-2 analysis job (returns immediately with job_id).

**Request:**
```json
{
  "aoi": {
    "state": "West Bengal",
    "district": "Murshidabad",
    "latitude": null,
    "longitude": null,
    "radius_km": 25,
    "geojson": null
  },
  "date_from": "2023-10-01",
  "date_to": "2024-02-28",
  "cloud_threshold": 20,
  "ndvi_threshold": 0.25,
  "scale_meters": 30
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "uuid-string",
  "status": "pending",
  "message": "Analysis job queued.",
  "created_at": "2024-01-01T00:00:00Z"
}
```

Poll `GET /api/results/{job_id}` for status and results.

---

### `POST /api/ndvi`

Identical to `/analyze` — separate endpoint for clarity.

---

### `POST /api/training-data`

Upload training polygon data.

**Request:** `multipart/form-data`
- `analyze_job_id`: string (required)
- `file`: GeoJSON file upload (optional)
- `geojson_body`: GeoJSON string (optional; one of file/body required)

**GeoJSON format:**
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Polygon", "coordinates": [[...]] },
      "properties": { "crop_class": "brinjal" }
    }
  ]
}
```

**Valid `crop_class` values:**
`brinjal`, `other_crop`, `bare_soil`, `built_up`, `water`, `other_vegetation`

---

### `POST /api/train`

Train the Random Forest classifier.

**Request:**
```json
{
  "analyze_job_id": "uuid",
  "training_job_id": "uuid",
  "n_estimators": 200,
  "max_depth": null,
  "min_samples_split": 5,
  "test_size": 0.25,
  "random_state": 42
}
```

---

### `POST /api/classify`

Run brinjal classification over the AOI.

**Request:**
```json
{
  "analyze_job_id": "uuid",
  "model_id": "uuid",
  "confidence_high_threshold": 0.75,
  "confidence_medium_threshold": 0.50,
  "min_field_area_ha": 0.05,
  "ndvi_threshold": 0.25
}
```

---

### `GET /api/results/{job_id}`

Poll any job's status and result.

**Response:**
```json
{
  "job_id": "uuid",
  "job_type": "analyze",
  "status": "completed",
  "progress": 100,
  "message": "Sentinel-2 data loaded successfully",
  "result": { ... },
  "error": null,
  "created_at": "...",
  "updated_at": "..."
}
```

**Status values:** `pending`, `running`, `completed`, `failed`

---

### `GET /api/statistics/{classify_job_id}`

Return area statistics for a completed classification.

**Response:**
```json
{
  "total_area_ha": 450.23,
  "total_area_km2": 4.5023,
  "vegetated_area_ha": 312.45,
  "vegetated_area_pct": 69.4,
  "low_ndvi_area_ha": 137.78,
  "low_ndvi_area_pct": 30.6,
  "predicted_brinjal_ha": 45.67,
  "predicted_brinjal_pct": 10.1,
  "predicted_other_crop_ha": 180.32,
  "num_brinjal_fields": 234,
  "avg_brinjal_confidence": 0.723,
  "date_from": "2023-10-01",
  "date_to": "2024-02-28",
  "cloud_threshold": 20,
  "ndvi_threshold": 0.25
}
```

---

### `GET /api/model/{train_job_id}`

Return model metrics for a completed training job.

**Response:**
```json
{
  "model_id": "uuid",
  "model_type": "Random Forest",
  "n_estimators": 200,
  "overall_accuracy": 0.8756,
  "macro_precision": 0.8432,
  "macro_recall": 0.8311,
  "macro_f1": 0.8370,
  "n_training_samples": 1500,
  "n_validation_samples": 500,
  "class_metrics": [...],
  "confusion_matrix": [[...], ...],
  "class_names": ["brinjal", "other_crop", ...],
  "feature_importances": { "NDVI_mean": 0.145, ... }
}
```

---

### `GET /api/export/{classify_job_id}?format=csv|geojson|report`

Export classification results.

| format | Content-Type | Description |
|--------|-------------|-------------|
| `csv` | `text/csv` | Lat/lon/class/probability table |
| `geojson` | `application/geo+json` | GeoJSON FeatureCollection |
| `report` | `text/markdown` | Human-readable summary |

---

## Error Codes

| Code | Meaning |
|------|---------|
| 202 | Job queued (long-running) |
| 400 | Invalid request parameters |
| 404 | Job or resource not found |
| 413 | File too large (> 50 MB) |
| 422 | Validation error |
| 503 | GEE not authenticated |
