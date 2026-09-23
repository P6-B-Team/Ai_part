# Backend Integration Guide — Workshop AI Module (WST-FR-14)

This is what the Backend team needs to wire the AI service into the main
Node.js API. The AI service is a **separate process** (own Docker
container) — Backend calls it over HTTP, it never touches Postgres
directly.

**Two contracts are served.** Use the blueprint contract for new work —
it's what `AI_Service_Blueprint.pdf` specifies and what any Backend code
written from now on should target. The legacy contract (`/ai/reorder`,
`/ai/training-risk`) still works, unchanged, for anything already built
against the earlier design doc.

| | Blueprint contract (recommended) | Legacy contract |
|---|---|---|
| Reorder | `POST /ai/predict-reorder` | `POST /ai/reorder` |
| Risk | `POST /ai/student-risk` | `POST /ai/training-risk` |
| Field casing | camelCase | snake_case |
| Auth required | Yes | Yes |

## 1. Where it lives

- Local dev: `http://localhost:8001`
- In the project's `docker-compose.yml`, add this service block (copy the
  `ai-service` block from `ai_service/docker-compose.yml`) alongside the
  existing `backend`, `frontend`, `db` services so they share a network —
  then Backend reaches it at `http://ai-service:8001` instead of
  `localhost`.
- Set the URL via an environment variable on the Backend side, e.g.
  `AI_SERVICE_URL=http://ai-service:8001` — never hard-code it.

## 2. Auth — required on every /ai/* call

Every `/ai/*` POST endpoint (both contracts) requires this header:

```
X-Internal-Token: <value of INTERNAL_AI_TOKEN>
```

Default dev value is `dev-secret-change-me` (set via the `INTERNAL_AI_TOKEN`
env var on the AI service container). **The AI service will refuse to
start on staging/production** if `ENVIRONMENT` isn't `development` and a
real token hasn't been set — this is intentional, so a missing secret is
caught at deploy time, not discovered later as a silent security gap. Set
both:
```
ENVIRONMENT=production
INTERNAL_AI_TOKEN=<a real generated secret>
```
and give Backend the same token value via its own env var, e.g.
`AI_SERVICE_TOKEN`. Missing or wrong token on a request → `401 Unauthorized`.

`GET /health`, `GET /ai/reorder-alerts`, `GET /ai/predictions`, and
`GET /ai/model-info` are read-only and do **not** require the token.

## 3. Calling it from Node.js (Express/NestJS)

```js
// services/aiClient.js
const AI_SERVICE_URL = process.env.AI_SERVICE_URL || "http://localhost:8001";
const AI_SERVICE_TOKEN = process.env.AI_SERVICE_TOKEN || "dev-secret-change-me";
const TIMEOUT_MS = 2000; // fail fast — see fallback rule below

async function predictReorder(part) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const res = await fetch(`${AI_SERVICE_URL}/ai/predict-reorder`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Token": AI_SERVICE_TOKEN,
      },
      body: JSON.stringify({
        partId: part.id,
        onHandQty: part.stockQuantity,
        minLevel: part.minStockLevel,
        maxLevel: part.maxStockLevel,
        weeklyConsumption: part.monthlyUsage / 4.345, // see note below
        reservedQty: part.reservedQuantity,           // optional, improves accuracy
        openPoQty: part.openPoQuantity,                // optional, improves accuracy
      }),
      signal: controller.signal,
    });

    if (res.status === 401) throw new Error("AI service auth failed — check AI_SERVICE_TOKEN");
    if (res.status === 400) throw new Error("AI service rejected request — missing field");
    if (res.status === 422) throw new Error("AI service rejected request — invalid field type");
    if (!res.ok) throw new Error(`AI service returned ${res.status}`);
    return await res.json(); // { suggestedQty, baselineUsed, explanation, partId, riskLevel, fallbackActive }
  } catch (err) {
    // Rule: workshop operations must never block on the AI service.
    // Log and fall back — do not throw up to the request handler.
    console.warn("AI reorder suggestion unavailable:", err.message);
    return { available: false, reason: err.message, fallback: true };
  } finally {
    clearTimeout(timeout);
  }
}

module.exports = { predictReorder };
```

