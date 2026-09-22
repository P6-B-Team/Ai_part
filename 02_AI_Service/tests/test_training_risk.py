from app.rules.training_risk import TrainingRiskInput, evaluate_training_risk


def test_high_risk_multiple_factors():
    data = TrainingRiskInput(
        student_id="S-1",
        attendance_rate=50,          # < 60 -> +40
        unsigned_assessments=3,      # >= 3 -> +25
        missing_competencies=2,      # >= 2 -> +25
        actual_time_on_task=40,
        expected_time_on_task=60,    # ratio 0.67 < 0.70 -> +10
    )
    result = evaluate_training_risk(data)
    assert result.score == 100
    assert result.risk == "High"
    assert "low_attendance" in result.contributing_factors


def test_low_risk_all_normal():
    data = TrainingRiskInput(
        student_id="S-2",
        attendance_rate=95,
        unsigned_assessments=0,
        missing_competencies=0,
        actual_time_on_task=60,
        expected_time_on_task=60,
    )
    result = evaluate_training_risk(data)
    assert result.score == 0
    assert result.risk == "Low"
    assert result.contributing_factors == []


def test_medium_risk_boundary():
    data = TrainingRiskInput(
        student_id="S-3",
        attendance_rate=70,          # < 85, >= 60 -> +25 (weight bumped for blueprint compliance)
        unsigned_assessments=1,      # >= 1, < 3 -> +10
        missing_competencies=0,
        actual_time_on_task=60,
        expected_time_on_task=60,
    )
    result = evaluate_training_risk(data)
    assert result.score == 35
    assert result.risk == "Medium"


def test_expected_time_zero_does_not_crash():
    data = TrainingRiskInput(
        student_id="S-4",
        attendance_rate=90,
        unsigned_assessments=0,
        missing_competencies=0,
        actual_time_on_task=0,
        expected_time_on_task=0,
    )
    result = evaluate_training_risk(data)
    assert result.risk == "Low"
