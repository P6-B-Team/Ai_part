"""
Student Risk Engine — OFFICIAL, active implementation.

Committed data foundation: `data/students_performance.csv`. Per an
explicit team decision, this dataset (and `data/vehicle_maintenance.csv`
for the parts-service model) is now the permanent basis for these AI
features — not a placeholder awaiting a different export. Column names
differ from the original WST-FR-14 design-doc field names
(attendance_rate/unsigned_assessments/missing_competencies), because
they're driven by this committed dataset's real columns
(Midterm_Score/Assignments_Avg/Quizzes_Avg/Participation_Score/etc.)
instead. The older `app/rules/training_risk.py` module — built against
the WST database schema's own tables — is kept in the codebase, unused
by the live API for now, in case the team later also wants that data
source; it is not deleted and needs no changes if that day comes.

Deterministic rule-based baseline (project rule 5: "Every AI feature
needs a deterministic baseline and a fallback").

Two variants exist, matching the two ML model variants in
app/ml/train_student_risk_model.py — see MODEL_CARD.md for why both
exist and when each is appropriate:

- "early": only columns known partway through the term (Midterm,
  Assignments, Quizzes, Participation, plus behavioral columns).
  A genuine early-warning signal.
- "final": adds Final_Score and Projects_Score, columns only known near
  the end of the term. Much stronger signal, but NOT an early-warning
  tool — by the time these are known, the term is nearly over.
"""
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class StudentRiskFeatures:
    student_id: str
    midterm_score: float
    assignments_avg: float
    quizzes_avg: float
    participation_score: float
    final_score: float | None = None      # only used by the "final" variant
    projects_score: float | None = None   # only used by the "final" variant


@dataclass
class StudentRiskResult:
    student_id: str
    risk: str
    score: int
    reason: str
    variant: Literal["early", "final"]
    contributing_factors: list[str] = field(default_factory=list)


# Thresholds are round numbers on a 0-100 scale, chosen from the
# dataset's own quartiles (25th percentile is roughly 55-62 across these
# columns) rather than an arbitrary guess.
LOW_THRESHOLD = 50
MID_THRESHOLD = 65


def _score_band(value: float, weight_low: int, weight_mid: int) -> tuple[int, str | None]:
    if value < LOW_THRESHOLD:
        return weight_low, "low"
    if value < MID_THRESHOLD:
        return weight_mid, "borderline"
    return 0, None


def evaluate_student_risk(data: StudentRiskFeatures) -> StudentRiskResult:
    score = 0
    factors = []

    for label, value, w_low, w_mid in [
        ("midterm", data.midterm_score, 30, 15),
        ("assignments", data.assignments_avg, 20, 10),
        ("quizzes", data.quizzes_avg, 20, 10),
        ("participation", data.participation_score, 15, 8),
    ]:
        points, band = _score_band(value, w_low, w_mid)
        score += points
        if band:
            factors.append(f"{label}_{band}")

    variant = "early"
    if data.final_score is not None and data.projects_score is not None:
        variant = "final"
        for label, value, w_low, w_mid in [
            ("final_exam", data.final_score, 25, 12),
            ("projects", data.projects_score, 15, 8),
        ]:
            points, band = _score_band(value, w_low, w_mid)
            score += points
            if band:
                factors.append(f"{label}_{band}")

    if score >= 50:
        risk = "High"
    elif score >= 25:
        risk = "Medium"
    else:
        risk = "Low"

    reason = (
        f"{len(factors)} indicator(s) below expected range: {', '.join(factors)}"
        if factors else "All tracked academic indicators are within normal range"
    )

    return StudentRiskResult(
        student_id=data.student_id, risk=risk, score=score,
        reason=reason, variant=variant, contributing_factors=factors,
    )
