# Architecture Overview

## System Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                     USER BROWSER                               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         React + Vite + TypeScript Frontend               │  │
│  │  ┌─────────────┐  ┌───────────┐  ┌───────────────────┐  │  │
│  │  │ControlPanel │  │  MapView  │  │  StatisticsPanel  │  │  │
│  │  │  (Leaflet)  │  │  (GEE     │  │  ModelPanel       │  │  │
│  │  │             │  │  tiles)   │  │  ExportPanel      │  │  │
│  │  └─────────────┘  └───────────┘  └───────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────┬───────────────────────────────────────────┘
                     │ REST API (HTTP + JSON)
                     │ Proxy via Vite dev server
┌────────────────────▼───────────────────────────────────────────┐
│                   FastAPI Backend (Python)                      │
│                                                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ /analyze │ │  /train  │ │/classify │ │  /results/{id}   │  │
│  │  route   │ │  route   │ │  route   │ │  /export/{id}    │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────────────────┘  │
│       │            │            │                               │
│  ┌────▼────────────▼────────────▼──────────────────────────┐   │
│  │                    Job Service                           │   │
│  │          (Async in-memory job tracker)                   │   │
│  └────┬──────────────────────────────────────┬─────────────┘   │
│       │                                      │                  │
│  ┌────▼───────────────────────┐   ┌──────────▼──────────────┐  │
│  │    Earth Engine Module     │   │      ML Module           │  │
│  │  ┌────────────────────┐    │   │  ┌──────────────────┐   │  │
│  │  │ sentinel2.py       │    │   │  │ random_forest.py │   │  │
│  │  │ Cloud masking      │    │   │  │ preprocessing.py │   │  │
│  │  │ ndvi.py            │    │   │  │ evaluation.py    │   │  │
│  │  │ NDVI/EVI/SAVI/NDBI │    │   │  └──────────────────┘   │  │
│  │  │ feature_extraction │    │   └─────────────────────────┘  │
│  │  └────────────────────┘    │                                 │
│  └────────────────────────────┘                                 │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   Geospatial Module                      │   │
│  │  vector.py (GeoJSON validation, MMU filter)              │   │
│  │  export.py (CSV, GeoJSON, Markdown report)               │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────┬───────────────────────────────────────────┘
                     │ Python GEE API
┌────────────────────▼───────────────────────────────────────────┐
│              Google Earth Engine (Server-side)                  │
│                                                                 │
│  COPERNICUS/S2_SR_HARMONIZED                                   │
│  FAO/GAUL/2015/level1, level2                                  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Cloud mask (QA60 + SCL)                                 │   │
│  │  → Median composite                                      │   │
│  │  → NDVI / EVI / SAVI / NDWI / NDBI / NDRE               │   │
│  │  → Temporal statistics (mean, max, min, std, median)     │   │
│  │  → Feature image (29 bands)                              │   │
│  │  → sampleRegions for training pixels                     │   │
│  │  → Map tile URLs for frontend                            │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| `frontend/` | React UI, map rendering, user controls |
| `app/api/` | FastAPI HTTP endpoints, request validation |
| `app/services/` | Business logic, job orchestration |
| `app/earth_engine/` | GEE authentication, Sentinel-2 processing |
| `app/ml/` | Random Forest training, evaluation, prediction |
| `app/geospatial/` | Vector operations, export generation |
| `app/models/` | Pydantic schemas for type safety |

## Data Flow

```
User selects AOI + Date Range
    → POST /api/analyze (returns job_id)
    → GEE: load S2 → cloud mask → compute indices → build feature image
    → Frontend polls GET /api/results/{job_id}
    → NDVI tile URLs rendered on Leaflet map

User uploads training GeoJSON
    → POST /api/training-data (returns job_id)
    → GEE: sample pixels from training polygons
    → Returns feature DataFrame

User clicks Train Model
    → POST /api/train (returns job_id)
    → sklearn: train RF, evaluate on validation set
    → Return accuracy, F1, confusion matrix, feature importance

User clicks Run Brinjal Detection
    → POST /api/classify (returns job_id)
    → Sample pixels from AOI
    → Apply trained RF → brinjal probability
    → Apply NDVI mask → area statistics
    → Frontend renders predictions on map
```

## Security Model

- All GEE credentials stored in `.env` (never in frontend code)
- API validates all input with Pydantic schemas
- File uploads have 50 MB size limit
- GeoJSON is validated before processing
- Environment variables never exposed in API responses
