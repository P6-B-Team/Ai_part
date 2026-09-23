"""
Central place for every tunable number in the rule engines.
Storekeepers / training supervisors should be able to change these
without anyone touching rules.py — this is exactly what the design
document calls out as "configuration, not hard-coded".
"""

# ---- Reorder engine -------------------------------------------------------

REORDER_WEEKS_OF_COVER_HIGH = 1     # < 1 week of cover  -> High
REORDER_WEEKS_OF_COVER_MEDIUM = 3   # < 3 weeks of cover -> Medium, else Low

# ---- Training risk engine --------------------------------------------------

import os
import sys

from dotenv import load_dotenv

load_dotenv()  # reads a local .env file if present; real env vars always win

ATTENDANCE_HIGH_THRESHOLD = 60      # % below this -> +40
# Bumped from 80 to 85 per AI_Service_Blueprint.pdf section 10:
# "Student High-Risk Test: Confirm risk flag triggers for attendance < 85%."
ATTENDANCE_MEDIUM_THRESHOLD = 85    # % below this (and >= HIGH) -> +20

UNSIGNED_ASSESSMENTS_HIGH = 3       # >= this -> +25
UNSIGNED_ASSESSMENTS_MEDIUM = 1     # >= this (and < HIGH) -> +10

MISSING_COMPETENCIES_HIGH = 2       # >= this -> +25
MISSING_COMPETENCIES_MEDIUM = 1     # == this -> +10

TIME_ON_TASK_RATIO_THRESHOLD = 0.70  # actual/expected below this -> +10

RISK_SCORE_HIGH = 50                # score >= this -> High
RISK_SCORE_MEDIUM = 25              # score >= this (and < HIGH) -> Medium

WEIGHTS = {
    "attendance_high": 40,
    "attendance_medium": 25,  # was 20 — bumped so attendance alone crossing
                              # the 85% threshold reaches RISK_SCORE_MEDIUM (25)
                              # on its own, matching the blueprint's explicit
                              # "attendance < 85% triggers risk flag" test.
    "unsigned_high": 25,
    "unsigned_medium": 10,
    "missing_competencies_high": 25,
    "missing_competencies_medium": 10,
    "time_on_task": 10,
}

BASELINE_VERSION = "rule-v1.0"

# ---- Release gate (AI_Service_Blueprint.pdf section 7) --------------------
# "Risk Precision / Recall >= 80% Precision on 80/20 train/test holdout split"
RISK_PRECISION_TARGET = 0.80
TRAIN_TEST_SPLIT = 0.20  # blueprint specifies 80/20, not the earlier 70/15/15

# Precision alone can be gamed by a model/threshold that flags almost
# nobody (e.g. 100% precision, 5% recall is technically "passing" but
# operationally useless — it would miss most at-risk students). This
# minimum recall is an engineering safeguard, not in the blueprint text,
# added so the release gate can't be cleared by a model that isn't
# actually useful. See MODEL_CARD.md for the specific case this caught.
RISK_MIN_RECALL_FOR_GATE = 0.40

# ---- Internal service auth (blueprint section 4: "Internal Auth Token") ---
# The Node.js Backend must send this as the X-Internal-Token header on
# every /ai/* call.
#
# The token itself is NEVER hard-coded here. It comes from the
# INTERNAL_AI_TOKEN environment variable — set it in a local .env file for
# development (see .env.example), and as a real secret (Docker secret,
# CI/CD secret store, etc.) in staging/production. ENVIRONMENT defaults to
# "development" so local runs work out of the box with a placeholder
# value; outside development, forgetting to set a real token is a
# deployment mistake, not something the code should paper over — so it
# fails at startup instead of silently serving a known, guessable secret.
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
_DEV_PLACEHOLDER_TOKEN = "dev-secret-change-me"
INTERNAL_AI_TOKEN = os.environ.get("INTERNAL_AI_TOKEN", _DEV_PLACEHOLDER_TOKEN)

if ENVIRONMENT != "development" and INTERNAL_AI_TOKEN == _DEV_PLACEHOLDER_TOKEN:
    sys.exit(
        "FATAL: ENVIRONMENT is '%s' but INTERNAL_AI_TOKEN was not set — "
        "refusing to start with the known development placeholder token "
        "outside development. Set a real INTERNAL_AI_TOKEN (env var or "
        "secret store)." % ENVIRONMENT
    )

# Risk-level bucketing for the model's raw probability output, so both the
# rule baseline and the ML model report on the same Low/Medium/High scale
# (the blueprint's binary High/Low is bucketed into three for consistency
# with the rule engine's granularity).
RISK_PROBABILITY_HIGH = 0.66
RISK_PROBABILITY_MEDIUM = 0.33

# ---- Optional Week-4 model -------------------------------------------------
# Per the brief: "Rule-Based Baseline first... optional models only after
# sufficient history." The rule baseline is ALWAYS computed and ALWAYS
# shown, even when this is True — the model result is additive, never a
# replacement, and the code must work fine with this False (or with no
# trained model file present at all).
ENABLE_TRAINING_RISK_MODEL = True
