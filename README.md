# 🌿 AI-Based Brinjal Crop Detection & Mapping in India

> **Using Sentinel-2 Satellite Imagery, Google Earth Engine, and Random Forest Machine Learning**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18.3-61DAFB.svg)](https://reactjs.org)
[![GEE](https://img.shields.io/badge/Google_Earth_Engine-API-4285F4.svg)](https://earthengine.google.com)

---

## ⚠️ Important Disclaimer

Results from this system are labelled **"Predicted Brinjal Fields"** — not confirmed brinjal cultivation.

- Sentinel-2 satellite imagery does **NOT** inherently contain brinjal labels.
- NDVI alone **CANNOT** identify brinjal. Other crops share similar spectral signatures.
- Reliable detection requires GPS-verified ground-truth data, appropriate crop-season imagery, and multiple temporal observations.
- The sample training data provided is **DEMONSTRATION DATA ONLY** — replace with real ground-truth surveys for production use.

---

## Project Overview

This is a complete web-based GIS and machine-learning application that:

1. Loads **Sentinel-2 Surface Reflectance** imagery from **Google Earth Engine**
2. Applies **cloud masking** (QA60 + Scene Classification Layer)
3. Computes **NDVI, EVI, SAVI, NDWI, NDBI, NDRE** vegetation indices
4. Applies a **configurable low-NDVI filter** (default: 0.25) to isolate vegetated areas
5. Extracts **29 spectral and temporal features** per pixel
6. Trains a **Random Forest classifier** on user-supplied ground-truth polygons
7. Generates a **brinjal probability map** with confidence levels
8. Visualises results on an **interactive Leaflet map** with India coverage
9. Exports results as **CSV, GeoJSON, or Markdown report**

---

## Architecture

```
Frontend (React + Vite + TypeScript + Leaflet)
          ↕ REST API
Backend (FastAPI + Python)
    ├── Google Earth Engine (Sentinel-2, cloud masking, feature extraction)
    ├── scikit-learn (Random Forest classifier)
    └── GeoPandas / Shapely (vector processing)
```

See [docs/architecture.md](docs/architecture.md) for the full system diagram.

---

## Technologies

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Leaflet, Recharts |
| Backend | Python 3.11+, FastAPI, uvicorn |
| Satellite | Google Earth Engine Python API |
| ML | scikit-learn (RandomForestClassifier) |
| Geospatial | GeoPandas, Shapely, Fiona |
| Styling | Vanilla CSS (dark glassmorphism) |

---

## Sentinel-2 Dataset

- **Collection ID:** `COPERNICUS/S2_SR_HARMONIZED`
- **Level:** 2A (atmospherically corrected surface reflectance)
- **Bands:** B2, B3, B4, B5, B6, B7, B8, B8A, B11, B12
- **Cloud masking:** QA60 bitmask + SCL layer
- **Processing:** Server-side in Google Earth Engine (no local download required)

---

## Google Earth Engine Setup

### Step 1: Create a Google Earth Engine Account

1. Go to https://earthengine.google.com
2. Click "Sign Up" and register (free for research/education)
3. Wait for approval (usually instant for Google accounts)

### Step 2: Create a Google Cloud Project

1. Go to https://console.cloud.google.com
2. Create a new project (or use existing)
3. Enable the **Earth Engine API** for your project

### Step 3: Authentication (choose one option)

**Option A: Personal Authentication (Development)**
```bash
earthengine authenticate
```
This opens a browser, authenticates with your Google account,
and saves credentials to `~/.config/earthengine/credentials`.

**Option B: Service Account (Production/Server)**
1. In Google Cloud Console → IAM & Admin → Service Accounts
2. Create a service account
3. Grant it "Earth Engine" role
4. Create and download a JSON key
5. Add to `.env`:
```
GEE_SERVICE_ACCOUNT_EMAIL=your-account@your-project.iam.gserviceaccount.com
GEE_PRIVATE_KEY_FILE=/absolute/path/to/key.json
GEE_PROJECT_ID=your-project-id
```

---

## Installation

### Prerequisites

- Python 3.11+
- Node.js 18+
- Git

### Clone

```bash
git clone <your-repo-url>
cd brinjal-detection
```

---

## Backend Setup

### 1. Create virtual environment

```bash
cd backend
python -m venv venv

# Windows:
venv\Scripts\activate

# Linux/Mac:
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your GEE credentials and settings
```

### 4. Create directories

```bash
mkdir -p saved_models logs
```

### 5. Authenticate GEE (if using personal auth)

```bash
earthengine authenticate
```

### 6. Start backend

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify: http://localhost:8000/api/health

---

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open: http://localhost:5173

---

## Usage Workflow

### Step 1: Configure Area of Interest

- Select an **Indian state** (e.g., West Bengal)
- Optionally specify a **district**
- Or enter **latitude/longitude** with a radius
- Set the **date range** (recommended: Oct–Mar for rabi brinjal season)
- Click **"Load Satellite Data"**

### Step 2: Upload Training Data

Upload a GeoJSON file with training polygons, or use the **demo data**
(sample polygons for West Bengal, Bihar, Odisha, Karnataka).

Each polygon must have a `crop_class` property:
```json
{ "crop_class": "brinjal" }
```

### Step 3: Train Model

Click **"Train Random Forest"**. The system will:
- Extract pixel features from your training polygons
- Apply 75/25 stratified train/validation split
- Train a Random Forest with the configured number of trees
- Display accuracy, F1, confusion matrix, feature importance

### Step 4: Run Brinjal Detection

Click **"Run Brinjal Detection"**. The system will:
- Sample pixels from the full AOI
- Apply the NDVI filter (low-NDVI pixels masked)
- Classify each pixel with the trained RF model
- Calculate brinjal probabilities
- Show area statistics and map predictions

### Step 5: Export Results

Download results as:
- **CSV**: predictions table with lat/lon/class/probability
- **GeoJSON**: spatial prediction features
- **Report**: Markdown summary report

---

## Training Data Preparation

See [data/README.md](data/README.md) for full guidance.

Required GeoJSON format:
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[lon, lat], ...]]
      },
      "properties": {
        "crop_class": "brinjal"
      }
    }
  ]
}
```

**Minimum recommended samples:**
- brinjal: 20+ polygons
- other_crop: 15+
- bare_soil: 10+
- built_up: 10+
- water: 5+
- other_vegetation: 10+

---

## NDVI Threshold Explanation

The NDVI threshold is a **pre-filter only** — NOT a brinjal detector.

```
NDVI = (NIR - RED) / (NIR + RED)
     = (B8 - B4) / (B8 + B4)
