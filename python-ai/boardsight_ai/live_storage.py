from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def init_live_storage(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
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
            """
        )
        connection.commit()


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
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO live_sessions (
                session_id, user_id, username, title, status, source_type, analysis_profile, output_dir,
                transcript_json, state_json, final_result_json
            ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, '[]', '{}', NULL)
            """,
            (
                session_id,
                user_id,
                username,
                title,
                source_type,
                analysis_profile,
                str(output_dir),
            ),
        )
        connection.commit()


def get_live_session(database_path: Path, session_id: str, user_id: int | None = None) -> dict[str, Any] | None:
    init_live_storage(database_path)
    query = "SELECT * FROM live_sessions WHERE session_id = ?"
    params: tuple[Any, ...] = (session_id,)
    if user_id is not None:
        query += " AND user_id = ?"
        params = (session_id, user_id)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(query, params).fetchone()
    return dict(row) if row is not None else None


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
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE live_sessions
            SET transcript_json = ?,
                state_json = ?,
                status = COALESCE(?, status),
                final_result_json = COALESCE(?, final_result_json),
                updated_at = CURRENT_TIMESTAMP
            WHERE session_id = ?
            """,
            (
                json.dumps(transcript),
                json.dumps(state),
                status,
                json.dumps(final_result) if final_result is not None else None,
                session_id,
            ),
        )
        connection.commit()


def parse_live_session_record(record: dict[str, Any]) -> dict[str, Any]:
    parsed = dict(record)
    parsed["transcript"] = json.loads(str(record.get("transcript_json") or "[]"))
    parsed["state"] = json.loads(str(record.get("state_json") or "{}"))
    parsed["final_result"] = json.loads(str(record.get("final_result_json") or "null"))
    return parsed
