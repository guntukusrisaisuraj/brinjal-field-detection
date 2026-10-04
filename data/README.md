# Training Data Guide

## Overview

This directory contains sample training data for the Brinjal Detection system.

> **⚠ IMPORTANT: All data in `sample_training_data/` is DEMONSTRATION DATA ONLY.**
> It is provided to demonstrate the system workflow and show the expected format.
> Replace with real GPS-verified ground-truth data before any production use.

---

## File: `sample_training_data.geojson`

A GeoJSON FeatureCollection with 12 sample polygons across:
- West Bengal (Murshidabad)
- Bihar (Nalanda)
- Karnataka
- Odisha

### Classes included:
| Class | Description |
|-------|-------------|
| `brinjal` | Brinjal (eggplant) cultivation areas |
| `other_crop` | Rice, jute, wheat, and other crops |
| `bare_soil` | Fallow / bare agricultural land |
| `built_up` | Urban / built-up areas |
| `water` | Water bodies, reservoirs |
| `other_vegetation` | Forests, shrublands, non-crop vegetation |

---

## GeoJSON Format

Each training polygon must follow this format:

```json
{
  "type": "Feature",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[lon1, lat1], [lon2, lat2], ..., [lon1, lat1]]]
  },
  "properties": {
    "crop_class": "brinjal",
    "label": "Optional description",
    "state": "West Bengal",
    "district": "Murshidabad",
    "season": "rabi"
  }
}
```

**Required property:** `crop_class` (must be one of: `brinjal`, `other_crop`, `bare_soil`, `built_up`, `water`, `other_vegetation`)

---

## Real Ground-Truth Data Collection Tips

For reliable brinjal detection, ground-truth data should:

1. **Be GPS-verified** – Use a mobile GPS or GNSS device during field surveys.
2. **Cover the target season** – Brinjal rabi season: October–March; kharif: June–September.
3. **Be representative** – Include fields of different sizes, ages, and irrigation status.
4. **Include negative examples** – Other crops, bare soil, and water are essential for the RF classifier.
5. **Minimum polygon size** – Use polygons larger than 0.05 ha (smaller than Sentinel-2 pixel resolution at 10 m = 0.01 ha).
6. **Avoid boundaries** – Avoid mixed pixels at field edges.
7. **Spatial diversity** – Spread training polygons across different areas to reduce spatial autocorrelation bias.

---

## Required Samples per Class

| Class | Minimum Recommended | Notes |
|-------|--------------------|-|
| brinjal | 20+ polygons | Must be present |
| other_crop | 15+ | Helps distinguish from brinjal |
| bare_soil | 10+ | Reduces false positives |
| built_up | 10+ | Reduces false positives |
| water | 5+ | Distinctive spectral signature |
| other_vegetation | 10+ | Forests, grasslands |

---

## CSV Format (Alternative)

You can also upload a CSV with lat/lon and class labels:

```csv
latitude,longitude,crop_class,label
22.57,88.36,brinjal,WB field 1
25.35,85.14,brinjal,Bihar field 1
25.40,85.20,other_crop,Rice paddy
28.70,77.20,built_up,Delhi urban
```

---

## Sources for Real Training Data

- **Bhuvan** (NRSC/ISRO): https://bhuvan.nrsc.gov.in
- **Kisan Portal** (GoI): Agricultural field boundaries
- **ICRISAT** open datasets
- **FAO GAUL** administrative boundaries
- Own GPS field surveys (most reliable)
