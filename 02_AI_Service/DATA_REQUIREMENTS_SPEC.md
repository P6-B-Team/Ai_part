# Data Requirements Specification — WST-FR-14

> **Update — real schema confirmed (`wst_schema.sql` received).** Every
> column below has a real, confirmed source in the actual WST database.
> This is no longer a hypothetical spec — it's a direct export
> instruction. See the mapping table at the end of each section.


This is the exact spec for the two datasets the AI Module needs. Send
this to whoever is exporting data (Backend/Data-BI teammate). Every
condition here exists because we already hit it as a real problem in an
earlier attempt — the "why" for each rule is the actual failure it fixes.

---

# Dataset 1 — Training Risk (for the student completion-risk model)

## Required columns (exact names, exact types)

| Column | Type | Range/Format | What it means |
|---|---|---|---|
| `student_id` | string | unique per row | Just an identifier, never used as a feature |
| `attendance_rate` | float | 0–100 | % of scheduled sessions attended, **as of the snapshot date** (see "Timing" below) |
| `unsigned_assessments` | int | ≥ 0 | Count of that student's Assessment records still `status='pending sign-off'` as of the snapshot date |
| `missing_competencies` | int | ≥ 0 | Count of required competencies not yet marked `met` as of the snapshot date |
| `actual_time_on_task` | float (minutes) | ≥ 0 | Sum/average of logged time on practical tasks up to the snapshot date |
| `expected_time_on_task` | float (minutes) | ≥ 0 | Expected/allocated time for those same tasks |
| `actually_incomplete` | int | 0 or 1 | **Ground truth**, recorded AFTER the course/term ended: did the student fail to complete/certify? |

## The one rule that matters most: timing

Every feature column (`attendance_rate` through `expected_time_on_task`)
must be a **snapshot taken partway through the term** — e.g. at the
midpoint, or at a fixed "checkpoint" date. `actually_incomplete` is the
only column allowed to be known only at the very end.

**Why this is non-negotiable:** a column computed *after* the outcome is
already known will accidentally encode the outcome itself. This is
exactly what happened with the last dataset — `unmetCompetencies` turned
out to correlate suspiciously cleanly with the final `Grade`, which is a
sign it was derived from the outcome rather than measured independently
beforehand. A model trained on that kind of column looks great in testing
and is useless in production, because at prediction time (mid-course,
when the flag is actually needed) that information doesn't exist yet.

## Minimum data quality bar (checked automatically — see script below)

- **No constant columns.** Every feature column must have real variation
  across students. (`missingAssessments` in the last file was `0` for
  all 5,000 rows — mathematically that column carries zero information,
  no matter how strong the model is.)
- **No duplicate/derived columns.** Every column must be an independent
  measurement. (`attendanceRate` in the last file was an exact copy of
  an existing column — same numbers, different name.)
- **Minimum size: 2,000 rows.** Our first synthetic attempt (400 rows)
  was too small — the test set ended up with only 80 rows, which made
  every precision/recall estimate noisy and unstable.
- **Minimum positive class size: at least 300 students with
  `actually_incomplete = 1`.** If completion failure is rare (under
  ~15% of students), pull data from multiple terms/cohorts to get enough
  positive examples — a model can't learn a pattern it barely sees.
- **No personally identifying information beyond `student_id`.** Strip
  names, emails, etc. The AI service never needs them and the brief
  requires minimizing PII exposure.

## Confirmed mapping to the real WST database (`wst_schema.sql`)

| Column we need | Real table(s)/column(s) it comes from |
|---|---|
| `student_id` | `students.id` |
| `attendance_rate` | `COUNT(attendances WHERE status='PRESENT') / COUNT(attendances)` per student, up to the snapshot date |
| `unsigned_assessments` | `COUNT(assessments WHERE status='PENDING_SIGNATURE')` per student (no matching row in `assessment_signoffs`) |
| `missing_competencies` | `COUNT(DISTINCT competencies.id)` reachable via `task_competencies` from `practical_tasks WHERE required=true`, that don't yet have a passed + signed assessment |
| `actual_time_on_task` | `assessments.time_on_task` — already a direct column, just aggregate (sum/avg) per student |
| `expected_time_on_task` | **⚠️ No direct column exists yet.** Two options to raise with the team: (1) add an `expected_minutes` column to `practical_tasks`, or (2) approximate via `courses.duration_hours` ÷ number of required tasks in that course |
| `actually_incomplete` | Derived at term-end from certificate issuance logic (`certificates` table + `org_settings.certificate_min_pass_ratio`/`certificate_min_attendance_ratio`) — did the student fail to meet those thresholds? |

## What "high accuracy" actually depends on

Meeting every rule above gives the model a real chance — it does **not**
guarantee 80%+ precision, because that also depends on how strong the
real-world relationship between these features and completion actually
is (something no amount of data cleaning can manufacture if it isn't
there). What we can promise: if these rules aren't met, the model
mathematically *cannot* do well, regardless of which algorithm is used —
we've now proven that twice with real tests. If they *are* met, we're
giving the model a fair shot, and can report the honest result either
way.

---

# Dataset 2 — Parts Demand (for the reorder forecast model)

## Required columns

| Column | Type | Range/Format | What it means |
|---|---|---|---|
| `part_id` | string | unique per part | SKU identifier |
| `week` | int or date | sequential, no gaps | Week number or week-start date |
| `weekly_consumption` | float | ≥ 0 | Units actually consumed/issued that week |
| `category` | string | optional | Part category, useful for grouping in dashboards |

## The one rule that matters most: this must be a time series, not a snapshot

`parts_data.csv` (the file already received) is one row per part — a
single point-in-time snapshot. That's exactly right for the **reorder
rule engine** (it only needs current stock levels), but it is **not**
usable for a forecasting model, which needs to see how each part's
consumption changes *across many weeks* to learn a trend.

## Confirmed mapping to the real WST database (`wst_schema.sql`)

| Column we need | Real table(s)/column(s) it comes from |
|---|---|
| `part_id` | `parts.id` (or `parts.sku`) |
| `week` / `weekly_consumption` | Aggregated from `stock_movements WHERE type='ISSUE'`, grouped by `part_id` and week from `created_at` |
| — | The **reorder rule engine's other inputs are already confirmed real and need no changes**: `current_stock` = `stock_balances.on_hand`, `reserved_quantity` = `stock_balances.reserved`, `min_stock`/`max_stock` = `parts.min_level`/`max_level`, `open_po_quantity` = `SUM(purchase_order_lines.ordered_qty - received_qty)` for that part's open POs |

## Minimum data quality bar

- **At least 52 weeks (1 full year) per part**, so the model can see a
  complete seasonal cycle. 26 weeks is the absolute minimum, and only
  acceptable as a stopgap.
- **At least 30–50 distinct parts** with full history — a model trained
  on 3–4 parts can't generalize to the other 96.
- **No silently back-filled or estimated weeks.** If a week's real
  number is unknown, leave it blank/flagged rather than guessing a
  value — a guessed value that gets treated as real teaches the model a
  pattern that never actually happened.

---

# Self-check script

Before sending any CSV, run it through `data/validate_dataset.py` (in
this same folder). It automatically checks for every issue listed above
— constant columns, duplicate columns, sample size, class balance — and
tells you exactly what's wrong before it reaches me. See that file's own
instructions for how to run it.
