# WST — AI Module Handoff Guide
### Reorder Suggestion & Training Risk Flag (WST-FR-14)
**Prepared by: AI Engineer, Squad 6 — v2, aligned to AI_Service_Blueprint.pdf**

This is the entry point. Read this first.

---

## 1. Three issues fixed in this review pass

A teammate flagged three real issues. All three are fixed and tested:

1. **Error handling was inconsistent between old/new endpoints** — worse
   than inconsistent, actually: the old endpoints had a decorator bug that
   caused an ugly unhandled 500 instead of the clean fallback it was meant
   to produce. Fixed: all four endpoints now use one identical pattern
   (try/except → clean `HTTPException(500, ...)` on real failure). See
   `tests/test_error_handling_unified.py`.
2. **Default token hard-coded in the code** — fixed: the token now loads
   from `.env` (`.env.example` included) or a real environment variable,
   and **the service refuses to start** if deployed with
   `ENVIRONMENT != development` and no real token set.
3. **Prediction log wiped on restart** — fixed: switched from an
   in-memory list to a local SQLite file
   (`02_AI_Service/storage/prediction_log.db`, zero new dependencies),
   mounted as a Docker volume so it survives container recreation too.

Full technical detail in `02_AI_Service/README.md` under "Fixes from the
latest review".

## 2. What's new in this version

The team sent two things: **`parts_data.csv`** (100 real parts) and
**`AI_Service_Blueprint.pdf`** (a more specific API contract than the
original design doc). Both are now fully incorporated:

- New endpoints matching the blueprint exactly: `POST /ai/predict-reorder`,
  `POST /ai/student-risk` (camelCase, minimal body). The original
  endpoints (`/ai/reorder`, `/ai/training-risk`) still work, for backward
  compatibility.
- **Internal auth token** required on every `/ai/*` POST call
  (`X-Internal-Token` header) — per blueprint section 4.
- **Status codes** now distinguish 400 (missing field) / 401 (bad auth) /
  422 (wrong type) — per blueprint section 8.
- **Real data processed**: `parts_data.csv` run through the live rule
  engine → 15 High risk, 14 Medium, 31 parts needing reorder. Found and
  fixed a real edge case (7 parts with `reserved_quantity > stock`).
- **Model retrained on the blueprint's exact 80/20 split.** Honest result:
  the model does **not** clear the blueprint's 80%-precision release gate
  (currently 56%). The live service correctly detects this and always
  falls back to the rule baseline for risk predictions until a future
  retrain clears the gate — this is by design, not a bug. Full details in
  `03_Team_Docs/MODEL_CARD.md`.
- **22/22 tests passing**, including a new suite
  (`tests/test_blueprint_api.py`) built directly from the blueprint's own
  "Verification & Test Suite" section (reorder test, high-risk test,
  fallback-crash test, plus every status code).

---

## 2. What's in this folder

```
WST-AI-Module/
├── 00_START_HERE.md
├── 01_Design_Document/
│   ├── AI_Design_Document.docx / .pdf     <- original spec
│   └── Project_6__AI_Service_Blueprint.pdf <- the team's API contract (now implemented)
├── 02_AI_Service/
│   ├── app/                       <- FastAPI service, rule engines, models, auth
│   ├── tests/                     <- 22 automated tests, including blueprint compliance
│   ├── data/
│   │   ├── parts_data.csv                  <- REAL data received
│   │   ├── reorder_suggestions_output.csv  <- REAL results
│   │   ├── process_real_parts_data.py
│   │   └── synthetic_*.csv + generator      <- still synthetic (student data not received yet)
│   ├── models/                    <- trained model + evaluation metrics (honest, incl. gate=false)
│   ├── Dockerfile, docker-compose.yml
│   └── README.md
└── 03_Team_Docs/
    ├── BACKEND_INTEGRATION.md     <- updated: auth header, new endpoints, status codes
    └── MODEL_CARD.md              <- updated: real data results, honest release-gate finding
```

---

## 3. How to run it

```bash
cd WST-AI-Module/02_AI_Service
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

Swagger: **http://localhost:8001/docs** — remember every `/ai/*` POST
needs header `X-Internal-Token: dev-secret-change-me` (dev default; change
for staging/prod).

```bash
pytest -v          # should show 22 passed
python -m data.process_real_parts_data   # re-run the real-data report
```

---

## 4. Still waiting on

**Student training data**, shaped like
`data/synthetic_students_training_history.csv`:
`student_id, attendance_rate, unsigned_assessments, missing_competencies,
actual_time_on_task, expected_time_on_task` (+ a ground-truth
`actually_incomplete` column if available, needed only to retrain and
re-check the release gate — not needed for live rule-based predictions,
which already work today).

---

## 5. Exactly what to hand each teammate

### → Backend
- **Send:** `02_AI_Service/` + `03_Team_Docs/BACKEND_INTEGRATION.md`
- **Tell them:** *"Use the blueprint endpoints (`/ai/predict-reorder`,
  `/ai/student-risk`) going forward — matches AI_Service_Blueprint.pdf
  exactly, camelCase body, needs the X-Internal-Token header (see the
  guide for the exact value and where to set it). Legacy endpoints still
  work if anything's already wired to them."*

### → Frontend
- **Send:** nothing code-wise — point them at `/docs`, or the
  `PredictReorderResponse` / `StudentRiskResponse` examples.
- **Tell them:** *"You never call the AI service directly. No auth token
  needed on your side."*

### → Data/BI teammate
- **Send:** `02_AI_Service/data/` (including the real `parts_data.csv`
  results), `02_AI_Service/app/ml/`, and `MODEL_CARD.md`
- **Tell them:** *"Real reorder data is processed and validated. Still
  need student training data — same CSV shape as the synthetic file — to
  retrain and try to clear the 80% precision release gate."*

### → Tech Lead / Doctor
- **Send:** `01_Design_Document/` (all three files) + `03_Team_Docs/MODEL_CARD.md`
- **Tell them:** *"Rule engine live and tested against real parts data
  (100 real parts processed, real edge case found and fixed). Blueprint's
  exact API contract, auth, and status codes implemented and tested
  (22/22 passing). Model trained and evaluated on the blueprint's 80/20
  split — honestly does not yet clear the 80% precision gate on synthetic
  data, and the service correctly avoids serving it live until it does.
  Waiting on real student data to retrain."*

---

## 6. One-line status

> "AI Module for WST-FR-14 now matches AI_Service_Blueprint.pdf exactly —
> auth, status codes, endpoint contract. Reorder engine validated against
> 100 real parts (31 need reordering). Training-risk model is trained and
> honestly does not clear the blueprint's 80% precision gate yet, so the
> service correctly serves the rule baseline live — that's the fallback
> design working as intended, not a bug. 22/22 tests passing."
