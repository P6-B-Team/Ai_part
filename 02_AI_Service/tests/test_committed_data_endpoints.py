"""
Tests for the endpoints backed by the committed data foundation:
data/students_performance.csv and data/vehicle_maintenance.csv.
"""
from fastapi.testclient import TestClient

from app.main import app
from app import config

client = TestClient(app)
HEADERS = {"X-Internal-Token": config.INTERNAL_AI_TOKEN}


def test_student_performance_risk_early_variant():
    resp = client.post("/ai/student-performance-risk", headers=HEADERS, json={
        "student_id": "S-TEST-1", "midterm_score": 45, "assignments_avg": 50,
        "quizzes_avg": 48, "participation_score": 40,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["variant"] == "early"
    assert body["risk"] in ("Low", "Medium", "High")
    assert 0.0 <= body["at_risk_probability"] <= 1.0


def test_student_performance_risk_final_variant_uses_model():
    resp = client.post("/ai/student-performance-risk", headers=HEADERS, json={
        "student_id": "S-TEST-2", "midterm_score": 45, "assignments_avg": 50,
        "quizzes_avg": 48, "participation_score": 40, "final_score": 40, "projects_score": 45,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["variant"] == "final"


def test_student_performance_risk_healthy_student_is_low_risk():
    resp = client.post("/ai/student-performance-risk", headers=HEADERS, json={
        "student_id": "S-TEST-3", "midterm_score": 90, "assignments_avg": 92,
        "quizzes_avg": 88, "participation_score": 85,
    })
    assert resp.status_code == 200
    assert resp.json()["risk"] == "Low"


def test_vehicle_service_prediction_high_mileage():
    resp = client.post("/ai/vehicle-service-prediction", headers=HEADERS, json={
        "vehicle_id": "V-TEST-1", "mileage": 90000, "make": "toyota", "year": 2016,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["parts"]) == 14
    # very high mileage should flag at least the near-universal maintenance items
    assert "oil_filter" in body["predicted_parts"]


def test_vehicle_service_prediction_low_mileage_flags_fewer_parts():
    resp_low = client.post("/ai/vehicle-service-prediction", headers=HEADERS, json={
        "vehicle_id": "V-TEST-2", "mileage": 2000, "make": "honda", "year": 2018,
    })
    resp_high = client.post("/ai/vehicle-service-prediction", headers=HEADERS, json={
        "vehicle_id": "V-TEST-3", "mileage": 95000, "make": "honda", "year": 2016,
    })
    assert resp_low.status_code == 200 and resp_high.status_code == 200
    assert len(resp_low.json()["predicted_parts"]) <= len(resp_high.json()["predicted_parts"])


def test_committed_data_endpoints_require_auth():
    resp = client.post("/ai/student-performance-risk", json={
        "student_id": "S-X", "midterm_score": 50, "assignments_avg": 50, "quizzes_avg": 50, "participation_score": 50,
    })
    assert resp.status_code == 401

    resp2 = client.post("/ai/vehicle-service-prediction", json={"vehicle_id": "V-X", "mileage": 1000})
    assert resp2.status_code == 401
