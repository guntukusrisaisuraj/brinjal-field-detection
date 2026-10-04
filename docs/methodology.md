# Scientific Methodology

## 1. Overview

This system uses a supervised machine-learning approach to detect brinjal
(eggplant / *Solanum melongena*) cultivation in India using Sentinel-2
multispectral satellite imagery.

> **Important:** Results are labelled as "Predicted Brinjal Fields" — not
> confirmed brinjal cultivation. Reliable crop identification requires
> GPS-verified ground truth, appropriate imagery timing, and model validation.

---

## 2. Satellite Data

### Primary: Sentinel-2 (Level-2A Surface Reflectance)

- **Collection:** `COPERNICUS/S2_SR_HARMONIZED` (harmonised, atmospherically corrected)
- **Spatial resolution:** 10–20 m (bands used at 30 m for consistency)
- **Revisit time:** ~5 days (2-satellite constellation)
- **Available since:** June 2015

### Bands used:

| Band | Name | Resolution | Wavelength |
|------|------|------------|-----------|
| B2 | Blue | 10 m | 490 nm |
| B3 | Green | 10 m | 560 nm |
| B4 | Red | 10 m | 665 nm |
| B5 | Red Edge 1 | 20 m | 705 nm |
| B6 | Red Edge 2 | 20 m | 740 nm |
| B7 | Red Edge 3 | 20 m | 783 nm |
| B8 | NIR | 10 m | 842 nm |
| B8A | Narrow NIR | 20 m | 865 nm |
| B11 | SWIR 1 | 20 m | 1610 nm |
| B12 | SWIR 2 | 20 m | 2190 nm |

---

## 3. Cloud Masking

Two-stage cloud masking is applied:

1. **QA60 Bitmask:** Masks opaque clouds (bit 10) and cirrus (bit 11)
2. **Scene Classification Layer (SCL):** Additionally masks cloud shadows (3),
   medium/high probability clouds (8, 9), and thin cirrus (10)

Default cloud threshold: 20% scene cloud cover. User-configurable (0–100%).

---

## 4. Vegetation Indices

### NDVI (Normalized Difference Vegetation Index)
```
NDVI = (NIR - RED) / (NIR + RED) = (B8 - B4) / (B8 + B4)
```
Range: -1 to +1. Dense vegetation ≈ 0.6–0.9.

### EVI (Enhanced Vegetation Index)
```
EVI = 2.5 × (NIR - RED) / (NIR + 6×RED - 7.5×BLUE + 1)
```
Less sensitive to atmospheric effects and soil background than NDVI.

### SAVI (Soil-Adjusted Vegetation Index)
```
SAVI = ((NIR - RED) / (NIR + RED + L)) × (1 + L), L = 0.5
```
Corrects for soil background in sparse vegetation.

### NDWI (Normalized Difference Water Index)
```
NDWI = (GREEN - NIR) / (GREEN + NIR) = (B3 - B8) / (B3 + B8)
```
Positive values indicate water bodies.

### NDBI (Normalized Difference Built-up Index)
```
NDBI = (SWIR1 - NIR) / (SWIR1 + NIR) = (B11 - B8) / (B11 + B8)
```
Helps distinguish built-up areas from vegetation.

### NDRE (Normalized Difference Red Edge)
```
NDRE = (B8A - B5) / (B8A + B5)
```
Sentinel-2's red-edge bands (B5–B7) are particularly useful for
crop discrimination and canopy chlorophyll content estimation.

---

## 5. Low-NDVI Filter

Before machine-learning classification, a vegetation pre-filter is applied:

- **Threshold:** NDVI < 0.25 → Masked as "Low vegetation / non-vegetated"
- **Purpose:** Reduces computational load; non-vegetated areas are unlikely to be brinjal
- **CRITICAL:** This is NOT the brinjal classifier. The filter only removes
  obviously non-vegetated pixels. Actual crop classification uses the RF model.

---

## 6. Temporal Analysis

A single satellite image is insufficient for reliable crop identification.
The system uses the full temporal stack of Sentinel-2 images within the
specified date range:

| Temporal Feature | Description |
|-----------------|-------------|
| NDVI_mean | Average NDVI over the season |
| NDVI_max | Peak NDVI (maximum canopy greenness) |
| NDVI_min | Minimum NDVI (harvest/bare soil period) |
| NDVI_stdDev | Seasonal variability (crop phenology) |
| NDVI_median | Robust central tendency |
| NDVI_p25/p75 | Inter-quartile range |
| EVI_mean/max/std | EVI temporal statistics |
| NDRE_mean/max/std | Red-edge temporal statistics |

---

## 7. Feature Vector

Each pixel is described by **29 features**:
- 10 raw Sentinel-2 bands (median composite)
- 6 spectral indices (NDVI, EVI, NDWI, SAVI, NDBI, NDRE)
- 7 temporal NDVI statistics
- 3 temporal EVI statistics
- 3 temporal NDRE statistics

---

## 8. Random Forest Classification

**Algorithm:** sklearn `RandomForestClassifier`

**Hyperparameters:**
- `n_estimators`: 200 (configurable)
- `class_weight`: "balanced" (compensates for class imbalance)
- `oob_score`: True (out-of-bag validation estimate)
- `min_samples_split`: 5 (prevents overfitting)

**Classes:**
1. Brinjal (class 0)
2. Other crop (class 1)
3. Bare soil (class 2)
4. Built-up (class 3)
5. Water (class 4)
6. Other vegetation (class 5)

---

## 9. Confidence Levels

The RF model outputs per-class probabilities. For brinjal:

| Probability | Confidence Level |
|-------------|-----------------|
| ≥ 0.75 | HIGH — strong prediction |
| 0.50–0.74 | MEDIUM — moderate confidence |
| < 0.50 | LOW — uncertain, likely not brinjal |

---

## 10. Limitations

1. **Spectral overlap:** Brinjal has similar spectral signature to other
   broadleaf crops (tomato, potato, chilli). Red-edge bands help but
   are not fully discriminative.

2. **Training data dependency:** Model quality is entirely dependent on
   the quality and representativeness of the training polygons.

3. **Minimum field size:** Reliable detection requires fields > 0.05 ha.
   Small kitchen gardens may not be detected.

4. **Monsoon cloud cover:** June–September has high cloud cover over most
   of India, reducing available imagery.

5. **Mixed pixels:** Field boundary pixels contain mixed spectral signals.

6. **Temporal mismatch:** If training data was collected at a different
   phenological stage than the classification imagery, accuracy degrades.

7. **10 m vs 30 m:** Brinjal fields smaller than ~0.1 ha (ten 10-m pixels)
   are difficult to detect reliably.
