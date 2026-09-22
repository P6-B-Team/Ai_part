"""
Loads trained model artifacts lazily, and behaves safely if they don't
exist yet (fresh checkout, or Week-4 work hasn't run) — this is part of
the fallback story: the API must work with ZERO trained models present,
using the rule baseline only.
"""
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ai_service.model_registry")

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"

_training_risk_model = None
_training_risk_threshold = 0.5
_training_risk_metrics: Optional[dict] = None
_load_attempted = False


def _try_load():
    global _training_risk_model, _training_risk_threshold, _training_risk_metrics, _load_attempted
    if _load_attempted:
        return
    _load_attempted = True

    model_path = MODEL_DIR / "training_risk_model.joblib"
    metrics_path = MODEL_DIR / "training_risk_metrics.json"

    if model_path.exists():
        try:
            import joblib
            bundle = joblib.load(model_path)
            _training_risk_model = bundle["model"]
            _training_risk_threshold = bundle.get("threshold", 0.5)
            logger.info(
                "Loaded training-risk model %s (decision threshold=%.3f)",
                bundle.get("version"), _training_risk_threshold,
            )
        except Exception:
            logger.exception("Failed to load training-risk model; continuing rule-only")
            _training_risk_model = None

    if metrics_path.exists():
        try:
            _training_risk_metrics = json.loads(metrics_path.read_text())
        except Exception:
            logger.exception("Failed to load training-risk metrics")


def training_risk_model_available() -> bool:
    _try_load()
    return _training_risk_model is not None


def training_risk_release_gate_passed() -> bool:
    """
    Per AI_Service_Blueprint.pdf section 5, step 4: "Run trained
    Scikit-Learn ML Model if data quality meets release gate." A model
    file existing is not the same as it having cleared the release gate
    (blueprint section 7: Precision >= 80% on the 80/20 holdout). This is
    what actually gates live traffic — see training_risk_usable() below.
    """
    metrics = training_risk_metrics()
    if not metrics:
        return False
    return bool(metrics.get("release_gate", {}).get("gate_passed", False))


def training_risk_usable() -> bool:
    """True only when there's a loaded model AND it cleared the release
    gate. This is the single check live endpoints should use to decide
    whether to route to the model at all."""
    return training_risk_model_available() and training_risk_release_gate_passed()


def training_risk_metrics() -> Optional[dict]:
    _try_load()
    return _training_risk_metrics


def predict_training_risk(feature_vector: list[float]) -> tuple[str, float]:
    """Returns (risk_label, probability_of_high_risk), using the
    decision threshold the training script selected (see
    train_training_risk_model.py's best_threshold_for_gate) rather than a
    hard-coded 0.5 — a model trained specifically to clear the precision
    gate at threshold 0.75 should be evaluated at 0.75 live too. Caller
    must check training_risk_model_available() first."""
    _try_load()
    if _training_risk_model is None:
        raise RuntimeError("training risk model not loaded")
    proba = _training_risk_model.predict_proba([feature_vector])[0][1]
    label = "High" if proba >= _training_risk_threshold else "Low"
    return label, float(proba)


_student_risk_bundle = None
_student_risk_load_attempted = False


def _load_student_risk():
    global _student_risk_bundle, _student_risk_load_attempted
    if _student_risk_load_attempted:
        return
    _student_risk_load_attempted = True
    path = MODEL_DIR / "student_risk_final_model.joblib"
    if not path.exists():
        path = MODEL_DIR / "student_risk_early_model.joblib"
    if path.exists():
        try:
            import joblib
            _student_risk_bundle = joblib.load(path)
            logger.info("Loaded student risk model: %s", path.name)
        except Exception:
            logger.exception("Failed to load student risk model")


def student_risk_model_available() -> bool:
    _load_student_risk()
    return _student_risk_bundle is not None


def predict_student_risk(feature_vector: list[float]) -> tuple[str, float]:
    _load_student_risk()
    if _student_risk_bundle is None:
        raise RuntimeError("student risk model not loaded")
    model = _student_risk_bundle["model"]
    threshold = _student_risk_bundle["threshold"]
    proba = model.predict_proba([feature_vector])[0][1]
    label = "High" if proba >= threshold else "Low"
    return label, float(proba)


_vehicle_service_bundle = None
_vehicle_service_load_attempted = False


def _load_vehicle_service():
    global _vehicle_service_bundle, _vehicle_service_load_attempted
    if _vehicle_service_load_attempted:
        return
    _vehicle_service_load_attempted = True
    path = MODEL_DIR / "vehicle_service_model.joblib"
    if path.exists():
        try:
            import joblib
            _vehicle_service_bundle = joblib.load(path)
            logger.info("Loaded vehicle service models for %d parts", len(_vehicle_service_bundle))
        except Exception:
            logger.exception("Failed to load vehicle service models")


def vehicle_service_models_available() -> bool:
    _load_vehicle_service()
    return _vehicle_service_bundle is not None


def predict_vehicle_part(part: str, mileage: float, year, make):
    """Returns probability for one part, or None if that part has no
    trained model (e.g. oil_filter/engine_oil — near-universal, rule-only).
    Parameter names match wst_schema.sql's vehicles table (mileage, year,
    make) — no engine_type, since that column doesn't exist there."""
    _load_vehicle_service()
    if _vehicle_service_bundle is None or part not in _vehicle_service_bundle:
        return None
    import numpy as np
    entry = _vehicle_service_bundle[part]
    model, encoder, threshold = entry["model"], entry["encoder"], entry["threshold"]
    import pandas as pd
    cat_df = pd.DataFrame([{"brand": make}])  # CSV's training column is named "brand"; API/schema calls it "make"
    cat_encoded = encoder.transform(cat_df)
    X = np.hstack([[[mileage, year or 2020]], cat_encoded])
    proba = model.predict_proba(X)[0][1]
    return float(proba), float(threshold)


def reorder_forecast_metrics() -> Optional[dict]:
    metrics_path = MODEL_DIR / "reorder_forecast_metrics.json"
    if not metrics_path.exists():
        return None
    try:
        return json.loads(metrics_path.read_text())
    except Exception:
        logger.exception("Failed to load reorder forecast metrics")
        return None
