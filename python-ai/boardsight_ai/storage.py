from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from boardsight_ai.database import execute, fetchall, fetchone, insert_and_return_id, is_postgres, table_columns
from boardsight_ai.models import PipelineResult


def init_storage(database_path: Path) -> None:
    numeric_id_type = "BIGSERIAL" if is_postgres(database_path) else "INTEGER"
    auto_increment = " PRIMARY KEY" if is_postgres(database_path) else " PRIMARY KEY AUTOINCREMENT"
    float_type = "DOUBLE PRECISION" if is_postgres(database_path) else "REAL"
    timestamp_type = "TIMESTAMP" if is_postgres(database_path) else "TEXT"
    created_default = "CURRENT_TIMESTAMP"

    execute(
        database_path,
        f"""
        CREATE TABLE IF NOT EXISTS meetings (
            id {numeric_id_type}{auto_increment},
            user_id {"BIGINT" if is_postgres(database_path) else "INTEGER"},
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
            overall_attention {float_type} DEFAULT 0,
            overall_sentiment TEXT,
            impact_score {float_type} DEFAULT 0,
            productivity_score {float_type} DEFAULT 0,
            execution_readiness {float_type} DEFAULT 0,
            dominance_ratio {float_type} DEFAULT 0,
            runtime_profile TEXT,
            data_contract_version TEXT,
            analysis_profile TEXT,
            source_mode TEXT,
            run_status TEXT DEFAULT 'completed',
            execution_task_count INTEGER DEFAULT 0,
            risk_signal_count INTEGER DEFAULT 0,
            contract_version TEXT,
            result_json TEXT NOT NULL,
            created_at {timestamp_type} DEFAULT {created_default}
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
        "overall_attention": f"{float_type} DEFAULT 0",
        "overall_sentiment": "TEXT",
        "impact_score": f"{float_type} DEFAULT 0",
        "productivity_score": f"{float_type} DEFAULT 0",
        "execution_readiness": f"{float_type} DEFAULT 0",
        "dominance_ratio": f"{float_type} DEFAULT 0",
        "runtime_profile": "TEXT",
        "data_contract_version": "TEXT",
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

    execute(
        database_path,
        f"""
        CREATE TABLE IF NOT EXISTS live_sessions (
            id {numeric_id_type}{auto_increment},
            user_id {"BIGINT" if is_postgres(database_path) else "INTEGER"},
            username TEXT,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            transcript_text TEXT DEFAULT '',
            started_at {timestamp_type} DEFAULT {created_default},
            updated_at {timestamp_type} DEFAULT {created_default},
            finalized_at {timestamp_type},
            last_copilot_source TEXT DEFAULT '',
            last_copilot_answer TEXT DEFAULT ''
        )
        """,
    )

    live_session_columns = table_columns(database_path, "live_sessions")
    if "id" not in live_session_columns:
        if is_postgres(database_path):
            execute(database_path, "ALTER TABLE live_sessions ADD COLUMN id BIGINT")
            execute(database_path, "CREATE SEQUENCE IF NOT EXISTS live_sessions_id_seq")
            execute(database_path, "ALTER TABLE live_sessions ALTER COLUMN id SET DEFAULT nextval('live_sessions_id_seq')")
            execute(database_path, "UPDATE live_sessions SET id = nextval('live_sessions_id_seq') WHERE id IS NULL")
        else:
            execute(database_path, "ALTER TABLE live_sessions ADD COLUMN id INTEGER")
            execute(database_path, "UPDATE live_sessions SET id = rowid WHERE id IS NULL")
        live_session_columns = table_columns(database_path, "live_sessions")
    required_live_session_columns: dict[str, str] = {
        "user_id": "BIGINT" if is_postgres(database_path) else "INTEGER",
        "username": "TEXT",
        "status": "TEXT NOT NULL DEFAULT 'active'",
        "transcript_text": "TEXT DEFAULT ''",
        "started_at": f"{timestamp_type} DEFAULT {created_default}",
        "updated_at": f"{timestamp_type} DEFAULT {created_default}",
        "finalized_at": timestamp_type,
        "last_copilot_source": "TEXT DEFAULT ''",
        "last_copilot_answer": "TEXT DEFAULT ''",
    }
    for column_name, column_type in required_live_session_columns.items():
        if column_name not in live_session_columns:
            execute(database_path, f"ALTER TABLE live_sessions ADD COLUMN {column_name} {column_type}")

    execute(
        database_path,
        f"""
        CREATE TABLE IF NOT EXISTS live_session_events (
            id {numeric_id_type}{auto_increment},
            session_id {"BIGINT" if is_postgres(database_path) else "INTEGER"} NOT NULL,
            speaker TEXT,
            text TEXT NOT NULL,
            start_seconds {float_type} DEFAULT 0,
            end_seconds {float_type} DEFAULT 0,
            created_at {timestamp_type} DEFAULT {created_default}
        )
        """,
    )

    live_event_columns = table_columns(database_path, "live_session_events")
    required_live_event_columns: dict[str, str] = {
        "speaker": "TEXT",
        "start_seconds": f"{float_type} DEFAULT 0",
        "end_seconds": f"{float_type} DEFAULT 0",
        "created_at": f"{timestamp_type} DEFAULT {created_default}",
    }
    for column_name, column_type in required_live_event_columns.items():
        if column_name not in live_event_columns:
            execute(database_path, f"ALTER TABLE live_session_events ADD COLUMN {column_name} {column_type}")

    execute(
        database_path,
        f"""
        CREATE TABLE IF NOT EXISTS live_session_visual_events (
            id {numeric_id_type}{auto_increment},
            session_id {"BIGINT" if is_postgres(database_path) else "INTEGER"} NOT NULL,
            timestamp_seconds {float_type} DEFAULT 0,
            artifact_type TEXT DEFAULT '',
            display_mode TEXT DEFAULT '',
            visible_people_count INTEGER DEFAULT 0,
            screen_present INTEGER DEFAULT 0,
            chart_present INTEGER DEFAULT 0,
            document_present INTEGER DEFAULT 0,
            textual_content TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            confidence {float_type} DEFAULT 0,
            detections_json TEXT DEFAULT '[]',
            source TEXT DEFAULT '',
            created_at {timestamp_type} DEFAULT {created_default}
        )
        """,
    )

    live_visual_columns = table_columns(database_path, "live_session_visual_events")
    required_live_visual_columns: dict[str, str] = {
        "timestamp_seconds": f"{float_type} DEFAULT 0",
        "artifact_type": "TEXT DEFAULT ''",
        "display_mode": "TEXT DEFAULT ''",
        "visible_people_count": "INTEGER DEFAULT 0",
        "screen_present": "INTEGER DEFAULT 0",
        "chart_present": "INTEGER DEFAULT 0",
        "document_present": "INTEGER DEFAULT 0",
        "textual_content": "TEXT DEFAULT ''",
        "summary": "TEXT DEFAULT ''",
        "confidence": f"{float_type} DEFAULT 0",
        "detections_json": "TEXT DEFAULT '[]'",
        "source": "TEXT DEFAULT ''",
        "created_at": f"{timestamp_type} DEFAULT {created_default}",
    }
    for column_name, column_type in required_live_visual_columns.items():
        if column_name not in live_visual_columns:
            execute(database_path, f"ALTER TABLE live_session_visual_events ADD COLUMN {column_name} {column_type}")


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
            runtime_profile,
            data_contract_version,
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
            :runtime_profile,
            :data_contract_version,
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
            "runtime_profile": str(result.metadata.get("performance_report", {}).get("runtime_profile", "")),
            "data_contract_version": str(result.metadata.get("data_contract_version", "")),
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
            runtime_profile,
            data_contract_version,
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


def create_live_session(database_path: Path, title: str, user_id: int | None = None, username: str | None = None) -> int:
    init_storage(database_path)
    live_session_columns = table_columns(database_path, "live_sessions")
    params: dict[str, object] = {"user_id": user_id, "username": username, "title": title}
    insert_columns = ["user_id", "username", "title"]
    insert_values = [":user_id", ":username", ":title"]
    if "session_id" in live_session_columns:
        params["session_id"] = f"live-{uuid4().hex}"
        insert_columns.insert(0, "session_id")
        insert_values.insert(0, ":session_id")
        if not is_postgres(database_path):
            next_id_row = fetchone(database_path, "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM live_sessions")
            params["id"] = int(next_id_row["next_id"]) if next_id_row and next_id_row.get("next_id") is not None else 1
            insert_columns.insert(0, "id")
            insert_values.insert(0, ":id")
    return insert_and_return_id(
        database_path,
        f"INSERT INTO live_sessions ({', '.join(insert_columns)}) VALUES ({', '.join(insert_values)})",
        params,
    )


def append_live_session_event(
    database_path: Path,
    session_id: int,
    text: str,
    speaker: str | None = None,
    start_seconds: float | None = None,
    end_seconds: float | None = None,
) -> int:
    init_storage(database_path)
    normalized_text = str(text or "").strip()
    if not normalized_text:
        raise ValueError("Live session event text is required.")
    start_value = float(start_seconds or 0.0)
    end_value = float(end_seconds if end_seconds is not None else start_value + 4.0)
    event_id = insert_and_return_id(
        database_path,
        """
        INSERT INTO live_session_events (session_id, speaker, text, start_seconds, end_seconds)
        VALUES (:session_id, :speaker, :text, :start_seconds, :end_seconds)
        """,
        {
            "session_id": session_id,
            "speaker": speaker,
            "text": normalized_text,
            "start_seconds": start_value,
            "end_seconds": end_value,
        },
    )
    event_rows = get_live_session_events(database_path, session_id)
    transcript_text = " ".join(
        f"{row['speaker']}: {row['text']}" if str(row.get("speaker") or "").strip() else str(row.get("text") or "")
        for row in event_rows
    ).strip()
    execute(
        database_path,
        """
        UPDATE live_sessions
        SET transcript_text = :transcript_text, updated_at = CURRENT_TIMESTAMP
        WHERE id = :session_id
        """,
        {"transcript_text": transcript_text, "session_id": session_id},
    )
    return event_id


def list_live_sessions(database_path: Path, user_id: int | None = None, status: str | None = None) -> list[dict]:
    init_storage(database_path)
    query = """
        SELECT
            id,
            user_id,
            username,
            title,
            status,
            transcript_text,
            started_at,
            updated_at,
            finalized_at,
            last_copilot_source,
            last_copilot_answer
        FROM live_sessions
    """
    params: dict[str, object] = {}
    filters: list[str] = []
    if user_id is not None:
        filters.append("user_id = :user_id")
        params["user_id"] = user_id
    if status is not None:
        filters.append("status = :status")
        params["status"] = status
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY id DESC"
    return fetchall(database_path, query, params)


def get_live_session(database_path: Path, session_id: int, user_id: int | None = None) -> dict | None:
    init_storage(database_path)
    query = "SELECT * FROM live_sessions WHERE id = :session_id"
    params: dict[str, object] = {"session_id": session_id}
    if user_id is not None:
        query += " AND user_id = :user_id"
        params["user_id"] = user_id
    return fetchone(database_path, query, params)


def get_live_session_events(database_path: Path, session_id: int) -> list[dict]:
    init_storage(database_path)
    return fetchall(
        database_path,
        """
        SELECT id, session_id, speaker, text, start_seconds, end_seconds, created_at
        FROM live_session_events
        WHERE session_id = :session_id
        ORDER BY id
        """,
        {"session_id": session_id},
    )


def append_live_visual_event(
    database_path: Path,
    session_id: int,
    timestamp_seconds: float,
    artifact_type: str,
    display_mode: str,
    visible_people_count: int,
    screen_present: bool,
    chart_present: bool,
    document_present: bool,
    textual_content: str,
    summary: str,
    confidence: float,
    detections: list[dict] | None = None,
    source: str = "",
) -> int:
    init_storage(database_path)
    visual_event_id = insert_and_return_id(
        database_path,
        """
        INSERT INTO live_session_visual_events (
            session_id,
            timestamp_seconds,
            artifact_type,
            display_mode,
            visible_people_count,
            screen_present,
            chart_present,
            document_present,
            textual_content,
            summary,
            confidence,
            detections_json,
            source
        ) VALUES (
            :session_id,
            :timestamp_seconds,
            :artifact_type,
            :display_mode,
            :visible_people_count,
            :screen_present,
            :chart_present,
            :document_present,
            :textual_content,
            :summary,
            :confidence,
            :detections_json,
            :source
        )
        """,
        {
            "session_id": session_id,
            "timestamp_seconds": float(timestamp_seconds),
            "artifact_type": str(artifact_type or ""),
            "display_mode": str(display_mode or ""),
            "visible_people_count": int(visible_people_count or 0),
            "screen_present": 1 if screen_present else 0,
            "chart_present": 1 if chart_present else 0,
            "document_present": 1 if document_present else 0,
            "textual_content": str(textual_content or ""),
            "summary": str(summary or ""),
            "confidence": float(confidence or 0.0),
            "detections_json": json.dumps(detections or []),
            "source": str(source or ""),
        },
    )
    execute(
        database_path,
        "UPDATE live_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = :session_id",
        {"session_id": session_id},
    )
    return visual_event_id


def get_live_session_visual_events(database_path: Path, session_id: int) -> list[dict]:
    init_storage(database_path)
    rows = fetchall(
        database_path,
        """
        SELECT
            id,
            session_id,
            timestamp_seconds,
            artifact_type,
            display_mode,
            visible_people_count,
            screen_present,
            chart_present,
            document_present,
            textual_content,
            summary,
            confidence,
            detections_json,
            source,
            created_at
        FROM live_session_visual_events
        WHERE session_id = :session_id
        ORDER BY id
        """,
        {"session_id": session_id},
    )
    items: list[dict] = []
    for row in rows:
        item = dict(row)
        try:
            item["detections"] = json.loads(str(item.get("detections_json") or "[]"))
        except json.JSONDecodeError:
            item["detections"] = []
        items.append(item)
    return items


def finalize_live_session(database_path: Path, session_id: int) -> None:
    init_storage(database_path)
    execute(
        database_path,
        """
        UPDATE live_sessions
        SET status = 'finalized', finalized_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE id = :session_id
        """,
        {"session_id": session_id},
    )


def save_live_copilot_reply(database_path: Path, session_id: int, answer: str, source: str) -> None:
    init_storage(database_path)
    execute(
        database_path,
        """
        UPDATE live_sessions
        SET last_copilot_answer = :answer,
            last_copilot_source = :source,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :session_id
        """,
        {"answer": answer, "source": source, "session_id": session_id},
    )
