"""
Model evaluation – accuracy, precision, recall, F1, confusion matrix.

All metrics are computed from actual training/validation data.
No fabricated or hard-coded values.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from app.ml.random_forest import CLASS_NAMES
from app.utils.logger import logger


def evaluate_model(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    class_ids_present: list[int],
) -> Dict[str, Any]:
    """
    Compute full classification metrics.

    Parameters
    ----------
    y_true : ndarray
        True class IDs.
    y_pred : ndarray
        Predicted class IDs.
    class_ids_present : list of int
        Class IDs actually present in the validation set.

    Returns
    -------
    dict containing accuracy, precision, recall, F1, confusion matrix,
    and per-class metrics.
    """
    labels = class_ids_present
    names_present = [CLASS_NAMES[i] for i in labels]

    overall_acc = float(accuracy_score(y_true, y_pred))
    macro_prec = float(precision_score(y_true, y_pred, average="macro",
                                        labels=labels, zero_division=0))
    macro_rec = float(recall_score(y_true, y_pred, average="macro",
                                    labels=labels, zero_division=0))
    macro_f1 = float(f1_score(y_true, y_pred, average="macro",
                               labels=labels, zero_division=0))

    cm = confusion_matrix(y_true, y_pred, labels=labels).tolist()

    report = classification_report(
        y_true, y_pred,
        labels=labels,
        target_names=names_present,
        output_dict=True,
        zero_division=0,
    )

    per_class: List[Dict[str, Any]] = []
    for name in names_present:
        r = report.get(name, {})
        per_class.append({
            "crop_class": name,
            "precision": round(r.get("precision", 0.0), 4),
            "recall": round(r.get("recall", 0.0), 4),
            "f1_score": round(r.get("f1-score", 0.0), 4),
            "support": int(r.get("support", 0)),
        })

    logger.info(
        f"[Evaluation] Accuracy={overall_acc:.4f} | "
        f"F1={macro_f1:.4f} | "
        f"Precision={macro_prec:.4f} | "
        f"Recall={macro_rec:.4f}"
    )

    return {
        "overall_accuracy": round(overall_acc, 4),
        "macro_precision": round(macro_prec, 4),
        "macro_recall": round(macro_rec, 4),
        "macro_f1": round(macro_f1, 4),
        "confusion_matrix": cm,
        "class_names": names_present,
        "class_metrics": per_class,
    }
