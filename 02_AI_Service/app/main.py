"""
AI Module service for Project 6 — Workshop Management & Student Practical
Training (WST-FR-14).

Two contracts are served side by side:

  Blueprint contract (AI_Service_Blueprint.pdf) — camelCase, minimal body,
  internal-auth-token protected, this is what the Backend should integrate
  against going forward:
    POST /ai/predict-reorder
    POST /ai/student-risk

  Original design-doc contract — snake_case, richer response, kept for
  backward compatibility with anything already built against it:
    POST /ai/reorder
    POST /ai/training-risk

  Shared, unauthenticated (read-only / monitoring):
    GET  /ai/reorder-alerts     -> current Medium/High alerts, for the dashboard
    GET  /ai/predictions        -> prediction log (audit trail)
    GET  /ai/model-info         -> release-gate metrics/versions
    POST /ai/predictions/{id}/decision -> record accept/override, for the metric
    GET  /health                -> liveness probe, used by Backend for fallback checks

Run locally:
    uvicorn app.main:app --reload --port 8001

Interactive docs (Swagger) then live at:
    http://localhost:8001/docs

Every POST /ai/* call must include header:
    X-Internal-Token: <value of INTERNAL_AI_TOKEN>
"""
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import config
from app.auth import verify_internal_token
from app.ml import model_registry
from app.ml.features import to_feature_vector
from app.prediction_log import log_prediction, record_decision, record_outcome, all_entries, PredictionLogEntry
from app.rules.reorder import ReorderInput, evaluate_reorder
from app.rules.training_risk import TrainingRiskInput, evaluate_training_risk
from app.rules.student_risk import StudentRiskFeatures, evaluate_student_risk
from app.rules.vehicle_service import VehicleFeatures, evaluate_vehicle_service, PARTS as VEHICLE_PARTS
from app.schemas import (
    ReorderRequest, ReorderResponse, ReorderAlert,
    TrainingRiskRequest, TrainingRiskResponse,
    PredictReorderRequest, PredictReorderResponse,
    StudentRiskRequest, StudentRiskResponse,
    StudentPerformanceRiskRequest, StudentPerformanceRiskResponse,
    VehicleServiceRequest, VehicleServiceResponse, PartPrediction,
)

