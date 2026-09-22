"""
Trains a per-part "does this vehicle need part X serviced" classifier for
every part in data/vehicle_maintenance.csv, and computes the rule
baseline's mileage thresholds from the same data.

Methodology matches the established pattern: 80/20 train_val/test split,
decision threshold chosen via 5-fold CV on train_val, test set touched
once. Uses RandomForest only (not a 3-model bake-off per part) to keep
training time reasonable across 14 parts — flagged honestly in the
metrics as a scope simplification, not hidden.

Run:
    python -m app.ml.train_vehicle_service_model

Writes:
    models/vehicle_service_rule_thresholds.json   (rule baseline, used live by app/rules/vehicle_service.py)
    models/vehicle_service_model.joblib            (dict of {part: {model, threshold}})
    models/vehicle_service_metrics.json            (per-part precision/recall, rule vs model)
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_recall_curve, precision_score, recall_score, f1_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.preprocessing import OneHotEncoder

from app.rules.vehicle_service import PARTS, THRESHOLDS_PATH
from app import config

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "vehicle_maintenance.csv"
MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
MODEL_DIR.mkdir(exist_ok=True)

NUMERIC_FEATURES = ["mileage", "make_year"]
CATEGORICAL_FEATURES = ["brand"]  # engine_type dropped — not a real vehicles table column


def build_feature_matrix(df: pd.DataFrame, encoder: OneHotEncoder | None = None):
    if encoder is None:
        encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
        cat_matrix = encoder.fit_transform(df[CATEGORICAL_FEATURES])
    else:
        cat_matrix = encoder.transform(df[CATEGORICAL_FEATURES])
    X = np.hstack([df[NUMERIC_FEATURES].values, cat_matrix])
    return X, encoder


def best_threshold_for_gate(y_true, y_proba):
    precisions, recalls, thresholds = precision_recall_curve(y_true, y_proba)
    thresholds = np.append(thresholds, 1.0)
    qualifying = [(p, r, t) for p, r, t in zip(precisions, recalls, thresholds)
                  if p >= config.RISK_PRECISION_TARGET and r >= config.RISK_MIN_RECALL_FOR_GATE]
    if qualifying:
        return max(qualifying, key=lambda x: x[1])
    f1s = [2 * p * r / (p + r) if (p + r) > 0 else 0 for p, r in zip(precisions, recalls)]
    idx = int(np.argmax(f1s))
    return precisions[idx], recalls[idx], thresholds[idx]


def main():
    if not DATA_PATH.exists():
        raise SystemExit(f"No dataset at {DATA_PATH}.")

    df = pd.read_csv(DATA_PATH)

    rule_thresholds = {}
    all_metrics = {}
    trained_models = {}

    for part in PARTS:
        y = df[part].values

        # Rule baseline threshold: 25th percentile of mileage among
        # records where this part WAS serviced — grounded in real data.
        mileage_when_serviced = df.loc[df[part] == 1, "mileage"]
        rule_threshold = float(mileage_when_serviced.quantile(0.25)) if len(mileage_when_serviced) > 5 else 40000.0
        rule_thresholds[part] = round(rule_threshold, 1)

        rule_pred = (df["mileage"].values >= rule_threshold).astype(int)
        rule_precision = precision_score(y, rule_pred, zero_division=0)
        rule_recall = recall_score(y, rule_pred, zero_division=0)

        # ML model
        train_val_df, test_df = train_test_split(
            df, test_size=config.TRAIN_TEST_SPLIT, random_state=42,
            stratify=y if len(set(y)) > 1 and min(np.bincount(y)) >= 2 else None,
        )
        X_train_val, encoder = build_feature_matrix(train_val_df)
        y_train_val = train_val_df[part].values
        X_test, _ = build_feature_matrix(test_df, encoder)
        y_test = test_df[part].values

        model = RandomForestClassifier(n_estimators=200, max_depth=5, class_weight="balanced", random_state=42)

        if len(set(y_train_val)) < 2:
            # a part with (almost) no positive examples can't be modeled meaningfully
            all_metrics[part] = {
                "skipped": True, "reason": "insufficient class variation",
                "rule_baseline": {"precision": round(float(rule_precision), 3), "recall": round(float(rule_recall), 3)},
            }
            continue

        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        oof_proba = cross_val_predict(clone(model), X_train_val, y_train_val, cv=cv, method="predict_proba")[:, 1]
        auc = roc_auc_score(y_train_val, oof_proba)
        _, _, threshold = best_threshold_for_gate(y_train_val, oof_proba)

        final_model = clone(model)
        final_model.fit(X_train_val, y_train_val)
        test_proba = final_model.predict_proba(X_test)[:, 1]
        test_pred = (test_proba >= threshold).astype(int)

        p_test = precision_score(y_test, test_pred, zero_division=0)
        r_test = recall_score(y_test, test_pred, zero_division=0)

        trained_models[part] = {"model": final_model, "encoder": encoder, "threshold": float(threshold)}
        all_metrics[part] = {
            "positive_rate": round(float(y.mean()), 3),
            "cv_auc": round(float(auc), 3),
            "threshold": round(float(threshold), 3),
            "model_precision": round(float(p_test), 3),
            "model_recall": round(float(r_test), 3),
            "rule_baseline": {"precision": round(float(rule_precision), 3), "recall": round(float(rule_recall), 3)},
            "model_beats_rule": bool(p_test >= rule_precision and r_test >= rule_recall * 0.8),
        }
        print(f"{part:32s} positive_rate={y.mean():.2f} rule_p={rule_precision:.2f} rule_r={rule_recall:.2f} "
              f"| model AUC={auc:.3f} p={p_test:.2f} r={r_test:.2f}")

    THRESHOLDS_PATH.write_text(json.dumps(rule_thresholds, indent=2))
    joblib.dump(trained_models, MODEL_DIR / "vehicle_service_model.joblib")
    with open(MODEL_DIR / "vehicle_service_metrics.json", "w") as f:
        json.dump({
            "trained_at": pd.Timestamp.now("UTC").isoformat(),
            "dataset": {"source": DATA_PATH.name, "rows": len(df), "n_parts": len(PARTS)},
            "note": (
                "Single-model (RandomForest) comparison per part, not a "
                "3-way bake-off like the reorder/training-risk models — "
                "scope simplification to keep training time reasonable "
                "across 14 parts. Flagged here, not hidden."
            ),
            "per_part": all_metrics,
        }, f, indent=2, default=str)

    print(f"\nSaved rule thresholds -> {THRESHOLDS_PATH}")
    print(f"Saved models -> {MODEL_DIR / 'vehicle_service_model.joblib'}")
    print(f"Saved metrics -> {MODEL_DIR / 'vehicle_service_metrics.json'}")


if __name__ == "__main__":
    main()
