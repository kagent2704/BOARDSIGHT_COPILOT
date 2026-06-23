from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from boardsight_ai.database import execute, fetchone, is_postgres


def init_agent_storage(database_path: Path) -> None:
    if is_postgres(database_path):
        execute(
            database_path,
            """
            CREATE TABLE IF NOT EXISTS agent_execution_runs (
                id BIGSERIAL PRIMARY KEY,
                approval_id TEXT NOT NULL UNIQUE,
                source_kind TEXT NOT NULL,
                source_id TEXT NOT NULL,
                meeting_title TEXT NOT NULL,
                action_type TEXT NOT NULL DEFAULT 'gitlab-sync',
                status TEXT NOT NULL DEFAULT 'previewed',
                created_by_user_id BIGINT,
                approved_by_user_id BIGINT,
                plan_json TEXT NOT NULL,
                connection_json TEXT,
                sync_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )
    else:
        execute(
            database_path,
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
            """,
        )


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
    execute(
        database_path,
        """
        INSERT INTO agent_execution_runs (
            approval_id, source_kind, source_id, meeting_title, action_type,
            status, created_by_user_id, plan_json
        ) VALUES (
            :approval_id, :source_kind, :source_id, :meeting_title, :action_type,
            :status, :created_by_user_id, :plan_json
        )
        """,
        {
            "approval_id": approval_id,
            "source_kind": source_kind,
            "source_id": source_id,
            "meeting_title": meeting_title,
            "action_type": action_type,
            "status": "previewed",
            "created_by_user_id": created_by_user_id,
            "plan_json": json.dumps(plan),
        },
    )
    return get_agent_execution_run(database_path, approval_id) or {}


def get_agent_execution_run(database_path: Path, approval_id: str) -> dict[str, Any] | None:
    init_agent_storage(database_path)
    payload = fetchone(
        database_path,
        """
        SELECT *
        FROM agent_execution_runs
        WHERE approval_id = :approval_id
        """,
        {"approval_id": approval_id},
    )
    if payload is None:
        return None
    for key in ("plan_json", "connection_json", "sync_json"):
        raw = payload.get(key)
        payload[key] = json.loads(str(raw)) if raw else None
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
    execute(
        database_path,
        """
        UPDATE agent_execution_runs
        SET status = :status,
            approved_by_user_id = COALESCE(:approved_by_user_id, approved_by_user_id),
            connection_json = COALESCE(:connection_json, connection_json),
            sync_json = COALESCE(:sync_json, sync_json),
            updated_at = CURRENT_TIMESTAMP
        WHERE approval_id = :approval_id
        """,
        {
            "status": status,
            "approved_by_user_id": approved_by_user_id,
            "connection_json": json.dumps(connection) if connection is not None else None,
            "sync_json": json.dumps(sync_result) if sync_result is not None else None,
            "approval_id": approval_id,
        },
    )
    return get_agent_execution_run(database_path, approval_id)
