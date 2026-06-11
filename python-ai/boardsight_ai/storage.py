from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from boardsight_ai.models import PipelineResult


def init_storage(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                run_name TEXT,
                input_video TEXT NOT NULL,
                output_dir TEXT,
                result_file TEXT,
                transcript_text TEXT,
                speaker_count INTEGER DEFAULT 0,
                decision_count INTEGER DEFAULT 0,
                visual_artifact_count INTEGER DEFAULT 0,
                top_decision_id TEXT,
                overall_attention REAL DEFAULT 0,
                overall_sentiment TEXT,
                impact_score REAL DEFAULT 0,
                productivity_score REAL DEFAULT 0,
                execution_readiness REAL DEFAULT 0,
                dominance_ratio REAL DEFAULT 0,
                analysis_profile TEXT,
                source_mode TEXT,
                run_status TEXT DEFAULT 'completed',
                execution_task_count INTEGER DEFAULT 0,
                risk_signal_count INTEGER DEFAULT 0,
                contract_version TEXT,
                result_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        existing_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(meetings)").fetchall()
        }
        required_columns: dict[str, str] = {
            "user_id": "INTEGER",
            "username": "TEXT",
            "run_name": "TEXT",
            "output_dir": "TEXT",
            "result_file": "TEXT",
            "transcript_text": "TEXT",
            "speaker_count": "INTEGER DEFAULT 0",
            "decision_count": "INTEGER DEFAULT 0",
            "visual_artifact_count": "INTEGER DEFAULT 0",
            "top_decision_id": "TEXT",
            "overall_attention": "REAL DEFAULT 0",
            "overall_sentiment": "TEXT",
            "impact_score": "REAL DEFAULT 0",
            "productivity_score": "REAL DEFAULT 0",
            "execution_readiness": "REAL DEFAULT 0",
            "dominance_ratio": "REAL DEFAULT 0",
            "analysis_profile": "TEXT",
            "source_mode": "TEXT",
            "run_status": "TEXT DEFAULT 'completed'",
            "execution_task_count": "INTEGER DEFAULT 0",
            "risk_signal_count": "INTEGER DEFAULT 0",
            "contract_version": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(f"ALTER TABLE meetings ADD COLUMN {column_name} {column_type}")

        connection.commit()


def save_meeting_result(
    database_path: Path,
    result: PipelineResult,
    output_dir: Path | None = None,
    result_file: Path | None = None,
    user_id: int | None = None,
    username: str | None = None,
) -> int:
    init_storage(database_path)
    payload = json.dumps(result.to_dict())
    top_speaker_ratio = 0.0
    if result.speaker_dominance.speakers:
        top_speaker_ratio = float(result.speaker_dominance.speakers[0].get("dominance_ratio", 0.0))
    top_decision_id = (
        str(result.workflow_model.prioritized_decisions[0].get("decision_id"))
        if result.workflow_model.prioritized_decisions
        else None
    )
    agentic_contract = result.metadata.get("agentic_contract", {}) if isinstance(result.metadata, dict) else {}
    risk_signals = agentic_contract.get("entities", {}).get("risk_signals", []) if isinstance(agentic_contract, dict) else []
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO meetings (
                user_id,
                username,
                run_name,
                input_video,
                output_dir,
                result_file,
                transcript_text,
                speaker_count,
                decision_count,
                visual_artifact_count,
                top_decision_id,
                overall_attention,
                overall_sentiment,
                impact_score,
                productivity_score,
                execution_readiness,
                dominance_ratio,
                analysis_profile,
                source_mode,
                run_status,
                execution_task_count,
                risk_signal_count,
                contract_version,
                result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                username,
                output_dir.name if output_dir is not None else None,
                result.input_video,
                str(output_dir) if output_dir is not None else None,
                str(result_file) if result_file is not None else None,
                result.transcript.full_text,
                len(result.speaker_dominance.speakers),
                len(result.decision_moments),
                len(result.visual_artifacts),
                top_decision_id,
                result.attention_sentiment.overall_attention,
                result.attention_sentiment.overall_sentiment,
                result.meeting_scores.impact_score,
                result.meeting_scores.productivity_score,
                result.meeting_scores.execution_readiness,
                top_speaker_ratio,
                result.metadata.get("analysis_profile"),
                result.metadata.get("source_mode"),
                "completed",
                len(result.workflow_model.execution_plan),
                len(risk_signals),
                agentic_contract.get("contract_version"),
                payload,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def list_meeting_results(database_path: Path, user_id: int | None = None) -> list[dict]:
    init_storage(database_path)
    query = """
        SELECT
            id,
            user_id,
            username,
            run_name,
            input_video,
            output_dir,
            result_file,
            speaker_count,
            decision_count,
            visual_artifact_count,
            top_decision_id,
            overall_attention,
            overall_sentiment,
            impact_score,
            productivity_score,
            execution_readiness,
            dominance_ratio,
            analysis_profile,
            source_mode,
            run_status,
            execution_task_count,
            risk_signal_count,
            contract_version,
            created_at
        FROM meetings
    """
    params: tuple = ()
    if user_id is not None:
        query += " WHERE user_id = ?"
        params = (user_id,)
    query += " ORDER BY id DESC"

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_meeting_result(database_path: Path, meeting_id: int, user_id: int | None = None) -> dict | None:
    init_storage(database_path)
    query = "SELECT * FROM meetings WHERE id = ?"
    params: tuple = (meeting_id,)
    if user_id is not None:
        query += " AND user_id = ?"
        params = (meeting_id, user_id)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(query, params).fetchone()
    return dict(row) if row is not None else None