Use the same pattern for `POST /ai/student-risk`
(`{ studentId, attendanceRate, missingAssessments, unmetCompetencies }` →
`{ riskLevel, completionProbability, explanation, studentId, baselineUsed,
fallbackActive }`).

**Note on `weeklyConsumption`:** if the Backend's stock data is monthly
(as in the `parts_data.csv` sample the AI Engineer received), convert by
dividing by 4.345 (average weeks/month) — see
`data/process_real_parts_data.py` for the reference implementation.

## 4. The fallback contract (read this before wiring anything else)

The brief's rule 5 is non-negotiable: *"Every AI feature needs a
deterministic baseline and a fallback."* The blueprint's own response
shape gives you two fields to read for this:

- **`baselineUsed`** (bool) — `true` means the deterministic rule engine
  answered this request (always the case for reorder today; for risk,
  whenever the ML model hasn't cleared its release gate — see
  `MODEL_CARD.md`). `false` means the ML model's prediction is what you're
  looking at.
- **`fallbackActive`** (bool) — `true` means something degraded (sparse
  history, a model error) and the system fell back to the rule engine
  specifically *because of that*, as opposed to the rule engine being the
  normal, by-design answer.

Concretely:

- **Always set a request timeout** (2 seconds is plenty — this is rule
  evaluation, not a heavy model). Never let a slow/down AI service hold up
  a job-card save or a stock update.
- **Treat any non-200 response, timeout, or network error the same way**:
  log it, show the UI "prediction unavailable" state, and let the
  underlying workflow continue normally. A missing reorder suggestion must
  never block issuing a part; a missing risk flag must never block
  recording attendance.
- **Never surface a 500 to the end user** because the AI service hiccuped
  — that's a Backend bug, not an AI service bug, if it happens. (The AI
  service itself only returns 500 for a genuine internal crash in the rule
  engine, which should never happen in normal operation — a model-only
  failure is caught internally and answered via the rule baseline instead,
  still with a 200.)

## 5. Which endpoint to call when

| Backend event | Call | Notes |
|---|---|---|
| Stock falls below reorder point (nightly job or on stock movement) | `POST /ai/predict-reorder` | Store the result against the Part; surface via `GET /ai/reorder-alerts` for the dashboard, or cache Backend-side if you prefer Postgres as the source of truth |
| Nightly analytics refresh (per brief's workflow step 7) | `POST /ai/student-risk` per active student | Batch it — the endpoint is single-student per call by design, so loop or parallelize with a concurrency cap |
| Dashboard load | `GET /ai/reorder-alerts` | Read-only, no side effects, safe to call often, no auth needed |
| Storekeeper accepts/overrides a suggestion | `POST /ai/predictions/{id}/decision` | This is what feeds the "acceptance/override rate" metric the brief requires |

## 6. What Backend owns vs. what AI Module owns

- **AI Module owns:** the rule logic, the risk/quantity calculation, the
  explanation text, the prediction log entries it creates.
- **Backend owns:** looking up the actual Part/Student records from
  Postgres, deciding *when* to call the AI service, eventually migrating
  `Prediction` into the project's own Postgres database long-term (the AI
  service currently persists it to a local SQLite file — durable across
  restarts, but not queryable alongside JobCard/Student the way a real
  Postgres table would be — see `app/prediction_log.py`), and enforcing
  that a suggestion never becomes an automatic purchase order or an
  automatic grade (per the brief's explicit out-of-scope items).

## 7. Swagger reference

Full request/response schemas, with live "Try it out": `/docs` on the AI
service (e.g. `http://localhost:8001/docs`). That's the authoritative
contract — this guide is a summary of how to consume it correctly.
Remember to add the `X-Internal-Token` header when trying it from Swagger
too (the "Authorize" lock icon, or manually per-request).
