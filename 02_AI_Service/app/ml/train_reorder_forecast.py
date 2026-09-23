"""
Compares a simple demand-forecast model against the moving-average
baseline for parts consumption, using MAE and WAPE by SKU — exactly the
metric the brief names for this feature:

    "If sufficient clean history exists, compare a simple demand-forecast
    model against the moving-average baseline, using MAE or WAPE by
    SKU/category."

This is the Reorder Suggestion engine's Week-4 stretch counterpart to the
training-risk model above. It does NOT replace the live rule engine
(app/rules/reorder.py) — that stays the deterministic MVP baseline. This
script is the documented comparison a Data/BI teammate would run to
decide whether a trained forecast is worth adopting later.

Run:
    python -m app.ml.train_reorder_forecast

Writes:
    models/reorder_forecast_metrics.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "synthetic_parts_consumption_history.csv"
MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
MODEL_DIR.mkdir(exist_ok=True)

FORECAST_VERSION = "reorder-forecast-v1.0-linreg"
WINDOW = 4          # weeks used for the moving-average baseline
LOOKBACK = 4         # weeks of lag features fed to the model
HOLDOUT_WEEKS = 4    # last N weeks per part reserved for evaluation


def moving_average_baseline(series: np.ndarray, window: int) -> np.ndarray:
    """Predicts week t as the mean of the previous `window` weeks."""
    preds = np.zeros(len(series))
    for t in range(len(series)):
        if t < window:
            preds[t] = series[:t].mean() if t > 0 else series[0]
        else:
            preds[t] = series[t - window:t].mean()
    return preds


def build_lag_features(series: np.ndarray, lookback: int):
    X, y = [], []
    for t in range(lookback, len(series)):
        X.append(series[t - lookback:t])
        y.append(series[t])
    return np.array(X), np.array(y)


def wape(y_true, y_pred) -> float:
    denom = np.sum(np.abs(y_true))
    if denom == 0:
        return 0.0
    return float(np.sum(np.abs(y_true - y_pred)) / denom)


def mae(y_true, y_pred) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))


def main():
    if not DATA_PATH.exists():
        raise SystemExit(
            f"No synthetic data at {DATA_PATH}. Run "
            "`python -m data.generate_synthetic_data` first."
        )

    df = pd.read_csv(DATA_PATH).sort_values(["part_id", "week"])

    all_X, all_y = [], []
    per_part_results = []

    for part_id, g in df.groupby("part_id"):
        series = g["weekly_consumption"].values
        if len(series) < LOOKBACK + HOLDOUT_WEEKS + 2:
            continue  # not enough history for this SKU yet

        # Baseline over the whole series (evaluated on the holdout tail)
        baseline_preds = moving_average_baseline(series, WINDOW)

        # Lag-feature model, trained on everything except the holdout tail
        X, y = build_lag_features(series, LOOKBACK)
        n_holdout = HOLDOUT_WEEKS
        X_train, y_train = X[:-n_holdout], y[:-n_holdout]
        X_test, y_test = X[-n_holdout:], y[-n_holdout:]

        if len(X_train) < 5:
            continue

        model = LinearRegression()
        model.fit(X_train, y_train)
        model_preds = model.predict(X_test)

        baseline_test = baseline_preds[-n_holdout:]
        actual_test = series[-n_holdout:]

        all_X.append((y_test, model_preds))
        per_part_results.append({
            "part_id": part_id,
            "model_mae": round(mae(actual_test, model_preds), 3),
            "baseline_mae": round(mae(actual_test, baseline_test), 3),
            "model_wape": round(wape(actual_test, model_preds), 3),
            "baseline_wape": round(wape(actual_test, baseline_test), 3),
        })

    # Aggregate across all SKUs
    all_actual = np.concatenate([r[0] for r in all_X])
    all_model_pred = np.concatenate([r[1] for r in all_X])
    # rebuild aggregate baseline predictions aligned the same way
    agg_baseline = []
    for part_id, g in df.groupby("part_id"):
        series = g["weekly_consumption"].values
        if len(series) < LOOKBACK + HOLDOUT_WEEKS + 2:
            continue
        baseline_preds = moving_average_baseline(series, WINDOW)
        agg_baseline.append(baseline_preds[-HOLDOUT_WEEKS:])
    agg_baseline = np.concatenate(agg_baseline)

    metrics = {
        "forecast_version": FORECAST_VERSION,
        "trained_at": pd.Timestamp.now("UTC").isoformat(),
        "dataset": {
            "source": str(DATA_PATH.name),
            "n_parts_evaluated": len(per_part_results),
            "holdout_weeks_per_part": HOLDOUT_WEEKS,
            "note": "100% synthetic data, per project rule 'Synthetic data only'.",
        },
        "aggregate_evaluation": {
            "model": {
                "mae": round(mae(all_actual, all_model_pred), 3),
                "wape": round(wape(all_actual, all_model_pred), 3),
            },
            "moving_average_baseline": {
                "mae": round(mae(all_actual, agg_baseline), 3),
                "wape": round(wape(all_actual, agg_baseline), 3),
            },
        },
        "model_beats_baseline": wape(all_actual, all_model_pred) < wape(all_actual, agg_baseline),
        "per_sku_sample": per_part_results[:5],
        "known_limitations": [
            "Trained on synthetic seasonal/trend patterns; real consumption "
            "may be spikier (e.g. campaign-driven repairs) than this generator models.",
            "Only 26 weeks of synthetic history per part — short for reliably "
            "detecting yearly seasonality.",
            "Linear regression on raw lags is a simple stretch baseline, "
            "not a production forecasting model (no holiday/promo calendar).",
        ],
    }

    with open(MODEL_DIR / "reorder_forecast_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    print(json.dumps(metrics, indent=2, default=str))
    print(f"\nSaved metrics -> {MODEL_DIR / 'reorder_forecast_metrics.json'}")


if __name__ == "__main__":
    main()