app = FastAPI(
    title="Workshop AI Module (WST-FR-14)",
    description=(
        "Rule-based baseline for Reorder Suggestion and Training Risk Flag. "
        "See AI_Design_Document.docx and AI_Service_Blueprint.pdf for the full specification."
    ),
    version="1.1.0",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Blueprint section 8 distinguishes 400 (missing required field) from
    422 (field present but wrong type/shape) — FastAPI's default treats
    both as 422, so this splits them explicitly.
    """
    errors = exc.errors()
    missing = [e for e in errors if e["type"] == "missing"]
    if missing and len(missing) == len(errors):
        return JSONResponse(
            status_code=400,
            content={"detail": "Missing required field(s)", "errors": missing},
        )
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid request data", "errors": errors},
    )

# In-memory demo store, standing in for the real Part / Student tables.
# The Backend/Data team should replace these with real DB lookups —
# these endpoints intentionally take full input in the request body so
# they work standalone before that integration exists.
_reorder_alert_cache: list[ReorderAlert] = []


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok"}


@app.post("/ai/reorder", response_model=ReorderResponse, tags=["reorder"], dependencies=[Depends(verify_internal_token)])
async def reorder(req: ReorderRequest):
    try:
        result = evaluate_reorder(ReorderInput(**req.model_dump()))
    except Exception as exc:  # noqa: BLE001 - genuine engine crash, same contract as /ai/predict-reorder
        raise HTTPException(status_code=500, detail=f"Reorder prediction failed: {exc}")

    log_prediction(
        feature="reorder",
        inputs=req.model_dump(),
        baseline_version=result.baseline_version,
        explanation=result.reason,
    )

    # keep the alert cache warm for the dashboard endpoint
    if result.risk in ("High", "Medium"):
        _reorder_alert_cache[:] = [
            a for a in _reorder_alert_cache if a.part_id != result.part_id
        ] + [ReorderAlert(
            part_id=result.part_id,
            part_name=result.part_name,
            level=result.risk,
            suggested_quantity=result.suggested_quantity,
        )]

    return ReorderResponse(
        part_id=result.part_id,
        part_name=result.part_name,
        suggested_quantity=result.suggested_quantity,
        risk=result.risk,
        reason=result.reason,
        available_stock=result.available_stock,
        net_position=result.net_position,
        weeks_of_cover=result.weeks_of_cover,
        baseline_version=result.baseline_version,
    )


@app.get("/ai/reorder-alerts", response_model=list[ReorderAlert], tags=["reorder"])
async def reorder_alerts():
    """Dashboard-facing endpoint — no model internals, just what the UI needs."""
    return _reorder_alert_cache


@app.post("/ai/training-risk", response_model=TrainingRiskResponse, tags=["training-risk"], dependencies=[Depends(verify_internal_token)])
async def training_risk(req: TrainingRiskRequest):
    try:
        # Rule baseline — ALWAYS computed, ALWAYS the primary result.
        result = evaluate_training_risk(TrainingRiskInput(**req.model_dump()))
    except Exception as exc:  # noqa: BLE001 - genuine engine crash, same contract as /ai/student-risk
        raise HTTPException(status_code=500, detail=f"Training risk prediction failed: {exc}")

    model_version = None
    model_risk = None
    model_probability = None

    # Optional model — additive only, and safe if disabled or untrained.
    if config.ENABLE_TRAINING_RISK_MODEL and model_registry.training_risk_usable():
        try:
            features = to_feature_vector(req.model_dump())
            model_risk, model_probability = model_registry.predict_training_risk(features)
            metrics = model_registry.training_risk_metrics()
            model_version = metrics["model_version"] if metrics else "training-risk-model"
        except Exception:
            # Model failure must never break the rule-based response.
            model_risk = None
            model_probability = None

    log_prediction(
        feature="training_risk",
        inputs=req.model_dump(),
        baseline_version=result.baseline_version,
        explanation=result.reason,
        model_version=model_version,
    )

    return TrainingRiskResponse(
        student_id=result.student_id,
        risk=result.risk,
        score=result.score,
        reason=result.reason,
        contributing_factors=result.contributing_factors,
        baseline_version=result.baseline_version,
        model_version=model_version,
        model_risk=model_risk,
        model_probability=round(model_probability, 3) if model_probability is not None else None,
    )


def _bucket_probability(p: float) -> str:
    """Maps a 0-1 probability to the same Low/Medium/High scale the rule
    engine uses, so callers see one consistent vocabulary regardless of
    whether the rule or the model produced the result."""
    if p >= config.RISK_PROBABILITY_HIGH:
        return "High"
    if p >= config.RISK_PROBABILITY_MEDIUM:
        return "Medium"
    return "Low"


# ---------------------------------------------------------------------------
# Blueprint-contract endpoints (AI_Service_Blueprint.pdf)
# ---------------------------------------------------------------------------

@app.post(
    "/ai/predict-reorder",
    response_model=PredictReorderResponse,
    tags=["blueprint"],
    dependencies=[Depends(verify_internal_token)],
)
async def predict_reorder(req: PredictReorderRequest):
    try:
        result = evaluate_reorder(ReorderInput(
            part_id=req.partId,
            part_name=req.partId,  # blueprint's minimal body has no separate name
            current_stock=req.onHandQty,
            reserved_quantity=req.reservedQty,
            min_stock=req.minLevel,
            max_stock=req.maxLevel,
            open_po_quantity=req.openPoQty,
            avg_weekly_consumption=req.weeklyConsumption,
        ))
    except Exception as exc:  # noqa: BLE001 - top-level safety net per blueprint's 500 case
        raise HTTPException(status_code=500, detail=f"Reorder prediction failed: {exc}")

    # No live ML model is wired for reorder yet (see MODEL_CARD.md — the
    # forecast comparison is evaluation-only). The rule baseline is always
    # the one answering this endpoint today, so baselineUsed is always
    # True; fallbackActive flags specifically the "insufficient history"
    # case per blueprint section 5 step 3 / section 9.
    fallback_active = req.weeklyConsumption <= 0

    log_prediction(
        feature="reorder",
        inputs=req.model_dump(),
        baseline_version=result.baseline_version,
        explanation=result.reason,
    )

    if result.risk in ("High", "Medium"):
        _reorder_alert_cache[:] = [
            a for a in _reorder_alert_cache if a.part_id != result.part_id
        ] + [ReorderAlert(
            part_id=result.part_id,
            part_name=result.part_name,
            level=result.risk,
            suggested_quantity=result.suggested_quantity,
        )]

    return PredictReorderResponse(
        suggestedQty=result.suggested_quantity,
        baselineUsed=True,
        explanation=result.reason,
        partId=result.part_id,
        riskLevel=result.risk,
        fallbackActive=fallback_active,
    )


@app.post(
    "/ai/student-risk",
    response_model=StudentRiskResponse,
    tags=["blueprint"],
    dependencies=[Depends(verify_internal_token)],
)
async def student_risk(req: StudentRiskRequest):
    try:
        # Rule baseline — always computed first, per the blueprint's own
        # execution flow ("Check Baseline / Fallback Gate -> Execute ML
        # Model / Rule Baseline").
        rule_result = evaluate_training_risk(TrainingRiskInput(
            student_id=req.studentId,
            attendance_rate=req.attendanceRate,
            unsigned_assessments=req.missingAssessments,
            missing_competencies=req.unmetCompetencies,
            # The blueprint's minimal body has no time-on-task field;
            # passing equal values means that factor contributes zero,
            # which is the correct "no signal available" behavior rather
            # than guessing.
            actual_time_on_task=1.0,
            expected_time_on_task=1.0,
        ))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Student risk prediction failed: {exc}")

    baseline_used = True
    fallback_active = False
    risk_level = rule_result.risk
    completion_probability = round(rule_result.score / 100, 3)
    explanation = rule_result.reason
    model_version = None

    gate_open = config.ENABLE_TRAINING_RISK_MODEL and model_registry.training_risk_usable()
    if gate_open:
        try:
            features = to_feature_vector({
                "attendance_rate": req.attendanceRate,
                "unsigned_assessments": req.missingAssessments,
                "missing_competencies": req.unmetCompetencies,
                "actual_time_on_task": 1.0,
                "expected_time_on_task": 1.0,
            })
            _, probability = model_registry.predict_training_risk(features)
            risk_level = _bucket_probability(probability)
            completion_probability = round(probability, 3)
            metrics = model_registry.training_risk_metrics()
            model_version = metrics["model_version"] if metrics else "training-risk-model"
            explanation = (
                f"ML model ({model_version}) estimated completion risk from attendance, "
                f"missing assessments and unmet competencies"
            )
            baseline_used = False
        except Exception:
            # Model degraded -> fall back to the rule result already computed above.
            baseline_used = True
            fallback_active = True

    log_prediction(
        feature="training_risk",
        inputs=req.model_dump(),
        baseline_version=rule_result.baseline_version,
        explanation=explanation,
        model_version=model_version,
    )

    return StudentRiskResponse(
        riskLevel=risk_level,
        completionProbability=completion_probability,
        explanation=explanation,
        studentId=req.studentId,
        baselineUsed=baseline_used,
        fallbackActive=fallback_active,
    )


# ---------------------------------------------------------------------------
# Committed-data endpoints — students_performance.csv / vehicle_maintenance.csv
# ---------------------------------------------------------------------------

@app.post(
    "/ai/student-performance-risk",
    response_model=StudentPerformanceRiskResponse,
    tags=["committed-data"],
    dependencies=[Depends(verify_internal_token)],
)
async def student_performance_risk(req: StudentPerformanceRiskRequest):
    has_final_data = req.final_score is not None and req.projects_score is not None

    try:
        rule_result = evaluate_student_risk(StudentRiskFeatures(
            student_id=req.student_id,
            midterm_score=req.midterm_score, assignments_avg=req.assignments_avg,
            quizzes_avg=req.quizzes_avg, participation_score=req.participation_score,
            final_score=req.final_score, projects_score=req.projects_score,
        ))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Student performance risk prediction failed: {exc}")

    risk = rule_result.risk
    probability = round(rule_result.score / 100, 3)
    explanation = rule_result.reason
    model_version = None

    if config.ENABLE_TRAINING_RISK_MODEL and model_registry.student_risk_model_available():
        try:
            features = [
                req.midterm_score, req.assignments_avg, req.quizzes_avg, req.participation_score,
                req.study_hours_per_week, req.attendance_pct, req.stress_level, req.sleep_hours_per_night,
            ]
            if has_final_data:
                features += [req.final_score, req.projects_score]
            label, proba = model_registry.predict_student_risk(features)
            risk = label
            probability = round(proba, 3)
            explanation = f"Model-estimated at-risk probability from academic performance indicators"
            model_version = "student-risk-model"
        except Exception:
            pass  # fall back to the rule result already computed above

    log_prediction(
        feature="training_risk", inputs=req.model_dump(),
        baseline_version="rule-v1.0-student-risk", explanation=explanation, model_version=model_version,
    )

    return StudentPerformanceRiskResponse(
        student_id=req.student_id, risk=risk, at_risk_probability=probability,
        explanation=explanation, variant=rule_result.variant,
        baseline_version="rule-v1.0-student-risk", model_version=model_version,
    )


@app.post(
    "/ai/vehicle-service-prediction",
    response_model=VehicleServiceResponse,
    tags=["committed-data"],
    dependencies=[Depends(verify_internal_token)],
)
async def vehicle_service_prediction(req: VehicleServiceRequest):
    try:
        rule_result = evaluate_vehicle_service(VehicleFeatures(
            vehicle_id=req.vehicle_id, mileage=req.mileage,
            make=req.make, year=req.year,
        ))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Vehicle service prediction failed: {exc}")

    parts_out = []
    predicted_parts = []
    model_used = False

    for part in VEHICLE_PARTS:
        ml_result = None
        if config.ENABLE_TRAINING_RISK_MODEL and model_registry.vehicle_service_models_available():
            try:
                ml_result = model_registry.predict_vehicle_part(
                    part, req.mileage, req.year, req.make
                )
            except Exception:
                ml_result = None

        if ml_result is not None:
            proba, threshold = ml_result
            likely = proba >= threshold
            parts_out.append(PartPrediction(part=part, likely_due=likely, probability=round(proba, 3)))
            model_used = True
        else:
            likely = bool(rule_result.part_scores.get(part, 0))
            parts_out.append(PartPrediction(part=part, likely_due=likely, probability=None))

        if likely:
            predicted_parts.append(part)

    log_prediction(
        feature="reorder", inputs=req.model_dump(),
        baseline_version="rule-v1.0-vehicle-service",
        explanation=f"{len(predicted_parts)} part(s) predicted due",
        model_version="vehicle-service-model" if model_used else None,
    )

    return VehicleServiceResponse(
        vehicle_id=req.vehicle_id, predicted_parts=predicted_parts, parts=parts_out,
        baseline_version="rule-v1.0-vehicle-service",
        model_version="vehicle-service-model" if model_used else None,
    )


@app.get("/ai/model-info", tags=["audit"])
async def model_info():
    """
    AI release-gate transparency endpoint: dataset split, baseline
    comparison, metric, known limitations, model/version log — everything
    the brief requires before an AI feature may be demonstrated.
    """
    return {
        "training_risk": {
            "enabled": config.ENABLE_TRAINING_RISK_MODEL,
            "model_available": model_registry.training_risk_model_available(),
            "release_gate_passed": model_registry.training_risk_release_gate_passed(),
            "usable_live": model_registry.training_risk_usable(),
            "metrics": model_registry.training_risk_metrics(),
        },
        "reorder_forecast": {
            "note": "Evaluation only — not wired into the live /ai/predict-reorder endpoint yet.",
            "metrics": model_registry.reorder_forecast_metrics(),
        },
    }


@app.get("/ai/predictions", response_model=list[PredictionLogEntry], tags=["audit"])
async def predictions():
    """Full audit trail — inputs, version, explanation, decision, outcome."""
    return all_entries()


@app.post("/ai/predictions/{entry_id}/decision", response_model=PredictionLogEntry, tags=["audit"])
async def set_decision(entry_id: str, decision: str):
    if decision not in ("accepted", "overridden", "ignored"):
        raise HTTPException(400, "decision must be accepted, overridden, or ignored")
    entry = record_decision(entry_id, decision)
    if entry is None:
        raise HTTPException(404, "prediction not found")
    return entry


@app.post("/ai/predictions/{entry_id}/outcome", response_model=PredictionLogEntry, tags=["audit"])
async def set_outcome(entry_id: str, outcome: str):
    """
    Closes the loop on WST-FR-14's required audit trail. Call this once
    the real-world result is known — e.g. after the reordered part's next
    consumption cycle, or once a student's course actually completes or
    doesn't. This is what makes the accuracy metrics in MODEL_CARD.md
    computable from real operation later, not just from a synthetic
    held-out set.
    """
    entry = record_outcome(entry_id, outcome)
    if entry is None:
        raise HTTPException(404, "prediction not found")
    return entry
