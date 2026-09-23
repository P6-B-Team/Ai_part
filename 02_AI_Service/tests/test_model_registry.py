from app.ml import model_registry
from app.ml.features import to_feature_vector


def test_model_registry_reports_availability_without_crashing():
    # Whether or not a model happens to be trained in this environment,
    # this call must never raise.
    available = model_registry.training_risk_model_available()
    assert isinstance(available, bool)


def test_feature_vector_shape():
    row = {
        "attendance_rate": 55,
        "unsigned_assessments": 1,
        "missing_competencies": 2,
        "actual_time_on_task": 40,
        "expected_time_on_task": 60,
    }
    vec = to_feature_vector(row)
    assert len(vec) == 4
    assert vec[0] == 55


def test_predict_if_model_available():
    if not model_registry.training_risk_model_available():
        return  # nothing to test in an environment with no trained model
    vec = to_feature_vector({
        "attendance_rate": 40,
        "unsigned_assessments": 3,
        "missing_competencies": 2,
        "actual_time_on_task": 20,
        "expected_time_on_task": 60,
    })
    label, proba = model_registry.predict_training_risk(vec)
    assert label in ("High", "Low")
    assert 0.0 <= proba <= 1.0
