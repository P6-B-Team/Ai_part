"""
Prediction log — audit trail required by WST-FR-14's acceptance evidence:
"Suggestion records inputs, baseline/model version, explanation, user
decision, and evaluation outcome."

Persisted to a local SQLite file (stdlib `sqlite3`, no extra dependency)
so restarting the service doesn't wipe the audit trail — this was an
in-memory Python list originally, which is fine for a quick demo but
loses everything on every restart/redeploy, which defeats the point of an
audit trail. This is still explicitly a stand-in: the Backend team should
eventually write to a real `Prediction` table in the project's own
Postgres database (see the Data requirements table in the brief) so it
lives alongside JobCard/Student/etc. To make that migration easy, all
access goes through the four functions below — nothing else in the
codebase touches storage directly.

The SQLite file's location is configurable via PREDICTION_LOG_DB_PATH so
it can be pointed at a mounted Docker volume for real persistence across
container recreation (see docker-compose.yml).
"""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel

DB_PATH = Path(os.environ.get(
    "PREDICTION_LOG_DB_PATH",
    Path(__file__).resolve().parents[1] / "storage" / "prediction_log.db",
))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


class PredictionLogEntry(BaseModel):
    id: str
    feature: Literal["reorder", "training_risk"]
    inputs: dict[str, Any]
    baseline_version: str
    model_version: Optional[str] = None
    explanation: str
    generated_at: str
    user_decision: Optional[Literal["accepted", "overridden", "ignored"]] = None
    evaluation_outcome: Optional[str] = None


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id TEXT PRIMARY KEY,
            feature TEXT NOT NULL,
            inputs TEXT NOT NULL,
            baseline_version TEXT NOT NULL,
            model_version TEXT,
            explanation TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            user_decision TEXT,
            evaluation_outcome TEXT
        )
    """)
    return conn


def _row_to_entry(row: tuple) -> PredictionLogEntry:
    return PredictionLogEntry(
        id=row[0], feature=row[1], inputs=json.loads(row[2]),
        baseline_version=row[3], model_version=row[4], explanation=row[5],
        generated_at=row[6], user_decision=row[7], evaluation_outcome=row[8],
    )


def log_prediction(
    feature: str,
    inputs: dict[str, Any],
    baseline_version: str,
    explanation: str,
    model_version: str | None = None,
) -> PredictionLogEntry:
    entry = PredictionLogEntry(
        id=str(uuid4()),
        feature=feature,
        inputs=inputs,
        baseline_version=baseline_version,
        model_version=model_version,
        explanation=explanation,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO predictions "
            "(id, feature, inputs, baseline_version, model_version, explanation, "
            " generated_at, user_decision, evaluation_outcome) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.id, entry.feature, json.dumps(entry.inputs), entry.baseline_version,
                entry.model_version, entry.explanation, entry.generated_at,
                entry.user_decision, entry.evaluation_outcome,
            ),
        )
    return entry


def record_decision(entry_id: str, decision: str) -> Optional[PredictionLogEntry]:
    with _get_conn() as conn:
        conn.execute("UPDATE predictions SET user_decision = ? WHERE id = ?", (decision, entry_id))
        row = conn.execute("SELECT * FROM predictions WHERE id = ?", (entry_id,)).fetchone()
    return _row_to_entry(row) if row else None


def record_outcome(entry_id: str, outcome: str) -> Optional[PredictionLogEntry]:
    """
    Fills in evaluation_outcome — the one field of WST-FR-14's acceptance
    evidence ("inputs, baseline/model version, explanation, user decision,
    and evaluation outcome") that can only be known LATER, once the real
    result plays out (e.g. the part was actually reordered and consumption
    is now known, or the student actually completed/didn't complete).
    Backend calls this once that real outcome is available.
    """
    with _get_conn() as conn:
        conn.execute("UPDATE predictions SET evaluation_outcome = ? WHERE id = ?", (outcome, entry_id))
        row = conn.execute("SELECT * FROM predictions WHERE id = ?", (entry_id,)).fetchone()
    return _row_to_entry(row) if row else None


def all_entries() -> list[PredictionLogEntry]:
    with _get_conn() as conn:
        rows = conn.execute("SELECT * FROM predictions ORDER BY generated_at").fetchall()
    return [_row_to_entry(r) for r in rows]
