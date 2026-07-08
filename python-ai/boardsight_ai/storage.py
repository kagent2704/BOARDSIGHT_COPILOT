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
                runtime_profile TEXT,
                data_contract_version TEXT,
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
            "runtime_profile": "TEXT",
            "data_contract_version": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(f"ALTER TABLE meetings ADD COLUMN {column_name} {column_type}")

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS live_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                transcript_text TEXT DEFAULT '',
                started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                finalized_at TEXT,
                last_copilot_source TEXT DEFAULT '',
                last_copilot_answer TEXT DEFAULT ''
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS live_session_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                speaker TEXT,
                text TEXT NOT NULL,
                start_seconds REAL DEFAULT 0,
                end_seconds REAL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES live_sessions(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS live_session_visual_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                timestamp_seconds REAL DEFAULT 0,
                artifact_type TEXT DEFAULT '',
                display_mode TEXT DEFAULT '',
                visible_people_count INTEGER DEFAULT 0,
                screen_present INTEGER DEFAULT 0,
                chart_present INTEGER DEFAULT 0,
                document_present INTEGER DEFAULT 0,
                textual_content TEXT DEFAULT '',
                summary TEXT DEFAULT '',
                confidence REAL DEFAULT 0,
                detections_json TEXT DEFAULT '[]',
                source TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES live_sessions(id) ON DELETE CASCADE
            )
            """
        )

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
                runtime_profile,
                data_contract_version,
                result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                str(result.metadata.get("performance_report", {}).get("runtime_profile", "")),
                str(result.metadata.get("data_contract_version", "")),
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
            runtime_profile,
            data_contract_version,
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


def create_live_session(database_path: Path, title: str, user_id: int | None = None, username: str | None = None) -> int:
    init_storage(database_path)
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO live_sessions (user_id, username, title)
            VALUES (?, ?, ?)
            """,
            (user_id, username, title),
        )
        connection.commit()
        return int(cursor.lastrowid)


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
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO live_session_events (session_id, speaker, text, start_seconds, end_seconds)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, speaker, normalized_text, start_value, end_value),
        )
        transcript_row = connection.execute(
            """
            SELECT GROUP_CONCAT(
                CASE
                    WHEN speaker IS NOT NULL AND TRIM(speaker) <> '' THEN speaker || ': ' || text
                    ELSE text
                END,
                ' '
            )
            FROM live_session_events
            WHERE session_id = ?
            ORDER BY id
            """,
            (session_id,),
        ).fetchone()
        transcript_text = str((transcript_row[0] if transcript_row is not None else "") or "")
        connection.execute(
            """
            UPDATE live_sessions
            SET transcript_text = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (transcript_text, session_id),
        )
        connection.commit()
        return int(cursor.lastrowid)


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
    params: list[object] = []
    filters: list[str] = []
    if user_id is not None:
        filters.append("user_id = ?")
        params.append(user_id)
    if status is not None:
        filters.append("status = ?")
        params.append(status)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY id DESC"
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def get_live_session(database_path: Path, session_id: int, user_id: int | None = None) -> dict | None:
    init_storage(database_path)
    query = "SELECT * FROM live_sessions WHERE id = ?"
    params: tuple[object, ...] = (session_id,)
    if user_id is not None:
        query += " AND user_id = ?"
        params = (session_id, user_id)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(query, params).fetchone()
    return dict(row) if row is not None else None


def get_live_session_events(database_path: Path, session_id: int) -> list[dict]:
    init_storage(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, session_id, speaker, text, start_seconds, end_seconds, created_at
            FROM live_session_events
            WHERE session_id = ?
            ORDER BY id
            """,
            (session_id,),
        ).fetchall()
    return [dict(row) for row in rows]


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
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                float(timestamp_seconds),
                str(artifact_type or ""),
                str(display_mode or ""),
                int(visible_people_count or 0),
                1 if screen_present else 0,
                1 if chart_present else 0,
                1 if document_present else 0,
                str(textual_content or ""),
                str(summary or ""),
                float(confidence or 0.0),
                json.dumps(detections or []),
                str(source or ""),
            ),
        )
        connection.execute(
            """
            UPDATE live_sessions
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (session_id,),
        )
        connection.commit()
        return int(cursor.lastrowid)


def get_live_session_visual_events(database_path: Path, session_id: int) -> list[dict]:
    init_storage(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
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
            WHERE session_id = ?
            ORDER BY id
            """,
            (session_id,),
        ).fetchall()
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
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE live_sessions
            SET status = 'finalized',
                finalized_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (session_id,),
        )
        connection.commit()


def save_live_copilot_reply(database_path: Path, session_id: int, answer: str, source: str) -> None:
    init_storage(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE live_sessions
            SET last_copilot_answer = ?,
                last_copilot_source = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (answer, source, session_id),
        )
        connection.commit()
