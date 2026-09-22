"""
Validates a candidate CSV against DATA_REQUIREMENTS_SPEC.md before anyone
wastes a training run on it. Catches exactly the problems found in real
review: constant columns, duplicate columns, too few rows, too few
positive examples.

Usage:
    python -m data.validate_dataset path/to/file.csv --kind training_risk
    python -m data.validate_dataset path/to/file.csv --kind parts_demand

Exits with a non-zero status if any check fails, so it can be used in a
script/CI step, not just read by eye.
"""
import argparse
import sys

import pandas as pd

TRAINING_RISK_COLUMNS = {
    "student_id": "string identifier",
    "attendance_rate": "float 0-100",
    "unsigned_assessments": "int >= 0",
    "missing_competencies": "int >= 0",
    "actual_time_on_task": "float minutes >= 0",
    "expected_time_on_task": "float minutes >= 0",
    "actually_incomplete": "int 0 or 1 (ground truth)",
}
TRAINING_RISK_FEATURE_COLUMNS = [c for c in TRAINING_RISK_COLUMNS if c != "student_id"]
TRAINING_RISK_MIN_ROWS = 2000
TRAINING_RISK_MIN_POSITIVES = 300

PARTS_DEMAND_COLUMNS = {
    "part_id": "string identifier",
    "week": "int or date, sequential",
    "weekly_consumption": "float >= 0",
}
PARTS_DEMAND_MIN_WEEKS_PER_PART = 26
PARTS_DEMAND_MIN_PARTS = 30


def _fail(msg):
    print(f"  \u2717 FAIL: {msg}")
    return False


def _ok(msg):
    print(f"  \u2713 OK: {msg}")
    return True


def validate_training_risk(df: pd.DataFrame) -> bool:
    print(f"Checking training-risk dataset ({len(df)} rows)...\n")
    passed = True

    missing_cols = [c for c in TRAINING_RISK_COLUMNS if c not in df.columns]
    if missing_cols:
        passed &= _fail(f"missing required column(s): {missing_cols}")
        return passed  # can't check further without the columns
    else:
        passed &= _ok("all required columns present")

    if len(df) < TRAINING_RISK_MIN_ROWS:
        passed &= _fail(f"only {len(df)} rows, need at least {TRAINING_RISK_MIN_ROWS}")
    else:
        passed &= _ok(f"row count ({len(df)}) meets the {TRAINING_RISK_MIN_ROWS} minimum")

    # Constant columns — zero variance, mathematically useless
    for col in TRAINING_RISK_FEATURE_COLUMNS:
        n_unique = df[col].nunique(dropna=True)
        if n_unique <= 1:
            passed &= _fail(f"'{col}' is constant (only {n_unique} unique value) — carries zero information")
        else:
            passed &= _ok(f"'{col}' has {n_unique} unique values")

    # Duplicate columns — exact or near-exact copies of each other.
    # Skip constant columns here (already flagged above); correlation
    # against a constant is undefined (0/0), not a duplicate finding.
    numeric_cols = [
        c for c in TRAINING_RISK_FEATURE_COLUMNS
        if pd.api.types.is_numeric_dtype(df[c]) and df[c].nunique(dropna=True) > 1
    ]
    for i, col_a in enumerate(numeric_cols):
        for col_b in numeric_cols[i + 1:]:
            corr = df[col_a].corr(df[col_b])
            if pd.notna(corr) and abs(corr) > 0.98:
                passed &= _fail(f"'{col_a}' and '{col_b}' are near-duplicates (correlation={corr:.3f})")

    # Class balance for the ground-truth label
    if "actually_incomplete" in df.columns:
        n_positive = int(df["actually_incomplete"].sum())
        if n_positive < TRAINING_RISK_MIN_POSITIVES:
            passed &= _fail(
                f"only {n_positive} rows with actually_incomplete=1, "
                f"need at least {TRAINING_RISK_MIN_POSITIVES}"
            )
        else:
            passed &= _ok(f"{n_positive} positive examples (>= {TRAINING_RISK_MIN_POSITIVES} minimum)")

    return passed


def validate_parts_demand(df: pd.DataFrame) -> bool:
    print(f"Checking parts-demand dataset ({len(df)} rows)...\n")
    passed = True

    missing_cols = [c for c in PARTS_DEMAND_COLUMNS if c not in df.columns]
    if missing_cols:
        passed &= _fail(f"missing required column(s): {missing_cols}")
        return passed
    else:
        passed &= _ok("all required columns present")

    n_parts = df["part_id"].nunique()
    if n_parts < PARTS_DEMAND_MIN_PARTS:
        passed &= _fail(f"only {n_parts} distinct parts, need at least {PARTS_DEMAND_MIN_PARTS}")
    else:
        passed &= _ok(f"{n_parts} distinct parts (>= {PARTS_DEMAND_MIN_PARTS} minimum)")

    weeks_per_part = df.groupby("part_id")["week"].nunique()
    too_short = weeks_per_part[weeks_per_part < PARTS_DEMAND_MIN_WEEKS_PER_PART]
    if len(too_short) > 0:
        passed &= _fail(
            f"{len(too_short)} part(s) have fewer than {PARTS_DEMAND_MIN_WEEKS_PER_PART} weeks of history "
            f"(e.g. {list(too_short.index[:5])})"
        )
    else:
        passed &= _ok(f"every part has >= {PARTS_DEMAND_MIN_WEEKS_PER_PART} weeks of history")

    return passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path")
    parser.add_argument("--kind", choices=["training_risk", "parts_demand"], required=True)
    args = parser.parse_args()

    df = pd.read_csv(args.csv_path)

    if args.kind == "training_risk":
        passed = validate_training_risk(df)
    else:
        passed = validate_parts_demand(df)

    print()
    if passed:
        print("ALL CHECKS PASSED — this dataset is ready to use for training.")
        sys.exit(0)
    else:
        print("ONE OR MORE CHECKS FAILED — see above. Fix these before training on this file.")
        sys.exit(1)


if __name__ == "__main__":
    main()
