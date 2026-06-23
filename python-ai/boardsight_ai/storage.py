from __future__ import annotations

import json
from pathlib import Path

from boardsight_ai.database import execute, fetchall, fetchone, insert_and_return_id, is_postgres, table_columns
from boardsight_ai.models import PipelineResult


def init_storage(database_path: Path) -> None:
    if is_postgres(database_path):
        execute(
            database_path,
            """
            CREATE TABLE IF NOT EXISTS meetings (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT,
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
                overall_attention DOUBLE PRECISION DEFAULT 0,
                overall_sentiment TEXT,
                impact_score DOUBLE PRECISION DEFAULT 0,
                productivity_score DOUBLE PRECISION DEFAULT 0,
                execution_readiness DOUBLE PRECISION DEFAULT 0,
                dominance_ratio DOUBLE PRECISION DEFAULT 0,
                analysis_profile TEXT,
                source_mode TEXT,
                run_status TEXT DEFAULT 'completed',
                execution_task_count INTEGER DEFAULT 0,
                risk_signal_count INTEGER DEFAULT 0,
                contract_version TEXT,
                result_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )
    else:
        execute(
            database_path,
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
            """,
        )

    existing_columns = table_columns(database_path, "meetings")
    required_columns: dict[str, str] = {
        "user_id": "BIGINT" if is_postgres(database_path) else "INTEGER",
        "username": "TEXT",
        "run_name": "TEXT",
        "output_dir": "TEXT",
        "result_file": "TEXT",
        "transcript_text": "TEXT",
        "speaker_count": "INTEGER DEFAULT 0",
        "decision_count": "INTEGER DEFAULT 0",
        "visual_artifact_count": "INTEGER DEFAULT 0",
        "top_decision_id": "TEXT",
        "overall_attention": "DOUBLE PRECISION DEFAULT 0" if is_postgres(database_path) else "REAL DEFAULT 0",
        "overall_sentiment": "TEXT",
        "impact_score": "DOUBLE PRECISION DEFAULT 0" if is_postgres(database_path) else "REAL DEFAULT 0",
        "productivity_score": "DOUBLE PRECISION DEFAULT 0" if is_postgres(database_path) else "REAL DEFAULT 0",
        "execution_readiness": "DOUBLE PRECISION DEFAULT 0" if is_postgres(database_path) else "REAL DEFAULT 0",
        "dominance_ratio": "DOUBLE PRECISION DEFAULT 0" if is_postgres(database_path) else "REAL DEFAULT 0",
        "analysis_profile": "TEXT",
        "source_mode": "TEXT",
        "run_status": "TEXT DEFAULT 'completed'",
        "execution_task_count": "INTEGER DEFAULT 0",
        "risk_signal_count": "INTEGER DEFAULT 0",
        "contract_version": "TEXT",
    }
    for column_name, column_type in required_columns.items():
        if column_name not in existing_columns:
            execute(database_path, f"ALTER TABLE meetings ADD COLUMN {column_name} {column_type}")


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
    return insert_and_return_id(
        database_path,
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
        ) VALUES (
            :user_id,
            :username,
            :run_name,
            :input_video,
            :output_dir,
            :result_file,
            :transcript_text,
            :speaker_count,
            :decision_count,
            :visual_artifact_count,
            :top_decision_id,
            :overall_attention,
            :overall_sentiment,
            :impact_score,
            :productivity_score,
            :execution_readiness,
            :dominance_ratio,
            :analysis_profile,
            :source_mode,
            :run_status,
            :execution_task_count,
            :risk_signal_count,
            :contract_version,
            :result_json
        )
        """,
        {
            "user_id": user_id,
            "username": username,
            "run_name": output_dir.name if output_dir is not None else None,
            "input_video": result.input_video,
            "output_dir": str(output_dir) if output_dir is not None else None,
            "result_file": str(result_file) if result_file is not None else None,
            "transcript_text": result.transcript.full_text,
            "speaker_count": len(result.speaker_dominance.speakers),
            "decision_count": len(result.decision_moments),
            "visual_artifact_count": len(result.visual_artifacts),
            "top_decision_id": top_decision_id,
            "overall_attention": result.attention_sentiment.overall_attention,
            "overall_sentiment": result.attention_sentiment.overall_sentiment,
            "impact_score": result.meeting_scores.impact_score,
            "productivity_score": result.meeting_scores.productivity_score,
            "execution_readiness": result.meeting_scores.execution_readiness,
            "dominance_ratio": top_speaker_ratio,
            "analysis_profile": result.metadata.get("analysis_profile"),
            "source_mode": result.metadata.get("source_mode"),
            "run_status": "completed",
            "execution_task_count": len(result.workflow_model.execution_plan),
            "risk_signal_count": len(risk_signals),
            "contract_version": agentic_contract.get("contract_version"),
            "result_json": payload,
        },
    )


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
    params: dict[str, object] = {}
    if user_id is not None:
        query += " WHERE user_id = :user_id"
        params["user_id"] = user_id
    query += " ORDER BY id DESC"
    return fetchall(database_path, query, params)


def get_meeting_result(database_path: Path, meeting_id: int, user_id: int | None = None) -> dict | None:
    init_storage(database_path)
    query = "SELECT * FROM meetings WHERE id = :meeting_id"
    params: dict[str, object] = {"meeting_id": meeting_id}
    if user_id is not None:
        query += " AND user_id = :user_id"
        params["user_id"] = user_id
    return fetchone(database_path, query, params)
