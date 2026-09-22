# Model Card — WST-FR-14 AI Features

This satisfies the brief's **AI release gate**: *"The AI feature may be
demonstrated only with a documented dataset split, baseline comparison,
metric, known limitations, model/version log, and a working non-AI
fallback."* Also aligned with **AI_Service_Blueprint.pdf section 7**'s
specific benchmark (Precision >= 80% on an 80/20 holdout). Each item
below, in order.

---

## Feature 1 — Training Risk (logistic regression / random forest / gradient boosting, best-of-3)

| Item | Value |
|---|---|
| Dataset split | 80% train_val / 20% test (blueprint section 7), 400 synthetic students, seed=42. Decision threshold selected via **5-fold cross-validation** on train_val; test set touched exactly once, for final reporting only. |
| Baseline | `rule-v1.0` (weighted rule engine, `app/rules/training_risk.py`) |
| Models compared | Logistic Regression, Random Forest, Gradient Boosting — see `app/ml/train_training_risk_model.py` |
| Metric | Precision / Recall on held-out test set, at a threshold chosen without ever looking at that test set |
| **Release gate** | Precision >= 80% **AND** Recall >= 40% (the recall floor is an engineering safeguard added after finding a threshold that hit 100% precision at 9% recall — see below) |
| **Result** | **Gate not met.** Best candidate (Gradient Boosting) reaches 85.7% precision but only 27.3% recall at its cross-validated threshold — clears precision, misses the recall floor. |
| Model/version log | Selected candidate and threshold logged per run in `models/training_risk_metrics.json`; artifact at `models/training_risk_model.joblib` |
| Fallback | `app/ml/model_registry.py::training_risk_usable()` requires the gate to have passed before the model is ever used live — it hasn't, so `/ai/student-risk` and `/ai/training-risk` currently always answer from the rule baseline |

### The methodology journey (reported in full, per project rule 5)

Three approaches were tried, each fixing a real flaw found in the last —
this is intentionally documented rather than only showing the final
number, because the flaws themselves are the useful finding:

| # | Approach | Result | Problem found |
|---|---|---|---|
| 1 | Pick threshold directly on the test set | 81.2% precision, 59.1% recall | **Invalid.** The test set is no longer a fair estimate once it was used to choose the threshold — this number is optimistic, not real. |
| 2 | Pick threshold on a separate 80-row validation split | Highly unstable — one candidate's "best" threshold flagged **zero** students in test | 80 rows is too few to pick a stable threshold; results swung wildly by model type. |
| 3 | Pick threshold via 5-fold cross-validation (out-of-fold predictions) on the full 320-row train_val set, evaluate once on test | Gradient Boosting: 85.7% precision / 27.3% recall | **Methodologically sound** — this is the number reported above. Clears precision, fails the recall floor. |

Approach 3 is what ships. Approaches 1 and 2 are kept in this document
specifically so a reviewer can see *why* they were rejected, not just that
they were.

### Why a recall floor was added to the gate at all

The blueprint's own target is precision-only ("Precision >= 80%"). While
testing thresholds, one candidate reached **100% precision at 9%
recall** — technically clearing the blueprint's stated target while
being nearly useless (it would miss 91% of genuinely at-risk students).
`config.RISK_MIN_RECALL_FOR_GATE = 0.40` was added specifically to stop
that kind of result from being reported as a pass. This is an addition
to the blueprint's spec, not a requirement it stated — flagged here in
case the team wants to set a different floor or discuss it explicitly
with the Tech Lead.

### What would actually move this number

Not further model tuning — three model families were tried and all
plateau in a similar range, so architecture isn't the bottleneck.
What's missing is data:

1. **More rows.** 400 synthetic students is small for reliably estimating
   an 80%-precision decision boundary; the test set alone is only 80 rows,
   so a handful of hard cases swing the reported number several points
   either way.
2. **Real labels.** The synthetic generator's `actually_incomplete` label
   has designed-in noise (see `data/generate_synthetic_data.py`) that caps
   how separable the classes can ever be, regardless of model or data
   volume. Real historical outcomes are expected to have a different —
   likely more learnable — signal-to-noise ratio.

**Recommendation:** keep the rule baseline live (it already is, and it's
working) and re-run `app/ml/train_training_risk_model.py` once real (or
a much larger seeded) student dataset is available. The script requires
no changes to do this — same CSV shape, same command.

