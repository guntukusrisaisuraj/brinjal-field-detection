"""
Pre-processing utilities: feature scaling, train/validation split,
class validation, and feature frame manipulation.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from app.ml.random_forest import CLASS_NAMES
from app.utils.logger import logger

MIN_SAMPLES_PER_CLASS = 5  # Warn if fewer than this


def validate_classes(y: np.ndarray) -> Dict[str, int]:
    """
    Check that each expected class has sufficient samples.

    Returns dict of {class_name: count}.
    Raises ValueError if mandatory classes are missing.
    """
    unique, counts = np.unique(y, return_counts=True)
    class_counts = {CLASS_NAMES[int(c)]: int(n) for c, n in zip(unique, counts)}

    warnings = []
    for name, count in class_counts.items():
        if count < MIN_SAMPLES_PER_CLASS:
            warnings.append(
                f"Class '{name}' has only {count} samples "
                f"(minimum recommended: {MIN_SAMPLES_PER_CLASS})"
            )

    if warnings:
        for w in warnings:
            logger.warning(f"[Preprocessing] {w}")

    # Must have brinjal class
    if "brinjal" not in class_counts:
        raise ValueError(
            "Training data must contain at least one 'brinjal' sample. "
            "Cannot train a brinjal classifier without positive examples."
        )

    if len(class_counts) < 2:
        raise ValueError(
            "Training data must contain at least 2 distinct classes. "
            f"Only found: {list(class_counts.keys())}"
        )

    return class_counts


def split_train_val(
    X: np.ndarray,
    y: np.ndarray,
    test_size: float = 0.25,
    random_state: int = 42,
    stratify: bool = True,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Stratified train/validation split.

    Uses stratified splitting to maintain class proportions.
    NOTE: For rigorous spatial validation, use spatially-aware splitting
    (e.g., separate geographic areas for training vs. validation).
    This implementation uses random stratified splitting as a baseline.
    """
    strat = y if stratify else None
    X_train, X_val, y_train, y_val = train_test_split(
        X, y,
        test_size=test_size,
        random_state=random_state,
        stratify=strat,
    )
    logger.info(
        f"[Preprocessing] Train: {len(X_train)}, Val: {len(X_val)}"
    )
    return X_train, X_val, y_train, y_val


def scale_features(
    X_train: np.ndarray,
    X_val: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, StandardScaler]:
    """
    Fit StandardScaler on training data and transform both sets.
    Note: Random Forest is largely scale-invariant, but scaling helps
    when features have very different ranges.
    """
    scaler = StandardScaler()
    X_train_sc = scaler.fit_transform(X_train)
    X_val_sc = scaler.transform(X_val)
    return X_train_sc, X_val_sc, scaler


def class_sample_report(y: np.ndarray) -> List[Dict[str, int]]:
    """Return per-class sample counts as a list of dicts."""
    unique, counts = np.unique(y, return_counts=True)
    return [
        {"class_name": CLASS_NAMES[int(c)], "count": int(n)}
        for c, n in zip(unique, counts)
    ]
