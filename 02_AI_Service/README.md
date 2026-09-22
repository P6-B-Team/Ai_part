# Workshop AI Module — WST-FR-14

Rule-based baseline for **Reorder Suggestion** and **Training Risk Flag**,
per `AI_Design_Document.docx`. This is the Week 2–3 deliverable: Rule
Engine + FastAPI service + Swagger docs.

## Structure

```
app/
  config.py            thresholds & weights (tune without touching logic)
  rules/
    reorder.py          reorder rule engine (pure functions, unit-testable)
    training_risk.py     training-risk rule engine
  schemas.py             Pydantic request/response models
  fallback.py             graceful-degradation wrapper for endpoints
  prediction_log.py       in-memory audit trail (inputs/version/decision/outcome)
  main.py                 FastAPI app — the actual /ai/* endpoints
tests/
  test_reorder.py
  test_training_risk.py
Dockerfile               container image (matches the project's Docker stack)
docker-compose.yml        standalone run/test of just this service
BACKEND_INTEGRATION.md    how the Node.js Backend should call this service, incl. the fallback pattern
```

## Run it

### Option A — local Python

```bash
cd ai_service
python -m venv venv && source venv/bin/activate     # optional but recommended
pip install -r requirements.txt

uvicorn app.main:app --reload --port 8001
```

### Option B — Docker

```bash
cd ai_service
docker compose up --build
```

To run it as part of the main project's `docker-compose.yml` instead of
standalone, copy the `ai-service` block from this folder's
`docker-compose.yml` into the root compose file so it joins the same
network as `backend`/`frontend`/`db`. See `BACKEND_INTEGRATION.md` for how
the Node.js Backend should then call it.

Swagger / interactive docs: **http://localhost:8001/docs**
(this *is* the Swagger deliverable — FastAPI generates it automatically
from the Pydantic schemas, nothing else to write).

## Run the tests

```bash
pytest -v
```

## Endpoints

**Blueprint contract** (recommended, matches `AI_Service_Blueprint.pdf`,
requires `X-Internal-Token` header):

| Method | Path | Purpose |
|---|---|---|
| POST | `/ai/predict-reorder` | Single-part reorder suggestion (camelCase body) |
| POST | `/ai/student-risk` | Single-student risk flag (camelCase body) |

**Legacy contract** (original design doc, also auth-protected):

| Method | Path | Purpose |
|---|---|---|
| POST | `/ai/reorder` | Single-part reorder suggestion (snake_case body) |
| POST | `/ai/training-risk` | Single-student risk flag (snake_case body) |

**Shared, no auth required:**

| Method | Path | Purpose |
|---|---|---|
| GET | `/ai/reorder-alerts` | Current Medium/High alerts for the dashboard |
| GET | `/ai/predictions` | Full audit trail (Prediction log) |
| GET | `/ai/model-info` | Release-gate status, metrics, versions |
| POST | `/ai/predictions/{id}/decision` | Record accept/override, for the acceptance-rate metric |
| GET | `/health` | Liveness check |

See `BACKEND_INTEGRATION.md` for the auth header and full request/response
examples.

## What's a placeholder vs. what's real

- **Real, matches the design doc exactly:** the rule logic in `rules/`, the
  JSON shapes, the fallback behavior, the audit-log fields.
- **Placeholder, needs Backend/DB integration later:** `prediction_log.py`
  is in-memory (replace with a write to the real `Prediction` table), and
  the two `/ai/reorder` and `/ai/training-risk` endpoints take the full
  input in the request body rather than looking a `part_id`/`student_id`
  up in Postgres — that lookup is the Backend team's side of the contract.

## Week 4 — optional model layer (done)

```bash
# 1. Generate synthetic data (required — no real data ever committed)
python -m data.generate_synthetic_data

# 2. Train + evaluate the training-risk model against the rule baseline
python -m app.ml.train_training_risk_model

# 3. Evaluate a demand-forecast model against the moving-average baseline
python -m app.ml.train_reorder_forecast
```

