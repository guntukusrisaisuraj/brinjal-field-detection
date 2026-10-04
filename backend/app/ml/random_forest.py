"""
Random Forest classifier for brinjal crop detection.

Uses scikit-learn RandomForestClassifier with per-class probability output.

CLASS MAPPING:
  0 = brinjal
  1 = other_crop
  2 = bare_soil
  3 = built_up
  4 = water
  5 = other_vegetation
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.exceptions import NotFittedError

from app.utils.logger import logger

ALPHAEARTH_COLLECTION = "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"
ALPHAEARTH_FEATURE_NAMES = [f"AE_{index:02d}" for index in range(1, 65)]

CLASS_NAMES = ["brinjal", "other_crop", "bare_soil", "built_up", "water", "other_vegetation"]
CLASS_MAP = {name: idx for idx, name in enumerate(CLASS_NAMES)}
BRINJAL_CLASS_ID = 0

MODEL_DIR = os.getenv("MODEL_DIR", "./saved_models")


# ---------------------------------------------------------------------------
# Model wrapper
# ---------------------------------------------------------------------------

class BrinjalRandomForest:
    """Wrapper around sklearn RandomForestClassifier."""

    def __init__(
        self,
        n_estimators: int = 200,
        max_depth: Optional[int] = None,
        min_samples_split: int = 5,
        random_state: int = 42,
        n_jobs: int = -1,
        alphaearth_enabled: bool = False,
    ) -> None:
        self.model_id = str(uuid.uuid4())
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.random_state = random_state
        self.feature_names: list[str] = []
        self.alphaearth_enabled = bool(alphaearth_enabled)
        self.alphaearth_collection = ALPHAEARTH_COLLECTION
        self.alphaearth_dimensions = 64
        self.alphaearth_feature_names = list(ALPHAEARTH_FEATURE_NAMES)
        self.trained_at: Optional[str] = None
        self._clf = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_split=min_samples_split,
            random_state=random_state,
            n_jobs=n_jobs,
            class_weight="balanced",       # handles class imbalance
            oob_score=True,                # out-of-bag estimate
            verbose=0,
        )

    # ------------------------------------------------------------------ #
    #  Training
    # ------------------------------------------------------------------ #

    def train(self, X_train: np.ndarray, y_train: np.ndarray,
              feature_names: list[str]) -> None:
        """Fit the Random Forest."""
        if X_train.ndim != 2 or X_train.shape[1] != len(feature_names):
            raise ValueError("Feature matrix width does not match the recorded feature schema.")
        includes_alphaearth = any(name.startswith("AE_") for name in feature_names)
        if includes_alphaearth != self.alphaearth_enabled:
            raise ValueError("AlphaEarth feature columns and model metadata do not match.")
        if includes_alphaearth and [
            name for name in feature_names if name.startswith("AE_")
        ] != self.alphaearth_feature_names:
            raise ValueError("Expected AlphaEarth feature columns AE_01 through AE_64 in order.")
        logger.info(
            f"[RF] Training with {X_train.shape[0]} samples, "
            f"{X_train.shape[1]} features, {self.n_estimators} trees"
        )
        self.feature_names = feature_names
        self._clf.fit(X_train, y_train)
        self.trained_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            f"[RF] OOB accuracy: {self._clf.oob_score_:.4f}"
        )

    # ------------------------------------------------------------------ #
    #  Prediction
    # ------------------------------------------------------------------ #

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Return predicted class IDs."""
        return self._clf.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Return class probabilities (n_samples × n_classes)."""
        return self._clf.predict_proba(X)

    def brinjal_probability(self, X: np.ndarray) -> np.ndarray:
        """
        Return brinjal probability for each sample.

        This is the probability of class 0 (brinjal), NOT a confirmed
        identification. Interpretation:
          HIGH   (≥ 0.75): Predicted brinjal, high confidence
          MEDIUM (0.50–0.74): Predicted brinjal, medium confidence
          LOW    (< 0.50): Uncertain / likely not brinjal
        """
        proba = self.predict_proba(X)
        brinjal_col = list(self._clf.classes_).index(BRINJAL_CLASS_ID) \
            if BRINJAL_CLASS_ID in self._clf.classes_ else 0
        return proba[:, brinjal_col]

    def confidence_level(
        self,
        probability: float,
        high_threshold: float = 0.75,
        medium_threshold: float = 0.50,
    ) -> str:
        if probability >= high_threshold:
            return "high"
        elif probability >= medium_threshold:
            return "medium"
        return "low"

    # ------------------------------------------------------------------ #
    #  Feature importances
    # ------------------------------------------------------------------ #

    def feature_importances_dict(self) -> Dict[str, float]:
        importances = self._clf.feature_importances_
        return {
            name: float(round(imp, 6))
            for name, imp in sorted(
                zip(self.feature_names, importances),
                key=lambda x: x[1],
                reverse=True,
            )
        }

    # ------------------------------------------------------------------ #
    #  Persistence
    # ------------------------------------------------------------------ #

    def save(self, directory: str = MODEL_DIR) -> str:
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"rf_{self.model_id}.joblib")
        joblib.dump(self, path)
        logger.info(f"[RF] Model saved: {path}")
        return path

    @staticmethod
    def load(path: str) -> "BrinjalRandomForest":
        model = joblib.load(path)
        logger.info(f"[RF] Model loaded: {path}")
        return model

    def is_trained(self) -> bool:
        try:
            self._clf.predict([[0] * len(self.feature_names)])
            return True
        except NotFittedError:
            return False

    def classes_(self) -> list[int]:
        return list(self._clf.classes_)


# ---------------------------------------------------------------------------
# In-memory model registry
# ---------------------------------------------------------------------------

_model_registry: Dict[str, BrinjalRandomForest] = {}


def register_model(model: BrinjalRandomForest) -> None:
    _model_registry[model.model_id] = model


def get_model(model_id: str) -> Optional[BrinjalRandomForest]:
    return _model_registry.get(model_id)
