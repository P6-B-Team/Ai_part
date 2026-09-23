"""
Synthetic data generator — REQUIRED by the project's shipping rule #3:
"No real student, customer, employee or applicant record enters your
repository, your laptop or your notebook. Every project ships a seed
generator."

Everything here is fabricated with numpy's RNG. No real names, no real
institution data. Run this before training any model.

Usage:
    python -m data.generate_synthetic_data
"""
import csv
import random
from pathlib import Path

import numpy as np

OUT_DIR = Path(__file__).parent
SEED = 42

random.seed(SEED)
np.random.seed(SEED)

FAKE_FIRST = ["Omar", "Sara", "Youssef", "Nour", "Ahmed", "Mona", "Karim", "Laila",
              "Hassan", "Dina", "Khaled", "Yara", "Tarek", "Salma", "Amr", "Heba"]


def generate_students(n=400):
    """
    Synthetic student training-activity records. Only learning-activity
    fields are generated — no protected attributes (age, gender, name is
    a fake placeholder only, never used as a model feature) per the
    brief's explicit rule for the training-risk model.
    """
    rows = []
    for i in range(n):
        attendance_rate = np.clip(np.random.normal(78, 20), 0, 100)
        unsigned_assessments = np.random.poisson(1.2)
        missing_competencies = np.random.poisson(0.8)
        expected_time = np.random.uniform(30, 90)
        # students who attend less also tend to under-invest time on task
        time_ratio_center = 0.5 + 0.5 * (attendance_rate / 100)
        actual_time = expected_time * np.clip(np.random.normal(time_ratio_center, 0.2), 0.1, 1.4)

        # Ground-truth outcome: did the student actually fail to complete
        # the course? Simulated with noise so it's learnable but not
        # perfectly deterministic from the rule alone (that's the point
        # of comparing a model against the rule baseline).
        risk_signal = (
            (100 - attendance_rate) * 0.5
            + unsigned_assessments * 8
            + missing_competencies * 10
            + max(0, expected_time - actual_time) * 0.3
        )
        prob_incomplete = 1 / (1 + np.exp(-(risk_signal - 45) / 12))
        incomplete = np.random.rand() < prob_incomplete

        rows.append({
            "student_id": f"S-{1000+i}",
            "attendance_rate": round(attendance_rate, 1),
            "unsigned_assessments": int(unsigned_assessments),
            "missing_competencies": int(missing_competencies),
            "actual_time_on_task": round(actual_time, 1),
            "expected_time_on_task": round(expected_time, 1),
            "actually_incomplete": int(incomplete),  # ground truth label
        })
    return rows


def generate_parts_consumption(n_parts=60, n_weeks=26):
    """
    Synthetic weekly consumption history per part, for the demand-forecast
    evaluation (moving average baseline vs a simple model).
    """
    rows = []
    for p in range(n_parts):
        part_id = f"P-{2000+p}"
        base_demand = np.random.uniform(2, 25)
        trend = np.random.uniform(-0.05, 0.08)
        seasonality_amp = np.random.uniform(0, 3)
        for w in range(n_weeks):
            seasonal = seasonality_amp * np.sin(2 * np.pi * w / 12)
            noise = np.random.normal(0, base_demand * 0.15)
            demand = max(0, base_demand + trend * w + seasonal + noise)
            rows.append({
                "part_id": part_id,
                "week": w,
                "weekly_consumption": round(demand, 1),
            })
    return rows


def write_csv(rows, filename):
    path = OUT_DIR / filename
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows -> {path}")


if __name__ == "__main__":
    write_csv(generate_students(400), "synthetic_students_training_history.csv")
    write_csv(generate_parts_consumption(60, 26), "synthetic_parts_consumption_history.csv")