This writes `models/training_risk_model.joblib` and two metrics JSON files.
Once `models/training_risk_model.joblib` exists and
`config.ENABLE_TRAINING_RISK_MODEL = True`, `POST /ai/training-risk` starts
returning extra `model_risk` / `model_probability` fields **alongside**
the rule output — the rule fields (`risk`, `score`, `reason`) are always
present and always the primary signal. Delete the `.joblib` file or flip
the config flag to go back to rule-only; nothing else changes.

Full dataset split / metric / limitations documentation: see
**`MODEL_CARD.md`** — this is what satisfies the brief's AI release gate
before demonstrating either feature.

`GET /ai/model-info` exposes the same information live, for the dashboard
or for a quick sanity check.

## Fixes from the latest review

Three issues were flagged and fixed:

1. **Inconsistent error handling.** The legacy endpoints (`/ai/reorder`,
   `/ai/training-risk`) used a decorator that, on a genuine crash, tried
   to return a shape that didn't match their declared response schema —
   this actually produced an ugly, unhandled 500 rather than a clean
   fallback. All four reorder/risk endpoints now use the identical
   pattern: compute the result in a try/except, raise a clean
   `HTTPException(500, "...")` on real failure. Locked in by
   `tests/test_error_handling_unified.py`.
2. **Hard-coded default token.** `INTERNAL_AI_TOKEN` is no longer baked
   into the code as a fallback that's easy to forget about. It's loaded
   from a `.env` file (see `.env.example`) or a real environment
   variable, and if `ENVIRONMENT` is set to anything other than
   `development` while the token is still the known placeholder, the
   service **refuses to start** rather than silently running with a
   guessable secret.
3. **Prediction log wiped on restart.** It was an in-memory Python list.
   It's now a local SQLite file (`storage/prediction_log.db`, stdlib
   `sqlite3`, zero new dependencies) that survives process restarts.
   `docker-compose.yml` mounts it as a named volume so it also survives
   container recreation — only `docker compose down -v` clears it. This
   is still explicitly a stand-in for a real `Prediction` table in the
   project's Postgres database, which is the Backend team's eventual job.

## Configuration

Copy `.env.example` to `.env` and adjust:

```bash
cp .env.example .env
```

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `development` | Set to anything else to require a real `INTERNAL_AI_TOKEN` |
| `INTERNAL_AI_TOKEN` | `dev-secret-change-me` | Shared secret with the Backend — generate a real one outside dev |
| `PREDICTION_LOG_DB_PATH` | `./storage/prediction_log.db` | Where the audit-trail SQLite file lives |

## ⚠️ Which endpoints can actually run on real, live data

| Endpoint | Live-viable? | Why |
|---|---|---|
| `/ai/predict-reorder`, `/ai/reorder` | ✅ Yes | Inputs (`on_hand`, `min_level`, etc.) match `parts`/`stock_balances` exactly |
| `/ai/vehicle-service-prediction` | ✅ Yes | Inputs (`mileage`, `make`, `year`) match `vehicles` table exactly |
| `/ai/training-risk`, `/ai/student-risk` (blueprint) | ✅ Yes | Inputs derivable from real `attendances`/`assessments`/`competencies` tables |
| `/ai/student-performance-risk` | ❌ **No** | Requires `Midterm_Score`, `Quizzes_Avg`, etc. — **these columns do not exist anywhere in the WST schema**. A real newly-registered student can never produce this input. Keep this endpoint as an ML-methodology demo only; do not wire it into production. |

## Real data received so far

`data/parts_data.csv` (100 real parts) has been processed through the live
reorder rule engine:

```bash
python -m data.process_real_parts_data
```

Output: `data/reorder_suggestions_output.csv` — full breakdown in
`MODEL_CARD.md`. Student training data hasn't arrived yet; the training-risk
model is still trained on synthetic data until it does.