```

| NDVI | Interpretation |
|------|----------------|
| < 0 | Water, bare rock |
| 0–0.1 | Bare soil, urban |
| 0.1–0.25 | Sparse vegetation |
| 0.25–0.5 | Moderate vegetation |
| 0.5–0.9 | Dense/healthy vegetation |

**Default threshold: 0.25**

- Pixels with NDVI < 0.25 are labelled "Low vegetation / non-vegetated"
- These are EXCLUDED from the crop classification pipeline
- This does NOT mean NDVI ≥ 0.25 = brinjal
- Brinjal classification is performed by the trained Random Forest model

---

## Brinjal Detection Procedure

```
Sentinel-2 imagery (COPERNICUS/S2_SR_HARMONIZED)
        ↓
Cloud masking (QA60 + SCL)
        ↓
Calculate spectral indices (NDVI, EVI, SAVI, NDWI, NDBI, NDRE)
        ↓
Calculate temporal statistics (NDVI_mean, NDVI_max, etc.)
        ↓
Build feature image (29 bands per pixel)
        ↓
Low-NDVI filter (NDVI < 0.25 → masked)
        ↓
Remaining pixels → Random Forest classifier
        ↓
Brinjal probability per pixel
        ↓
Confidence: HIGH (≥0.75) / MEDIUM (0.50–0.74) / LOW (<0.50)
        ↓
