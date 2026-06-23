from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from boardsight_ai.database import execute, fetchone, is_postgres


def init_live_storage(database_path: Path) -> None:
    if is_postgres(database_path):
        execute(
            database_path,
            """
            CREATE TABLE IF NOT EXISTS live_sessions (
                session_id TEXT PRIMARY KEY,
                user_id BIGINT,
                username TEXT,
                title TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                source_type TEXT,
                analysis_profile TEXT,
                output_dir TEXT,
                transcript_json TEXT NOT NULL DEFAULT '[]',
                state_json TEXT NOT NULL DEFAULT '{}',
                final_result_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )
    else:
        execute(
            database_path,
            """
            CREATE TABLE IF NOT EXISTS live_sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER,
                username TEXT,
                title TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                source_type TEXT,
                analysis_profile TEXT,
                output_dir TEXT,
                transcript_json TEXT NOT NULL DEFAULT '[]',
                state_json TEXT NOT NULL DEFAULT '{}',
                final_result_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )


def create_live_session(
    database_path: Path,
    *,
    session_id: str,
    user_id: int | None,
    username: str | None,
    title: str,
    source_type: str,
    analysis_profile: str,
    output_dir: Path,
) -> None:
    init_live_storage(database_path)
    execute(
        database_path,
        """
        INSERT INTO live_sessions (
            session_id, user_id, username, title, status, source_type, analysis_profile, output_dir,
            transcript_json, state_json, final_result_json
        ) VALUES (
            :session_id, :user_id, :username, :title, 'active', :source_type, :analysis_profile, :output_dir,
            '[]', '{}', NULL
        )
        """,
        {
            "session_id": session_id,
            "user_id": user_id,
            "username": username,
            "title": title,
            "source_type": source_type,
            "analysis_profile": analysis_profile,
            "output_dir": str(output_dir),
        },
    )


def get_live_session(database_path: Path, session_id: str, user_id: int | None = None) -> dict[str, Any] | None:
    init_live_storage(database_path)
    query = "SELECT * FROM live_sessions WHERE session_id = :session_id"
    params: dict[str, Any] = {"session_id": session_id}
    if user_id is not None:
        query += " AND user_id = :user_id"
        params["user_id"] = user_id
    return fetchone(database_path, query, params)


def update_live_session(
    database_path: Path,
    session_id: str,
    *,
    transcript: list[dict[str, Any]],
    state: dict[str, Any],
    status: str | None = None,
    final_result: dict[str, Any] | None = None,
) -> None:
    init_live_storage(database_path)
    execute(
        database_path,
        """
        UPDATE live_sessions
        SET transcript_json = :transcript_json,
            state_json = :state_json,
            status = COALESCE(:status, status),
            final_result_json = COALESCE(:final_result_json, final_result_json),
            updated_at = CURRENT_TIMESTAMP
        WHERE session_id = :session_id
        """,
        {
            "transcript_json": json.dumps(transcript),
            "state_json": json.dumps(state),
            "status": status,
            "final_result_json": json.dumps(final_result) if final_result is not None else None,
            "session_id": session_id,
        },
    )


def parse_live_session_record(record: dict[str, Any]) -> dict[str, Any]:
    parsed = dict(record)
    parsed["transcript"] = json.loads(str(record.get("transcript_json") or "[]"))
    parsed["state"] = json.loads(str(record.get("state_json") or "{}"))
    parsed["final_result"] = json.loads(str(record.get("final_result_json") or "null"))
    return parsed
