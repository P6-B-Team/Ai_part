from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Reorder
# ---------------------------------------------------------------------------

class ReorderRequest(BaseModel):
    part_id: str
    part_name: str
    current_stock: float = Field(ge=0)
    reserved_quantity: float = Field(ge=0)
    min_stock: float = Field(ge=0)
    max_stock: float = Field(ge=0)
    open_po_quantity: float = Field(ge=0, default=0)
    avg_weekly_consumption: float = Field(ge=0, default=0)

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "part_id": "P-0042",
                "part_name": "Brake Pad",
                "current_stock": 5,
                "reserved_quantity": 0,
                "min_stock": 10,
                "max_stock": 40,
                "open_po_quantity": 0,
                "avg_weekly_consumption": 7,
            }
        })


class ReorderResponse(BaseModel):
    part_id: str
    part_name: str
    suggested_quantity: float
    risk: str
    reason: str
    available_stock: float
    net_position: float
    weeks_of_cover: Optional[float]
    baseline_version: str
    model_version: Optional[str] = None


class ReorderAlert(BaseModel):
    part_id: str
    part_name: str
    level: str
    suggested_quantity: float


# ---------------------------------------------------------------------------
# Training risk
# ---------------------------------------------------------------------------

class TrainingRiskRequest(BaseModel):
    student_id: str
    attendance_rate: float = Field(ge=0, le=100)
    unsigned_assessments: int = Field(ge=0)
    missing_competencies: int = Field(ge=0)
    actual_time_on_task: float = Field(ge=0)
    expected_time_on_task: float = Field(ge=0)

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "student_id": "S-0123",
                "attendance_rate": 55,
                "unsigned_assessments": 1,
                "missing_competencies": 2,
                "actual_time_on_task": 40,
                "expected_time_on_task": 60,
            }
        })


class TrainingRiskResponse(BaseModel):
    student_id: str
    risk: str
    score: int
    reason: str
    contributing_factors: list[str]
    baseline_version: str
    model_version: Optional[str] = None
    # Present only when ENABLE_TRAINING_RISK_MODEL is on and a trained
    # model artifact exists. The rule fields above are ALWAYS the primary
    # decision — this is an additional, clearly-labeled signal.
    model_risk: Optional[str] = None
    model_probability: Optional[float] = None


# ---------------------------------------------------------------------------
# Blueprint-aligned schemas (AI_Service_Blueprint.pdf) — camelCase, minimal
# body, used by POST /ai/predict-reorder and POST /ai/student-risk.
# The richer snake_case schemas above remain available on the original
# /ai/reorder and /ai/training-risk routes for backward compatibility.
# ---------------------------------------------------------------------------

class PredictReorderRequest(BaseModel):
    partId: str
    onHandQty: float = Field(ge=0)
    minLevel: float = Field(ge=0)
    maxLevel: float = Field(ge=0)
    weeklyConsumption: float = Field(ge=0, default=0)
    # Not in the blueprint's minimal body, but accepted if the Backend has
    # them available — they materially improve accuracy (see design doc
    # section 2.2) and default to 0 if omitted, so the blueprint's exact
    # minimal payload still works unchanged.
    reservedQty: float = Field(ge=0, default=0)
    openPoQty: float = Field(ge=0, default=0)

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "partId": "PART_016",
                "onHandQty": 0,
                "minLevel": 12,
                "maxLevel": 116,
                "weeklyConsumption": 9,
            }
        })


class PredictReorderResponse(BaseModel):
    # Exactly the three fields the blueprint specifies:
    suggestedQty: float
    baselineUsed: bool
    explanation: str
    # Additive extras — safe to ignore for a consumer that only reads the
    # three fields above, useful for the dashboard/debugging.
    partId: str
    riskLevel: str
    fallbackActive: bool


class StudentRiskRequest(BaseModel):
    studentId: str
    attendanceRate: float = Field(ge=0, le=100)
    missingAssessments: int = Field(ge=0)
    unmetCompetencies: int = Field(ge=0)

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "studentId": "S-0123",
                "attendanceRate": 55,
                "missingAssessments": 1,
                "unmetCompetencies": 2,
            }
        })


class StudentRiskResponse(BaseModel):
    riskLevel: str
    completionProbability: float
    explanation: str
    studentId: str
    baselineUsed: bool
    fallbackActive: bool


# ---------------------------------------------------------------------------
# Student Performance Risk — committed data foundation (students_performance.csv)
# ---------------------------------------------------------------------------

class StudentPerformanceRiskRequest(BaseModel):
    student_id: str
    midterm_score: float = Field(ge=0, le=100)
    assignments_avg: float = Field(ge=0, le=100)
    quizzes_avg: float = Field(ge=0, le=100)
    participation_score: float = Field(ge=0, le=100)
    study_hours_per_week: float = Field(ge=0, default=0)
    attendance_pct: float = Field(ge=0, le=100, default=0)
    stress_level: float = Field(ge=0, le=10, default=5)
    sleep_hours_per_night: float = Field(ge=0, default=7)
    # Optional — only known near end of term; supplying them switches to
    # the "final" model variant, which is far more accurate but is NOT an
    # early-warning signal (see MODEL_CARD.md).
    final_score: Optional[float] = Field(default=None, ge=0, le=100)
    projects_score: Optional[float] = Field(default=None, ge=0, le=100)


class StudentPerformanceRiskResponse(BaseModel):
    student_id: str
    risk: str
    at_risk_probability: float
    explanation: str
    variant: str  # "early" or "final"
    baseline_version: str
    model_version: Optional[str] = None


# ---------------------------------------------------------------------------
# Vehicle Service Prediction — committed data foundation (vehicle_maintenance.csv)
# ---------------------------------------------------------------------------

class VehicleServiceRequest(BaseModel):
    """Field names match wst_schema.sql's `vehicles` table exactly
    (vehicles.mileage, vehicles.make, vehicles.year) — no engine_type,
    since that column doesn't exist in the real schema."""
    vehicle_id: str
    mileage: float = Field(ge=0)
    make: Optional[str] = None
    year: Optional[int] = None


class PartPrediction(BaseModel):
    part: str
    likely_due: bool
    probability: Optional[float] = None  # only present when the ML model answered this part


class VehicleServiceResponse(BaseModel):
    vehicle_id: str
    predicted_parts: list[str]
    parts: list[PartPrediction]
    baseline_version: str
    model_version: Optional[str] = None


