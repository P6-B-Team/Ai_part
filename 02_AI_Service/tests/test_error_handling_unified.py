"""
Regression test for a real bug found during review: the legacy endpoints
(/ai/reorder, /ai/training-risk) used a decorator that, on a genuine engine
crash, tried to return a FallbackResponse object while the endpoint's
declared response_model was ReorderResponse/TrainingRiskResponse. FastAPI's
own response validation then raised ResponseValidationError — an unhandled
500 with a confusing traceback, not the clean fallback it was meant to be.

Fix: both endpoint generations now use the identical pattern — compute the
rule engine result inside try/except, raise HTTPException(500) with a
clear message on genuine failure. This test locks that in on all four
reorder/risk endpoints so no unimplemented status code sneaks back into
either engine's error handling.
"""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app import config

client = TestClient(app)
HEADERS = {"X-Internal-Token": config.INTERNAL_AI_TOKEN}

VALID_REORDER_LEGACY = {
    "part_id": "P-1", "part_name": "Test Part", "current_stock": 5,
    "reserved_quantity": 0, "min_stock": 10, "max_stock": 40,
    "open_po_quantity": 0, "avg_weekly_consumption": 7,
}
VALID_REORDER_BLUEPRINT = {
    "partId": "P-1", "onHandQty": 5, "minLevel": 10, "maxLevel": 40, "weeklyConsumption": 7,
}
VALID_RISK_LEGACY = {
    "student_id": "S-1", "attendance_rate": 90, "unsigned_assessments": 0,
    "missing_competencies": 0, "actual_time_on_task": 60, "expected_time_on_task": 60,
}
VALID_RISK_BLUEPRINT = {
    "studentId": "S-1", "attendanceRate": 90, "missingAssessments": 0, "unmetCompetencies": 0,
}


def test_legacy_reorder_returns_clean_500_on_engine_crash():
    with patch("app.main.evaluate_reorder", side_effect=RuntimeError("boom")):
        resp = client.post("/ai/reorder", headers=HEADERS, json=VALID_REORDER_LEGACY)
    assert resp.status_code == 500
    assert "Reorder prediction failed" in resp.json()["detail"]


def test_blueprint_reorder_returns_clean_500_on_engine_crash():
    with patch("app.main.evaluate_reorder", side_effect=RuntimeError("boom")):
        resp = client.post("/ai/predict-reorder", headers=HEADERS, json=VALID_REORDER_BLUEPRINT)
    assert resp.status_code == 500
    assert "Reorder prediction failed" in resp.json()["detail"]


def test_legacy_training_risk_returns_clean_500_on_engine_crash():
    with patch("app.main.evaluate_training_risk", side_effect=RuntimeError("boom")):
        resp = client.post("/ai/training-risk", headers=HEADERS, json=VALID_RISK_LEGACY)
    assert resp.status_code == 500
    assert "Training risk prediction failed" in resp.json()["detail"]


def test_blueprint_student_risk_returns_clean_500_on_engine_crash():
    with patch("app.main.evaluate_training_risk", side_effect=RuntimeError("boom")):
        resp = client.post("/ai/student-risk", headers=HEADERS, json=VALID_RISK_BLUEPRINT)
    assert resp.status_code == 500
    assert "Student risk prediction failed" in resp.json()["detail"]


def test_all_four_endpoints_succeed_normally_with_valid_input():
    """Sanity check: the try/except refactor didn't break the happy path."""
    assert client.post("/ai/reorder", headers=HEADERS, json=VALID_REORDER_LEGACY).status_code == 200
    assert client.post("/ai/predict-reorder", headers=HEADERS, json=VALID_REORDER_BLUEPRINT).status_code == 200
    assert client.post("/ai/training-risk", headers=HEADERS, json=VALID_RISK_LEGACY).status_code == 200
    assert client.post("/ai/student-risk", headers=HEADERS, json=VALID_RISK_BLUEPRINT).status_code == 200
