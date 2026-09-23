"""
Vehicle Part Service Prediction — deterministic rule-based baseline.

Committed data foundation: `data/vehicle_maintenance.csv` (1,139 real
service records). Given a vehicle's mileage/brand/engine, predicts which
parts are likely due for service — a genuinely different capability from
the stock-level Reorder Suggestion engine (app/rules/reorder.py), which
stays as-is and answers a different question ("is this SKU low in the
store"). This one answers "does THIS vehicle likely need part X soon".

Baseline rule: for each part, use the 25th percentile of mileage among
service records where that part WAS serviced, as the "typical trigger
mileage" — grounded in the actual data rather than an arbitrary guess.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

PARTS = [
    "oil_filter", "engine_oil", "washer_plug_drain", "dust_and_pollen_filter",
    "whell_alignment_and_balancing", "air_clean_filter", "fuel_filter", "spark_plug",
    "brake_fluid", "brake_and_clutch_oil", "transmission_fluid", "brake_pads",
    "clutch", "coolant",
]

THRESHOLDS_PATH = Path(__file__).resolve().parents[2] / "models" / "vehicle_service_rule_thresholds.json"


@dataclass
class VehicleFeatures:
    """Field names match wst_schema.sql's `vehicles` table exactly:
    vehicles.mileage, vehicles.make, vehicles.year. `engine_type` was
    dropped — it does not exist as a column in the real schema, so a
    model trained on it could never receive real values in production."""
    vehicle_id: str
    mileage: float
    make: str | None = None
    year: int | None = None


@dataclass
class VehicleServiceResult:
    vehicle_id: str
    predicted_parts: list[str] = field(default_factory=list)
    part_scores: dict = field(default_factory=dict)  # part -> 0/1 rule flag
    explanation: str = ""


def _load_thresholds() -> dict:
    if THRESHOLDS_PATH.exists():
        return json.loads(THRESHOLDS_PATH.read_text())
    # Fallback defaults if thresholds haven't been computed yet (rare —
    # only before the first training run), rough industry norms in km.
    return {p: 40000 for p in PARTS}


def evaluate_vehicle_service(data: VehicleFeatures) -> VehicleServiceResult:
    thresholds = _load_thresholds()
    part_scores = {}
    predicted = []

    for part in PARTS:
        threshold = thresholds.get(part, 40000)
        flag = 1 if data.mileage >= threshold else 0
        part_scores[part] = flag
        if flag:
            predicted.append(part)

    explanation = (
        f"{len(predicted)} part(s) at or beyond their typical service mileage "
        f"at {data.mileage:g} km"
        if predicted else
        f"No parts yet at their typical service mileage ({data.mileage:g} km)"
    )

    return VehicleServiceResult(
        vehicle_id=data.vehicle_id, predicted_parts=predicted,
        part_scores=part_scores, explanation=explanation,
    )
