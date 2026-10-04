"""
Main analysis service – orchestrates the full detection pipeline.

Pipeline:
  1. Load Sentinel-2 collection (GEE)
  2. Cloud masking
  3. NDVI calculation + low-NDVI filter
  4. Feature extraction (spectral + temporal)
  5. (If training data provided) sample features → train RF
  6. Apply trained RF → brinjal probabilities
  7. Post-process → field-level stats
  8. Generate map tile URLs
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import date
from typing import Any, Dict, List, Optional

import ee
import numpy as np

from app.earth_engine.ee_client import EEClient
from app.earth_engine.feature_extraction import (
    FEATURE_BANDS,
    ALPHAEARTH_FEATURE_BANDS,
    build_feature_image,
    feature_names_for,
    get_ndvi_tile_url,
    aoi_index_means,
    validate_feature_image,
    sample_training_features,
    get_feature_array,
)
from app.earth_engine.ndvi import (
    apply_low_ndvi_mask,
    make_ndvi_category_mask,
    temporal_ndvi_stats,
)
from app.earth_engine.sentinel2 import (
    aoi_from_request,
    collection_info,
    create_median_composite,
    load_sentinel2_collection,
)
from app.ml.evaluation import evaluate_model
from app.ml.preprocessing import (
    class_sample_report,
    scale_features,
    split_train_val,
    validate_classes,
)
from app.ml.random_forest import (
    BRINJAL_CLASS_ID,
    BrinjalRandomForest,
    CLASS_NAMES,
    get_model,
    register_model,
)
from app.services.alphaearth_service import (
    ALPHA_EARTH_COLLECTION,
    build_alphaearth_feature_image,
)
from app.models.schemas import (
    AnalyzeRequest,
    ClassifyRequest,
    TrainRequest,
    TrainingDataRequest,
)
from app.services.job_service import Job, JobStatus, job_service
from app.utils.logger import logger

# In-memory result cache
_result_cache: Dict[str, Dict[str, Any]] = {}
_result_cache_created: Dict[str, float] = {}
RESULT_RETENTION_SECONDS = 24 * 60 * 60
MAX_RESULT_CACHE_ENTRIES = 100


def _cleanup_result_cache(
    now: Optional[float] = None,
    additionally_protected: Optional[set[str]] = None,
) -> None:
    """Prune expired/oldest unpinned entries; active job contexts stay resident."""
    now = time.monotonic() if now is None else now
    protected = job_service.protected_context_ids() | (additionally_protected or set())
    for key in _result_cache:
        _result_cache_created.setdefault(key, now)

    expired = [
        key for key, created in _result_cache_created.items()
        if key in _result_cache
        and key not in protected
        and now - created >= RESULT_RETENTION_SECONDS
    ]
    for key in expired:
        _result_cache.pop(key, None)
        _result_cache_created.pop(key, None)

    protected_count = len(protected.intersection(_result_cache))
    overflow = max(0, len(_result_cache) - protected_count - MAX_RESULT_CACHE_ENTRIES)
    evictable = sorted(
        (key for key in _result_cache if key not in protected),
        key=lambda key: _result_cache_created.get(key, now),
    )
    for key in evictable[:overflow]:
        _result_cache.pop(key, None)
        _result_cache_created.pop(key, None)


def cleanup_result_cache() -> None:
    """Run lazy retention cleanup for results polling and result consumers."""
    _cleanup_result_cache()


def store_result(job_id: str, data: Dict[str, Any]) -> None:
    _cleanup_result_cache()
    _result_cache[job_id] = data
    _result_cache_created[job_id] = time.monotonic()
    _cleanup_result_cache(additionally_protected={job_id})


def get_result(job_id: str) -> Optional[Dict[str, Any]]:
    _cleanup_result_cache()
    return _result_cache.get(job_id)


# ---------------------------------------------------------------------------
# Analyze (load S2 + compute NDVI + build feature image)
# ---------------------------------------------------------------------------

async def run_analyze(job: Job, request: AnalyzeRequest) -> None:
    """Background task: load S2 data and build feature image."""
    loop = asyncio.get_running_loop()
    try:
        await job_service.update_job(job.job_id, status=JobStatus.RUNNING,
                                      progress=5, message="Initialising Earth Engine")

        if not EEClient.is_ready():
            raise RuntimeError("Earth Engine not initialised")

        aoi_dict = request.aoi.model_dump()

        # Step 1: AOI
        await job_service.update_job(job.job_id, progress=10, message="Resolving AOI")
        aoi = await loop.run_in_executor(None, aoi_from_request, aoi_dict)

        # Step 2: Load collection
        await job_service.update_job(job.job_id, progress=20,
                                      message="Loading Sentinel-2 collection")
        collection = await loop.run_in_executor(
            None,
            load_sentinel2_collection,
            aoi, request.date_from, request.date_to, request.cloud_threshold,
        )

        try:
            info = await loop.run_in_executor(None, collection_info, collection)
        except Exception as exc:
            raise RuntimeError(
                f"Earth Engine could not evaluate the Sentinel-2 collection: {exc}"
            ) from exc
        if info["image_count"] == 0:
            raise ValueError(
                f"No Sentinel-2 images found for the selected AOI and date range "
                f"({request.date_from} → {request.date_to}) "
                f"with cloud threshold ≤ {request.cloud_threshold}%. "
                "Try widening the date range or increasing the cloud threshold."
            )

        await job_service.update_job(
            job.job_id, progress=35,
            message=f"Found {info['image_count']} images. Building feature stack..."
        )

        # Step 3: Build feature image
        try:
            feature_image = await loop.run_in_executor(
                None, build_feature_image, collection, aoi
            )
        except Exception as exc:
            raise RuntimeError(f"Earth Engine could not build the feature image: {exc}") from exc

        await loop.run_in_executor(
            None, validate_feature_image, feature_image, aoi, request.scale_meters
        )

        # Reduce the already-computed median-composite index bands over the
        # same AOI and requested analysis scale.
        try:
            index_stats = await loop.run_in_executor(
                None, aoi_index_means, feature_image, aoi, request.scale_meters
            )
        except Exception as exc:
            raise RuntimeError(
                f"Earth Engine could not calculate Sentinel-2 AOI index statistics: {exc}"
            ) from exc

        # Step 4: NDVI tile URLs
        await job_service.update_job(job.job_id, progress=70,
                                      message="Generating NDVI visualisation")
        try:
            tile_urls = await loop.run_in_executor(
                None, get_ndvi_tile_url, feature_image, aoi, request.ndvi_threshold
            )
        except Exception as exc:
            raise RuntimeError(f"Earth Engine could not generate NDVI map tiles: {exc}") from exc

        # Step 5: AOI bounds for the frontend map
        try:
            bounds = await loop.run_in_executor(None, lambda: aoi.bounds().getInfo())
        except Exception as exc:
            raise RuntimeError(f"Earth Engine could not evaluate AOI bounds: {exc}") from exc

        result = {
            "analyze_job_id": job.job_id,
            "collection_info": info,
            "tile_urls": tile_urls,
            "index_stats": index_stats,
            "aoi_bounds": bounds,
            "ndvi_threshold": request.ndvi_threshold,
            "cloud_threshold": request.cloud_threshold,
            "scale_meters": request.scale_meters,
            "date_from": request.date_from,
            "date_to": request.date_to,
            # Store references for later pipeline steps
            "_feature_image_id": id(feature_image),
            "_collection_id": id(collection),
            "_aoi_id": id(aoi),
        }

        # Cache heavy objects (in-process)
        store_result(job.job_id, {
            **result,
            "_feature_image": feature_image,
            "_collection": collection,
            "_aoi": aoi,
        })

        await job_service.update_job(
            job.job_id, status=JobStatus.COMPLETED, progress=100,
            message="Sentinel-2 data loaded successfully", result=result,
        )

    except Exception as exc:
        logger.exception(f"[AnalyzeService] Job {job.job_id} failed: {exc}")
        await job_service.update_job(
            job.job_id, status=JobStatus.FAILED,
            message="Analysis failed", error=str(exc),
        )


# ---------------------------------------------------------------------------
# Training data extraction
# ---------------------------------------------------------------------------

def training_label_source(training_data_source: str) -> str:
    """Keep labelled uploads distinguishable from demonstration samples."""
    return "demonstration_data" if training_data_source == "demo" else "ground_truth"


async def run_extract_training(
    job: Job, analyze_job_id: str, training_features: List[Dict[str, Any]],
    scale: int = 30, alphaearth_enabled: bool = False,
    training_data_source: str = "uploaded",
) -> None:
    """Background task: sample pixel features from training polygons."""
    loop = asyncio.get_running_loop()
    try:
        await job_service.update_job(job.job_id, status=JobStatus.RUNNING,
                                      progress=10, message="Retrieving analysis context")

        cached = get_result(analyze_job_id)
        if not cached:
            raise ValueError(f"Analysis job '{analyze_job_id}' not found or expired. "
                             "Please re-run the analysis first.")

        feature_image = cached.get("_feature_image")
        if feature_image is None:
            raise ValueError("Feature image not found in cache. Re-run analysis.")
        # Keep compatibility with direct callers that pass a scale argument,
        # while using the analysis request's scale for associated extraction.
        scale = int(cached.get("scale_meters", scale))
        alphaearth_image = None
        alphaearth_year = None
        if alphaearth_enabled:
            date_to = cached.get("date_to")
            if not date_to:
                raise ValueError("Analysis context has no date_to for annual AlphaEarth feature selection.")
            alphaearth_year = date.fromisoformat(date_to).year
            await job_service.update_job(
                job.job_id, progress=20,
                message=f"Loading AlphaEarth {alphaearth_year} embedding features",
            )
            alphaearth_image = await loop.run_in_executor(
                None, build_alphaearth_feature_image, cached["_aoi"], alphaearth_year
            )

        await job_service.update_job(job.job_id, progress=30,
                                      message="Sampling pixel features from polygons")

        if alphaearth_enabled:
            sample_call = lambda: sample_training_features(
                feature_image, training_features, scale, 150,
                additional_feature_image=alphaearth_image,
            )
        else:
            # Preserve the original S2-only call signature for existing integrations.
            sample_call = lambda: sample_training_features(
                feature_image, training_features, scale, 150,
            )
        df = await loop.run_in_executor(None, sample_call)

        X, y = get_feature_array(df)
        class_counts = class_sample_report(y)

        result = {
            "training_job_id": job.job_id,
            "n_samples": len(df),
            "class_counts": class_counts,
            "feature_names": feature_names_for(alphaearth_enabled),
            "alphaearth_enabled": alphaearth_enabled,
            "alphaearth_collection": ALPHA_EARTH_COLLECTION,
            "alphaearth_dimensions": len(ALPHAEARTH_FEATURE_BANDS),
            "alphaearth_feature_names": ALPHAEARTH_FEATURE_BANDS,
            "alphaearth_year": alphaearth_year,
            "training_data_source": training_data_source,
            "label_source": training_label_source(training_data_source),
        }

        # The dataframe is only needed to build X/y and otherwise duplicates
        # the same sampled values in the in-memory context.
        X_sentinel = df[FEATURE_BANDS].values.astype(np.float32)
        store_result(job.job_id, {
            **result,
            "_X": X,
            "_X_sentinel": X_sentinel,
            "_y": y,
            "_feature_names": feature_names_for(alphaearth_enabled),
        })

        await job_service.update_job(
            job.job_id, status=JobStatus.COMPLETED, progress=100,
            message=f"Extracted {len(df)} training pixels", result=result,
        )

    except Exception as exc:
        logger.exception(f"[TrainingService] Job {job.job_id} failed: {exc}")
        await job_service.update_job(
            job.job_id, status=JobStatus.FAILED,
            message="Feature extraction failed", error=str(exc),
        )


# ---------------------------------------------------------------------------
# Model training
# ---------------------------------------------------------------------------

async def run_train(job: Job, request: TrainRequest) -> None:
    """Background task: train Random Forest classifier."""
    loop = asyncio.get_running_loop()
    try:
        await job_service.update_job(job.job_id, status=JobStatus.RUNNING,
                                      progress=10, message="Loading training features")

        train_cache = get_result(request.training_job_id)
        if not train_cache:
            raise ValueError(
                f"Training data for job '{request.training_job_id}' is unavailable or expired. "
                "Re-upload the training data and try again."
            )

        X: np.ndarray = train_cache["_X"]
        y: np.ndarray = train_cache["_y"]
        alphaearth_enabled = bool(train_cache.get("alphaearth_enabled", False))
        if alphaearth_enabled != bool(request.alphaearth_enabled):
            raise ValueError(
                "The AlphaEarth setting must match the setting used during feature extraction. "
                "Re-extract training features with the desired option."
            )
        feature_names = list(train_cache.get("_feature_names", FEATURE_BANDS))
        expected_feature_names = feature_names_for(alphaearth_enabled)
        if feature_names != expected_feature_names or X.shape[1] != len(feature_names):
            raise ValueError("Training features do not match the recorded feature schema.")
        X_sentinel = train_cache.get("_X_sentinel", X[:, :len(FEATURE_BANDS)])
        if X_sentinel.shape != (len(X), len(FEATURE_BANDS)):
            raise ValueError("Sentinel-2 baseline features are unavailable for comparison.")

        # Validate classes
        await job_service.update_job(job.job_id, progress=20,
                                      message="Validating class distribution")
        validate_classes(y)

        # Split
        X_train, X_val, y_train, y_val = split_train_val(
            X, y, test_size=request.test_size, random_state=request.random_state
        )

        # Scale (RF is scale-invariant but normalisation is good practice)
        X_train_sc, X_val_sc, _scaler = scale_features(X_train, X_val)

        # Train
        await job_service.update_job(job.job_id, progress=40,
                                      message="Training Random Forest classifier")
        model = BrinjalRandomForest(
            n_estimators=request.n_estimators,
            max_depth=request.max_depth,
            min_samples_split=request.min_samples_split,
            random_state=request.random_state,
            alphaearth_enabled=alphaearth_enabled,
        )
        model.label_source = train_cache.get("label_source") or training_label_source(
            train_cache.get("training_data_source", "uploaded")
        )
        await loop.run_in_executor(
            None, model.train, X_train_sc, y_train, feature_names
        )

        # Evaluate
        await job_service.update_job(job.job_id, progress=75,
                                      message="Evaluating model on validation set")
        y_pred = await loop.run_in_executor(None, model.predict, X_val_sc)
        class_ids_present = sorted(np.unique(y_val).tolist())
        metrics = evaluate_model(y_val, y_pred, class_ids_present)

        comparison = None
        if alphaearth_enabled:
            # Identical row split and RF settings for a paired feature ablation.
            Xs_train, Xs_val, ys_train, ys_val = split_train_val(
                X_sentinel, y, test_size=request.test_size,
                random_state=request.random_state,
            )
            if not np.array_equal(ys_train, y_train) or not np.array_equal(ys_val, y_val):
                raise ValueError("Could not construct a matched validation split for comparison.")
            Xs_train_sc, Xs_val_sc, _ = scale_features(Xs_train, Xs_val)
            baseline = BrinjalRandomForest(
                n_estimators=request.n_estimators,
                max_depth=request.max_depth,
                min_samples_split=request.min_samples_split,
                random_state=request.random_state,
            )
            await loop.run_in_executor(None, baseline.train, Xs_train_sc, ys_train, list(FEATURE_BANDS))
            baseline_pred = await loop.run_in_executor(None, baseline.predict, Xs_val_sc)
            baseline_metrics = evaluate_model(ys_val, baseline_pred, class_ids_present)
            def comparison_metrics(metric_result):
                brinjal = next((item for item in metric_result["class_metrics"]
                                if item["crop_class"] == "brinjal"), {})
                return {
                    "accuracy": metric_result["overall_accuracy"],
                    "macro_precision": metric_result["macro_precision"],
                    "macro_recall": metric_result["macro_recall"],
                    "macro_f1": metric_result["macro_f1"],
                    "brinjal_precision": brinjal.get("precision"),
                    "brinjal_recall": brinjal.get("recall"),
                    "brinjal_f1": brinjal.get("f1_score"),
                }
            comparison = {
                "evaluation_label": (
                    "Technical validation on demonstration polygons; not real-world agricultural accuracy."
                    if train_cache.get("training_data_source") == "demo"
                    else "Validation on supplied training polygons; field validation is not established."
                ),
                "model_a": {"feature_sources": ["Sentinel-2"], **comparison_metrics(baseline_metrics)},
                "model_b": {"feature_sources": ["Sentinel-2", "AlphaEarth embeddings (64)"], **comparison_metrics(metrics)},
            }

        # Save
        await job_service.update_job(job.job_id, progress=90, message="Saving model")
        model_dir = os.getenv("MODEL_DIR", "./saved_models")
        os.makedirs(model_dir, exist_ok=True)
        model_path = await loop.run_in_executor(None, model.save, model_dir)

        # Register
        register_model(model)
        # Keep the just-produced model/scaler context pinned until this train
        # job reaches a terminal state.
        job.depends_on.add(model.model_id)
        store_result(model.model_id, {
            "_model": model,
            "_scaler": _scaler,
            "model_path": model_path,
        })

        result = {
            "model_id": model.model_id,
            "model_type": "Random Forest",
            "n_estimators": request.n_estimators,
            "n_training_samples": int(len(X_train)),
            "n_validation_samples": int(len(X_val)),
            "feature_importances": model.feature_importances_dict(),
            "alphaearth_enabled": alphaearth_enabled,
            "alphaearth_collection": ALPHA_EARTH_COLLECTION,
            "alphaearth_dimensions": len(ALPHAEARTH_FEATURE_BANDS),
            "alphaearth_feature_names": ALPHAEARTH_FEATURE_BANDS,
            "feature_sources": ["Sentinel-2", "AlphaEarth embeddings (64)"] if alphaearth_enabled else ["Sentinel-2"],
            "label_source": model.label_source,
            "model_comparison": comparison,
            "trained_at": model.trained_at,
            **metrics,
        }

        store_result(job.job_id, result)
        await job_service.update_job(
            job.job_id, status=JobStatus.COMPLETED, progress=100,
            message="Model trained successfully", result=result,
        )

    except Exception as exc:
        logger.exception(f"[TrainService] Job {job.job_id} failed: {exc}")
        await job_service.update_job(
            job.job_id, status=JobStatus.FAILED,
            message="Model training failed", error=str(exc),
        )


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

async def run_classify(job: Job, request: ClassifyRequest) -> None:
    """Background task: classify the AOI using the trained RF model."""
    loop = asyncio.get_running_loop()
    try:
        await job_service.update_job(job.job_id, status=JobStatus.RUNNING,
                                      progress=10, message="Loading model and features")

        analyze_cache = get_result(request.analyze_job_id)
        if not analyze_cache:
            raise ValueError(
                f"Analysis context for job '{request.analyze_job_id}' is unavailable or expired. "
                "Run the analysis again before classification."
            )

        model_cache = get_result(request.model_id)
        if not model_cache:
            raise ValueError(
                f"Model context '{request.model_id}' is unavailable or expired. "
                "Train the model again before classification."
            )

        model: BrinjalRandomForest = model_cache["_model"]
        scaler = model_cache["_scaler"]
        feature_image: ee.Image = analyze_cache["_feature_image"]
        aoi: ee.Geometry = analyze_cache["_aoi"]
        scale_meters = int(analyze_cache.get("scale_meters", 30))
        alphaearth_enabled = bool(getattr(model, "alphaearth_enabled", False))
        model_feature_names = list(getattr(model, "feature_names", FEATURE_BANDS))
        if model_feature_names != feature_names_for(alphaearth_enabled):
            raise ValueError("The saved model feature schema is invalid or unsupported.")
        if alphaearth_enabled:
            analysis_year = date.fromisoformat(analyze_cache["date_to"]).year
            await job_service.update_job(job.job_id, progress=20,
                message=f"Loading AlphaEarth learned embeddings for {analysis_year}")
            alpha_image = await loop.run_in_executor(
                None, lambda: build_alphaearth_feature_image(aoi, analysis_year)
            )
            feature_image = feature_image.addBands(alpha_image).select(model_feature_names)

        await job_service.update_job(job.job_id, progress=25,
                                      message="Sampling classification pixels from AOI")

        # Sample pixels from the full AOI for prediction
        # (In production use EE Classifier for pixel-wise; here we sample for demo)
        n_sample_pixels = 5000
        sample_fc = await loop.run_in_executor(
            None,
            lambda: feature_image.sample(
                region=aoi, scale=scale_meters, numPixels=n_sample_pixels,
                geometries=True, seed=99,
            )
        )

        sample_info = await loop.run_in_executor(
            None, lambda: sample_fc.getInfo()
        )
        feats = sample_info["features"]

        if not feats:
            raise ValueError(
                "No pixels could be sampled from the AOI. "
                "Ensure the date range has sufficient cloud-free imagery."
            )

        await job_service.update_job(job.job_id, progress=50,
                                      message=f"Classifying {len(feats)} pixels")

        # Build feature matrix
        rows = []
        coords = []
        for feat in feats:
            props = feat["properties"]
            geom = feat.get("geometry", {})
            row = [props.get(b, np.nan) for b in model_feature_names]
            rows.append(row)
            if geom.get("type") == "Point":
                c = geom["coordinates"]
                coords.append((c[1], c[0]))  # lat, lon
            else:
                coords.append((np.nan, np.nan))

        X_cls = np.array(rows, dtype=np.float32)

        # Mask NaN rows
        valid_mask = np.all(np.isfinite(X_cls), axis=1)
        X_valid = X_cls[valid_mask]
        if not len(X_valid):
            raise ValueError(
                "No sampled pixels have complete values for this model's feature schema. "
                "For an AlphaEarth-enabled model, check annual embedding coverage for the AOI."
            )
        coords_valid = [c for c, m in zip(coords, valid_mask) if m]

        # Scale + predict
        X_valid_sc = scaler.transform(X_valid)
        y_pred = await loop.run_in_executor(None, model.predict, X_valid_sc)
        brinjal_proba = await loop.run_in_executor(
            None, model.brinjal_probability, X_valid_sc
        )

        # Apply NDVI filter (mark low-NDVI pixels)
        ndvi_vals = X_valid[:, FEATURE_BANDS.index("NDVI")]
        low_ndvi_mask = ndvi_vals < request.ndvi_threshold

        # Build output records
        prediction_records = []
        brinjal_ha_total = 0.0
        other_crop_ha_total = 0.0
        pixel_area_ha = (scale_meters * scale_meters) / 10_000

        for i, (lat, lon) in enumerate(coords_valid):
            cls_id = int(y_pred[i])
            prob = float(brinjal_proba[i])
            is_low_ndvi = bool(low_ndvi_mask[i])
            conf = model.confidence_level(
                prob,
                high_threshold=request.confidence_high_threshold,
                medium_threshold=request.confidence_medium_threshold,
            )
            cls_name = CLASS_NAMES[cls_id] if cls_id < len(CLASS_NAMES) else "unknown"

            if is_low_ndvi:
                cls_name = "low_vegetation"
                conf = "low"

            if cls_name == "brinjal" and prob >= request.confidence_medium_threshold:
                brinjal_ha_total += pixel_area_ha
            elif cls_name == "other_crop":
                other_crop_ha_total += pixel_area_ha

            prediction_records.append({
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "predicted_class": cls_name,
                "brinjal_probability": round(prob, 4),
                "confidence_level": conf,
                "ndvi": round(float(ndvi_vals[i]), 4) if not is_low_ndvi else round(float(ndvi_vals[i]), 4),
                "is_low_ndvi": is_low_ndvi,
                "date": analyze_cache.get("date_from", ""),
            })

        # Aggregate stats
        total_pixels = len(coords_valid)
        total_ha = total_pixels * pixel_area_ha
        vegetated_pixels = int(np.sum(~low_ndvi_mask))
        low_ndvi_pixels = int(np.sum(low_ndvi_mask))
        brinjal_pixels = sum(
            1 for r in prediction_records
            if r["predicted_class"] == "brinjal"
            and r["brinjal_probability"] >= request.confidence_medium_threshold
        )
        avg_conf = float(np.mean([
            r["brinjal_probability"] for r in prediction_records
            if r["predicted_class"] == "brinjal"
        ])) if brinjal_pixels else 0.0

        statistics = {
            "total_area_ha": round(total_ha, 2),
            "total_area_km2": round(total_ha / 100, 4),
            "vegetated_area_ha": round(vegetated_pixels * pixel_area_ha, 2),
            "vegetated_area_pct": round(100 * vegetated_pixels / max(total_pixels, 1), 2),
            "low_ndvi_area_ha": round(low_ndvi_pixels * pixel_area_ha, 2),
            "low_ndvi_area_pct": round(100 * low_ndvi_pixels / max(total_pixels, 1), 2),
            "predicted_brinjal_ha": round(brinjal_ha_total, 2),
            "predicted_brinjal_pct": round(100 * brinjal_ha_total / max(total_ha, 0.001), 2),
            "predicted_other_crop_ha": round(other_crop_ha_total, 2),
            "num_brinjal_fields": brinjal_pixels,
            "avg_brinjal_confidence": round(avg_conf, 4),
            "date_from": analyze_cache.get("date_from", ""),
            "date_to": analyze_cache.get("date_to", ""),
            "cloud_threshold": analyze_cache.get("cloud_threshold", 20),
            "ndvi_threshold": request.ndvi_threshold,
            "scale_meters": scale_meters,
        }

        result = {
            "classify_job_id": job.job_id,
            "statistics": statistics,
            "n_pixels_classified": len(prediction_records),
        }

        store_result(job.job_id, {
            **result,
            "_predictions": prediction_records,
            "_statistics": statistics,
        })

        await job_service.update_job(
            job.job_id, status=JobStatus.COMPLETED, progress=100,
            message=f"Classified {len(prediction_records)} pixels. "
                    f"Predicted brinjal: {brinjal_ha_total:.2f} ha",
            result=result,
        )

    except Exception as exc:
        logger.exception(f"[ClassifyService] Job {job.job_id} failed: {exc}")
        await job_service.update_job(
            job.job_id, status=JobStatus.FAILED,
            message="Classification failed", error=str(exc),
        )
