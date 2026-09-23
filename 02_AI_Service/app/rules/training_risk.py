"""
Training Risk Flag Engine — deterministic weighted-rule baseline (WST-FR-14).

Mirrors AI_Design_Document.docx section 3.2. Advisory only: never blocks or
alters an assessment sign-off, and never uses protected attributes.
"""
from dataclasses import dataclass, field

from app import config


@dataclass
class TrainingRiskInput:
    student_id: str
    attendance_rate: float            # percentage, 0-100
    unsigned_assessments: int
    missing_competencies: int
    actual_time_on_task: float        # minutes (or any consistent unit)
    expected_time_on_task: float      # minutes


@dataclass
class TrainingRiskResult:
    student_id: str
    risk: str
    score: int
    reason: str
    contributing_factors: list[str] = field(default_factory=list)
    baseline_version: str = config.BASELINE_VERSION


def evaluate_training_risk(data: TrainingRiskInput) -> TrainingRiskResult:
    score = 0
    factors: list[str] = []

    # Attendance
    if data.attendance_rate < config.ATTENDANCE_HIGH_THRESHOLD:
        score += config.WEIGHTS["attendance_high"]
        factors.append("low_attendance")
    elif data.attendance_rate < config.ATTENDANCE_MEDIUM_THRESHOLD:
        score += config.WEIGHTS["attendance_medium"]
        factors.append("moderate_attendance")

    # Unsigned assessments
    if data.unsigned_assessments >= config.UNSIGNED_ASSESSMENTS_HIGH:
        score += config.WEIGHTS["unsigned_high"]
        factors.append("many_unsigned_assessments")
    elif data.unsigned_assessments >= config.UNSIGNED_ASSESSMENTS_MEDIUM:
        score += config.WEIGHTS["unsigned_medium"]
        factors.append("pending_unsigned_assessments")

    # Missing competencies
    if data.missing_competencies >= config.MISSING_COMPETENCIES_HIGH:
        score += config.WEIGHTS["missing_competencies_high"]
        factors.append("missing_competencies")
    elif data.missing_competencies == config.MISSING_COMPETENCIES_MEDIUM:
        score += config.WEIGHTS["missing_competencies_medium"]
        factors.append("one_missing_competency")

    # Time on task
    if data.expected_time_on_task > 0:
        ratio = data.actual_time_on_task / data.expected_time_on_task
        if ratio < config.TIME_ON_TASK_RATIO_THRESHOLD:
            score += config.WEIGHTS["time_on_task"]
            factors.append("low_time_on_task")

    # Classification
    if score >= config.RISK_SCORE_HIGH:
        risk = "High"
    elif score >= config.RISK_SCORE_MEDIUM:
        risk = "Medium"
    else:
        risk = "Low"

    reason = _build_reason(factors, data)

    return TrainingRiskResult(
        student_id=data.student_id,
        risk=risk,
        score=score,
        reason=reason,
        contributing_factors=factors,
    )


def _build_reason(factors: list[str], data: TrainingRiskInput) -> str:
    if not factors:
        return "All tracked indicators are within normal range"

    readable = {
        "low_attendance": f"attendance below {config.ATTENDANCE_HIGH_THRESHOLD}%",
        "moderate_attendance": f"attendance below {config.ATTENDANCE_MEDIUM_THRESHOLD}%",
        "many_unsigned_assessments": f"{data.unsigned_assessments} unsigned assessments",
        "pending_unsigned_assessments": f"{data.unsigned_assessments} unsigned assessment(s) pending",
        "missing_competencies": f"{data.missing_competencies} competencies missing",
        "one_missing_competency": "1 competency missing",
        "low_time_on_task": "time-on-task below expected",
    }
    return "; ".join(readable[f] for f in factors)
