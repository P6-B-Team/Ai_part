"""
Feature definitions for the training-risk model.

Per the brief: "A simple logistic model may be tested for training
completion risk using only learning activity data, never protected
attributes." This file is the single place that defines what goes into
the model, so that constraint is enforced in one spot, not scattered.
"""

# Exactly the fields the rule engine already uses — the model and the
# baseline must see the same inputs, or a metric comparison is meaningless.
LEARNING_ACTIVITY_FEATURES = [
    "attendance_rate",
    "unsigned_assessments",
    "missing_competencies",
    "actual_time_on_task",
    "expected_time_on_task",
]

# Explicitly documented as NEVER used, so a future contributor doesn't
# "helpfully" add them back in.
FORBIDDEN_PROTECTED_ATTRIBUTES = [
    "age", "gender", "nationality", "religion", "disability_status", "name",
]


def to_feature_vector(row: dict) -> list[float]:
    """row must contain LEARNING_ACTIVITY_FEATURES keys (e.g. a dict from
    TrainingRiskInput or a CSV row). Returns a fixed-order numeric vector,
    with actual_time_on_task expressed as a ratio of expected (matching
    the rule engine's own derived signal) rather than a raw duration,
    since raw duration alone isn't comparable across different task types.
    """
    expected = float(row["expected_time_on_task"]) or 1.0  # avoid div-by-zero
    time_ratio = float(row["actual_time_on_task"]) / expected
    return [
        float(row["attendance_rate"]),
        float(row["unsigned_assessments"]),
        float(row["missing_competencies"]),
        time_ratio,
    ]


FEATURE_NAMES = ["attendance_rate", "unsigned_assessments", "missing_competencies", "time_on_task_ratio"]