## Feature 2 — Reorder Demand Forecast (evaluation only, not live yet)

| Item | Value |
|---|---|
| Dataset split | Per-SKU: all but last 4 weeks for training, last 4 weeks held out for evaluation; 60 synthetic parts, 26 weeks each |
| Baseline | 4-week moving average |
| Metric | MAE and WAPE, aggregated across all SKUs |
| Result | Model WAPE **0.154** vs baseline WAPE **0.173** → model beats baseline on this synthetic set |
| Model/version log | `reorder-forecast-v1.0-linreg`, evaluated via `app/ml/train_reorder_forecast.py`, metrics at `models/reorder_forecast_metrics.json` (no live model artifact — evaluation-only per current scope) |
| Known limitations | Synthetic seasonality is simple (single sine term); this evaluation still runs on synthetic weekly history, not the real `parts_data.csv` snapshot (which has no time dimension — see note below); linear regression on raw lags has no holiday/promotion calendar |
| Fallback | Not wired into the live `/ai/predict-reorder` endpoint — the rule-based Section-2 logic in the design document remains the only thing driving that endpoint today |

---

## Real data received so far: `parts_data.csv`

This is the **first real (non-synthetic) data** the AI Module has
processed — 100 real parts. Because it's a single point-in-time snapshot
(one row per part, `monthly_usage` as a scalar) rather than a weekly time
series, it's directly usable by the **reorder rule engine** (which only
needs current levels + an average consumption rate) but **not** by the
demand-forecast model above (which needs multiple weeks of history per
SKU to learn a trend). Processed via `data/process_real_parts_data.py`
(`monthly_usage` converted to weekly by dividing by 4.345):

| Result | Value |
|---|---|
| Parts processed | 100 |
| High risk | 15 |
| Medium risk | 14 |
| Low risk | 71 |
| Parts needing reorder | 31 / 100 |

**Real-data edge case found and fixed:** 7 of the 100 parts have
`reserved_quantity > stock_quantity` (already over-committed to open job
cards). The original engine computed a technically-correct but confusing
negative "weeks of cover" figure for these; `app/rules/reorder.py` now
detects this case and reports it plainly ("Stock is over-reserved by N
unit(s)") instead. Covered by
`tests/test_reorder.py::test_over_reserved_stock_flagged_high_with_clear_reason`.

Full per-part output: `data/reorder_suggestions_output.csv`.

**Still needed for training-risk retraining:** real (or seeded) student
data with the same shape as `data/synthetic_students_training_history.csv`
— `student_id, attendance_rate, unsigned_assessments,
missing_competencies, actual_time_on_task, expected_time_on_task,
actually_incomplete` (the last column is the ground-truth outcome, needed
only for retraining, not for live predictions).

---

---

## Exploratory Work — NOT part of the WST-FR-14 deliverable

A file named `Students_Performance_Cleaned.csv` was received and
initially treated as WST training data. Once the real database schema
(`wst_schema.sql`) arrived, it became clear this file has **no
relationship to the WST database** — none of its columns
(Midterm_Score, Final_Score, Grade, etc.) exist in the real
`students`/`attendances`/`assessments`/`competencies` tables. It's a
generic public academic-performance dataset, unrelated to this project.

Two model variants were built and evaluated on it anyway
(`app/exploratory/`), as a legitimate methodology exercise: comparing
model families, cross-validated threshold selection, and honestly
reporting a red flag (one variant hit AUC=1.000, a sign it was
reconstructing a linear formula rather than genuinely predicting an
uncertain outcome — see `app/exploratory/train_academic_risk_model.py`
for the full trade-off numbers). **These results should not be quoted as
WST-FR-14 model performance** — they describe an unrelated dataset.

The actual WST-FR-14 training-risk model (`app/rules/training_risk.py`,
`app/ml/train_training_risk_model.py`) is untouched and remains correct
— its feature set is now *confirmed* (not just assumed) to match the
real database, per the mapping tables in `DATA_REQUIREMENTS_SPEC.md`.

---

## Why both features still ship a working baseline

Per the project's shipping rule #5, and the blueprint's own architecture
("Check Baseline / Fallback Gate -> Execute ML Model / Rule Baseline"):
the rule engine is not a placeholder — it is what actually answers every
`/ai/predict-reorder` call today, and every `/ai/student-risk` call until
a future retrain clears the precision release gate.
