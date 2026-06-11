from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any


def init_agent_storage(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_execution_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                approval_id TEXT NOT NULL UNIQUE,
                source_kind TEXT NOT NULL,
                source_id TEXT NOT NULL,
                meeting_title TEXT NOT NULL,
                action_type TEXT NOT NULL DEFAULT 'gitlab-sync',
                status TEXT NOT NULL DEFAULT 'previewed',
                created_by_user_id INTEGER,
                approved_by_user_id INTEGER,
                plan_json TEXT NOT NULL,
                connection_json TEXT,
                sync_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()


def create_agent_execution_run(
    database_path: Path,
    *,
    source_kind: str,
    source_id: str,
    meeting_title: str,
    created_by_user_id: int | None,
    plan: dict[str, Any],
    action_type: str = "gitlab-sync",
) -> dict[str, Any]:
    init_agent_storage(database_path)
    approval_id = uuid.uuid4().hex[:16]
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO agent_execution_runs (
                approval_id, source_kind, source_id, meeting_title, action_type,
                status, created_by_user_id, plan_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approval_id,
                source_kind,
                source_id,
                meeting_title,
                action_type,
                "previewed",
                created_by_user_id,
                json.dumps(plan),
            ),
        )
        connection.commit()
    return get_agent_execution_run(database_path, approval_id) or {}


def get_agent_execution_run(database_path: Path, approval_id: str) -> dict[str, Any] | None:
    init_agent_storage(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT *
            FROM agent_execution_runs
            WHERE approval_id = ?
            """,
            (approval_id,),
        ).fetchone()
    if row is None:
        return None
    payload = dict(row)
    for key in ("plan_json", "connection_json", "sync_json"):
        raw = payload.get(key)
        if raw:
            payload[key] = json.loads(str(raw))
        else:
            payload[key] = None
    return payload


def update_agent_execution_run(
    database_path: Path,
    approval_id: str,
    *,
    status: str,
    approved_by_user_id: int | None = None,
    connection: dict[str, Any] | None = None,
    sync_result: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    init_agent_storage(database_path)
    with sqlite3.connect(database_path) as connection_db:
        connection_db.execute(
            """
            UPDATE agent_execution_runs
            SET status = ?,
                approved_by_user_id = COALESCE(?, approved_by_user_id),
                connection_json = COALESCE(?, connection_json),
                sync_json = COALESCE(?, sync_json),
                updated_at = CURRENT_TIMESTAMP
            WHERE approval_id = ?
            """,
            (
                status,
                approved_by_user_id,
                json.dumps(connection) if connection is not None else None,
                json.dumps(sync_result) if sync_result is not None else None,
                approval_id,
            ),
        )
        connection_db.commit()
    return get_agent_execution_run(database_path, approval_id)