Predicted Brinjal Field Map
```

---

## Model Evaluation

Metrics are computed **only from actual training/validation data**.

- **No fabricated values** are displayed
- Validation set is a held-out 25% stratified split
- Accuracy, Precision, Recall, F1 Score, Confusion Matrix

**Note:** For rigorous academic use, consider **spatially-aware cross-validation**
(training and validation areas in separate geographic zones) to reduce
overly optimistic results from spatially autocorrelated training samples.

---

## Exporting Results

| Format | Contents |
|--------|---------|
| CSV | Lat, Lon, Predicted class, Brinjal probability, Confidence, NDVI, Date |
| GeoJSON | Point features with all prediction attributes |
| Markdown Report | Area statistics, model metrics, scientific limitations |

---

## Troubleshooting

### "Google Earth Engine is not authenticated"

Run: `earthengine authenticate` (personal) or configure service account in `.env`.

### "No Sentinel-2 images found"

- Widen the date range (try 6+ months)
- Increase the cloud threshold (try 30–40%)
- Verify the AOI is within India and Sentinel-2 coverage

### "No training pixels could be extracted"

- Ensure the Analyze job completed first
- Check training polygons are within the AOI
- Check polygons are within the date range's imagery coverage

### "Training data must contain at least 2 distinct classes"

Upload training polygons for at least 2 different crop classes (brinjal + one other).

### Backend won't start / import errors

```bash
pip install -r requirements.txt
```

Ensure you are using Python 3.11+.

### Frontend: "Cannot connect to backend"

Ensure backend is running at http://localhost:8000 before starting the frontend.

---

## Limitations

1. NDVI alone cannot identify brinjal
2. Model quality depends entirely on training data quality
3. Monsoon season cloud cover reduces imagery availability (June–September)
4. Minimum detectable field size: ~0.05 ha
5. Brinjal shares spectral signatures with other broadleaf crops
6. Results must be validated with field surveys before operational use
7. GEE free tier has quotas; large AOIs may timeout

---

## Future Extensions

The architecture supports addition of:
- XGBoost / SVM / CNN classifiers
- Sentinel-1 SAR data (cloud-independent)
- LSTM / temporal deep learning models
- Weather and soil data
- Crop yield prediction
- Disease detection
- Crop growth monitoring

---

## Project Structure

```
brinjal-detection/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI entry point
│   │   ├── api/                  # HTTP routes
│   │   ├── services/             # Business logic / job management
│   │   ├── earth_engine/         # GEE: S2 loading, cloud mask, NDVI
│   │   ├── ml/                   # Random Forest training & evaluation
│   │   ├── geospatial/           # Vector processing, export
│   │   ├── models/               # Pydantic schemas
│   │   └── utils/                # Logger
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/           # React UI components
│   │   ├── services/             # API client layer
│   │   └── types/                # TypeScript types
│   ├── package.json
│   └── vite.config.ts
├── data/
│   ├── sample_training_data/     # Demo GeoJSON (not real ground truth)
│   └── README.md
├── docs/
│   ├── architecture.md
│   ├── methodology.md
│   └── api.md
├── README.md
└── .gitignore
```

---

## References

- Sentinel-2 Mission Guide: https://sentinel.esa.int/web/sentinel/missions/sentinel-2
- Google Earth Engine: https://earthengine.google.com
- scikit-learn RandomForest: https://scikit-learn.org
- NDVI Explanation: https://earthobservatory.nasa.gov/features/MeasuringVegetation
- FAO GAUL: https://www.fao.org/geonetwork/srv/en/metadata.show?id=12691
- India Brinjal Statistics: https://nhb.gov.in

---

*College Project — AI + Remote Sensing + GIS | Brinjal Detection using Sentinel-2 and Random Forest*
