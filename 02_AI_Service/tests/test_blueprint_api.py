"""
API-level tests matching AI_Service_Blueprint.pdf section 10 ("Verification
& Test Suite") item by item:
  - Reorder Test: low-inventory part triggers a reorder suggestion
  - Student High-Risk Test: attendance < 85% triggers a risk flag
  - Fallback Override Test: simulate an internal crash, verify the caller
    still gets a usable (non-500) response where possible

Plus the status-code contract from section 8 (400/401/422) since those are
part of the same acceptance surface.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import config

client = TestClient(app)
HEADERS = {"X-Internal-Token": config.INTERNAL_AI_TOKEN}


# ---------------------------------------------------------------------------
# Blueprint section 10, item 1 — Reorder Test
# ---------------------------------------------------------------------------

def test_reorder_test_low_inventory_triggers_suggestion():
    resp = client.post("/ai/predict-reorder", headers=HEADERS, json={
        "partId": "PART_016",
        "onHandQty": 0,      # matches the real dataset's PART_016 (0 in stock)
        "minLevel": 12,
        "maxLevel": 116,
        "weeklyConsumption": 9,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["suggestedQty"] > 0
    assert body["riskLevel"] == "High"
    assert body["baselineUsed"] is True
    assert "explanation" in body and len(body["explanation"]) > 0


# ---------------------------------------------------------------------------
# Blueprint section 10, item 2 — Student High-Risk Test (attendance < 85%)
# ---------------------------------------------------------------------------

def test_student_high_risk_test_attendance_below_85():
    resp = client.post("/ai/student-risk", headers=HEADERS, json={
        "studentId": "S-TEST-1",
        "attendanceRate": 80,   # < 85, per the blueprint's exact test spec
        "missingAssessments": 0,
        "unmetCompetencies": 0,
    })
    assert resp.status_code == 200
    body = resp.json()
    # attendance alone at 80% should be enough to move risk off "Low"
    assert body["riskLevel"] in ("Medium", "High")
    assert 0.0 <= body["completionProbability"] <= 1.0


def test_student_low_risk_when_attendance_above_85():
    resp = client.post("/ai/student-risk", headers=HEADERS, json={
        "studentId": "S-TEST-2",
        "attendanceRate": 95,
        "missingAssessments": 0,
        "unmetCompetencies": 0,
    })
    assert resp.status_code == 200
    assert resp.json()["riskLevel"] == "Low"


# ---------------------------------------------------------------------------
# Blueprint section 10, item 3 — Fallback Override Test
# ---------------------------------------------------------------------------

def test_fallback_override_when_model_raises():
    """
    Simulates the ML model crashing mid-prediction. The endpoint must not
    surface that as a broken response to the caller — it must fall back
    to the rule baseline and say so via fallbackActive.
    """
    with patch("app.main.config.ENABLE_TRAINING_RISK_MODEL", True), \
         patch("app.main.model_registry.training_risk_usable", return_value=True), \
         patch("app.main.model_registry.predict_training_risk", side_effect=RuntimeError("simulated crash")):
        resp = client.post("/ai/student-risk", headers=HEADERS, json={
            "studentId": "S-TEST-3",
            "attendanceRate": 50,
            "missingAssessments": 2,
            "unmetCompetencies": 1,
        })
    assert resp.status_code == 200  # zero downtime — never a 500 for a model-only failure
    body = resp.json()
    assert body["baselineUsed"] is True
    assert body["fallbackActive"] is True
    assert body["riskLevel"] in ("Low", "Medium", "High")


# ---------------------------------------------------------------------------
# Blueprint section 8 — status codes
# ---------------------------------------------------------------------------

def test_401_when_token_missing():
    resp = client.post("/ai/predict-reorder", json={
        "partId": "P-1", "onHandQty": 1, "minLevel": 1, "maxLevel": 10, "weeklyConsumption": 1,
    })
    assert resp.status_code == 401


def test_401_when_token_wrong():
    resp = client.post(
        "/ai/predict-reorder",
        headers={"X-Internal-Token": "wrong-token"},
        json={"partId": "P-1", "onHandQty": 1, "minLevel": 1, "maxLevel": 10, "weeklyConsumption": 1},
    )
    assert resp.status_code == 401


def test_400_when_required_field_missing():
    resp = client.post("/ai/predict-reorder", headers=HEADERS, json={
        "partId": "P-1", "minLevel": 1, "maxLevel": 10,
        # onHandQty intentionally omitted
    })
    assert resp.status_code == 400


def test_422_when_field_wrong_type():
    resp = client.post("/ai/predict-reorder", headers=HEADERS, json={
        "partId": "P-1", "onHandQty": "not-a-number", "minLevel": 1, "maxLevel": 10, "weeklyConsumption": 1,
    })
    assert resp.status_code == 422


def test_health_and_alerts_do_not_require_auth():
    assert client.get("/health").status_code == 200
    assert client.get("/ai/reorder-alerts").status_code == 200
