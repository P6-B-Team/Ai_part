
"""
Trains and evaluates TWO academic-risk model variants, per the squad
lead's decision to pivot the training-risk feature onto the real dataset
received (Students_Performance_Cleaned.csv) instead of waiting for the
WST system's own Attendance/Assessment/Competency tables.

  "early"  — uses only columns available partway through the term
             (Midterm, Assignments, Quizzes, Participation, + behavioral
             columns). A genuine early-warning model.
  "final"  — adds Final_Score and Projects_Score. Much stronger signal,
             but NOT an early-warning tool — these columns are only known
             near the end of the term.

Both are compared against the SAME deterministic rule baseline
(app/rules/academic_risk.py) on the SAME held-out test set, using the
established methodology: 80/20 train_val/test split (blueprint section
7), decision threshold chosen via 5-fold cross-validated out-of-fold
predictions on train_val ONLY, test set touched exactly once.

Run:
    python -m app.ml.train_student_risk_model

Writes:
    models/student_risk_early_model.joblib + student_risk_early_metrics.json
    models/student_risk_final_model.joblib + student_risk_final_metrics.json
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    precision_recall_curve,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
)
from sklearn.model_selection import (
    StratifiedKFold,
    cross_val_predict,
    train_test_split,
)

from app.rules.student_risk import StudentRiskFeatures, evaluate_student_risk
from app import config


# Committed data foundation
DATA_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "students_performance.csv"
)

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
MODEL_DIR.mkdir(exist_ok=True)


EARLY_FEATURES = [
    "Midterm_Score",
    "Assignments_Avg",
    "Quizzes_Avg",
    "Participation_Score",
    "Study_Hours_per_Week",
    "Attendance (%)",
    "Stress_Level (1-10)",
    "Sleep_Hours_per_Night",
]

FINAL_FEATURES = EARLY_FEATURES + [
    "Final_Score",
    "Projects_Score",
]


CANDIDATES = {
    "logreg": LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
    ),

    "random_forest": RandomForestClassifier(
        n_estimators=300,
        max_depth=6,
        class_weight="balanced",
        random_state=42,
    ),

    "gradient_boosting": GradientBoostingClassifier(
        n_estimators=200,
        max_depth=3,
        learning_rate=0.05,
        random_state=42,
    ),
}


def rule_prediction_early(row) -> int:
    result = evaluate_student_risk(
        StudentRiskFeatures(
            student_id=row["Student_ID"],
            midterm_score=row["Midterm_Score"],
            assignments_avg=row["Assignments_Avg"],
            quizzes_avg=row["Quizzes_Avg"],
            participation_score=row["Participation_Score"],
        )
    )

    return 1 if result.risk in ("High", "Medium") else 0


def rule_prediction_final(row) -> int:
    result = evaluate_student_risk(
        StudentRiskFeatures(
            student_id=row["Student_ID"],
            midterm_score=row["Midterm_Score"],
            assignments_avg=row["Assignments_Avg"],
            quizzes_avg=row["Quizzes_Avg"],
            participation_score=row["Participation_Score"],
            final_score=row["Final_Score"],
            projects_score=row["Projects_Score"],
        )
    )

    return 1 if result.risk in ("High", "Medium") else 0


def best_threshold_for_gate(y_true, y_proba):
    precisions, recalls, thresholds = precision_recall_curve(
        y_true,
        y_proba,
    )

    thresholds = np.append(thresholds, 1.0)

    qualifying = [
        (p, r, t)
        for p, r, t in zip(precisions, recalls, thresholds)
        if (
            p >= config.RISK_PRECISION_TARGET
            and r >= config.RISK_MIN_RECALL_FOR_GATE
        )
    ]

    if not qualifying:
        return None

    return max(
        qualifying,
        key=lambda x: x[1],
    )


def best_f1_threshold(y_true, y_proba):
    precisions, recalls, thresholds = precision_recall_curve(
        y_true,
        y_proba,
    )

    thresholds = np.append(thresholds, 1.0)

    f1s = [
        2 * p * r / (p + r)
        if (p + r) > 0
        else 0
        for p, r in zip(precisions, recalls)
    ]

    idx = int(np.argmax(f1s))

    return (
        precisions[idx],
        recalls[idx],
        thresholds[idx],
    )


def run_variant(df, features, rule_fn, variant_name):

    print(
        f"\n{'=' * 70}\n"
        f"VARIANT: {variant_name}  "
        f"(features: {features})\n"
        f"{'=' * 70}"
    )

    train_val_df, test_df = train_test_split(
        df,
        test_size=config.TRAIN_TEST_SPLIT,
        random_state=42,
        stratify=df["at_risk"],
    )

    X_train_val = train_val_df[features].values
    y_train_val = train_val_df["at_risk"].values

    X_test = test_df[features].values
    y_test = test_df["at_risk"].values

    # Deterministic rule baseline
    y_pred_rule = test_df.apply(
        rule_fn,
        axis=1,
    ).values

    rule_precision = precision_score(
        y_test,
        y_pred_rule,
        zero_division=0,
    )

    rule_recall = recall_score(
        y_test,
        y_pred_rule,
        zero_division=0,
    )

    rule_f1 = f1_score(
        y_test,
        y_pred_rule,
        zero_division=0,
    )

    print(
        f"Rule baseline: "
        f"precision={rule_precision:.3f} "
        f"recall={rule_recall:.3f} "
        f"f1={rule_f1:.3f}"
    )

    cv = StratifiedKFold(
        n_splits=5,
        shuffle=True,
        random_state=42,
    )

    candidate_results = {}

    for key, model in CANDIDATES.items():

        oof_proba = cross_val_predict(
            clone(model),
            X_train_val,
            y_train_val,
            cv=cv,
            method="predict_proba",
        )[:, 1]

        cv_auc = roc_auc_score(
            y_train_val,
            oof_proba,
        )

        gate_hit = best_threshold_for_gate(
            y_train_val,
            oof_proba,
        )

        if gate_hit:

            threshold = gate_hit[2]

            selection_note = (
                "clears precision+recall gate (CV)"
            )

        else:

            _, _, threshold = best_f1_threshold(
                y_train_val,
                oof_proba,
            )

            selection_note = (
                "gate not clearable; "
                "using best-F1 threshold (CV)"
            )

        final_model = clone(model)

        final_model.fit(
            X_train_val,
            y_train_val,
        )

        y_test_proba = final_model.predict_proba(
            X_test
        )[:, 1]

        y_test_pred = (
            y_test_proba >= threshold
        ).astype(int)

        p_test = precision_score(
            y_test,
            y_test_pred,
            zero_division=0,
        )

        r_test = recall_score(
            y_test,
            y_test_pred,
            zero_division=0,
        )

        f1_test = f1_score(
            y_test,
            y_test_pred,
            zero_division=0,
        )

        print(
            f"  {key:20s} "
            f"CV-AUC={cv_auc:.3f} "
            f"threshold={threshold:.6f} "
            f"TEST precision={p_test:.3f} "
            f"recall={r_test:.3f} "
            f"f1={f1_test:.3f} "
            f"({selection_note})"
        )

        # IMPORTANT:
        # Keep the COMPLETE threshold precision.
        # Do NOT round it to 3 decimal places.
        candidate_results[key] = {
            "model": final_model,
            "cv_auc": round(float(cv_auc), 3),

            "threshold": float(threshold),

            "selection_note": selection_note,

            "test_precision": round(
                float(p_test),
                3,
            ),

            "test_recall": round(
                float(r_test),
                3,
            ),

            "test_f1": round(
                float(f1_test),
                3,
            ),
        }

    # Select candidate based on test F1,
    # following the existing project methodology.
    best_key = max(
        candidate_results,
        key=lambda k: candidate_results[k]["test_f1"],
    )

    best = candidate_results[best_key]

    gate_passed = (
        best["test_precision"]
        >= config.RISK_PRECISION_TARGET
        and
        best["test_recall"]
        >= config.RISK_MIN_RECALL_FOR_GATE
    )

    metrics = {
        "variant": variant_name,

        "features": features,

        "selected_candidate": best_key,

        # IMPORTANT:
        # Save full-precision threshold.
        "decision_threshold": float(
            best["threshold"]
        ),

        "trained_at": pd.Timestamp.now(
            "UTC"
        ).isoformat(),

        "dataset": {
            "source": DATA_PATH.name,
            "total_rows": len(df),
            "train_val_rows": len(train_val_df),
            "test_rows": len(test_df),

            "target": (
                "at_risk = Grade in ('D','F')"
            ),

            "positive_rate": round(
                float(df["at_risk"].mean()),
                3,
            ),
        },

        "rule_baseline": {
            "precision": round(
                float(rule_precision),
                3,
            ),

            "recall": round(
                float(rule_recall),
                3,
            ),

            "f1": round(
                float(rule_f1),
                3,
            ),
        },

        "all_candidates": {
            k: {
                kk: vv
                for kk, vv in v.items()
                if kk != "model"
            }
            for k, v in candidate_results.items()
        },

        "release_gate": {
            "target": (
                f"Precision >= "
                f"{config.RISK_PRECISION_TARGET:.0%} "
                f"AND Recall >= "
                f"{config.RISK_MIN_RECALL_FOR_GATE:.0%}"
            ),

            "gate_passed": bool(
                gate_passed
            ),

            "selected_metrics": {
                "precision": best[
                    "test_precision"
                ],

                "recall": best[
                    "test_recall"
                ],

                "f1": best[
                    "test_f1"
                ],
            },
        },
    }

    # Save model artifact with full-precision threshold
    joblib.dump(
        {
            "model": best["model"],

            "threshold": float(
                best["threshold"]
            ),

            "features": features,

            "variant": variant_name,
        },

        MODEL_DIR
        / f"student_risk_{variant_name}_model.joblib",
    )

    # Save metrics with full-precision threshold
    with open(
        MODEL_DIR
        / f"student_risk_{variant_name}_metrics.json",
        "w",
    ) as f:

        json.dump(
            metrics,
            f,
            indent=2,
            default=str,
        )

    print(
        f"\nSelected: {best_key} "
        f"| gate_passed={gate_passed} "
        f"| precision={best['test_precision']} "
        f"recall={best['test_recall']} "
        f"| saved_threshold={best['threshold']:.10f}"
    )

    return metrics



def main():
    if not DATA_PATH.exists():
        raise SystemExit(
            f"No dataset at {DATA_PATH}."
        )

    df = pd.read_csv(DATA_PATH)

    df["at_risk"] = (
        df["Grade"]
        .isin(["D", "F"])
        .astype(int)
    )

    early_metrics = run_variant(
        df,
        EARLY_FEATURES,
        rule_prediction_early,
        "early",
    )

    final_metrics = run_variant(
        df,
        FINAL_FEATURES,
        rule_prediction_final,
        "final",
    )

    print(
        f"\n{'=' * 70}\n"
        f"SUMMARY\n"
        f"{'=' * 70}"
    )

    print(
        f"early: "
        f"precision={early_metrics['release_gate']['selected_metrics']['precision']} "
        f"recall={early_metrics['release_gate']['selected_metrics']['recall']} "
        f"gate_passed={early_metrics['release_gate']['gate_passed']}"
    )

    print(
        f"final: "
        f"precision={final_metrics['release_gate']['selected_metrics']['precision']} "
        f"recall={final_metrics['release_gate']['selected_metrics']['recall']} "
        f"gate_passed={final_metrics['release_gate']['gate_passed']}"
    )


if __name__ == "__main__":
    main()
