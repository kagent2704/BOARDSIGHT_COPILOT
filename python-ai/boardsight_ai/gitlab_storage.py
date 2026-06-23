from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from boardsight_ai.database import execute, insert_and_return_id, is_postgres


def init_gitlab_storage(database_path: Path) -> None:
    if is_postgres(database_path):
        execute(
            database_path,
            """
            CREATE TABLE IF NOT EXISTS gitlab_syncs (
                id BIGSERIAL PRIMARY KEY,
                source_kind TEXT NOT NULL,
                source_id TEXT NOT NULL,
                project_ref TEXT,
                dry_run INTEGER NOT NULL DEFAULT 1,
                plan_json TEXT NOT NULL,
                sync_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )
    else:
        execute(
            database_path,
            """
            CREATE TABLE IF NOT EXISTS gitlab_syncs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_kind TEXT NOT NULL,
                source_id TEXT NOT NULL,
                project_ref TEXT,
                dry_run INTEGER NOT NULL DEFAULT 1,
                plan_json TEXT NOT NULL,
                sync_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """,
        )


def save_gitlab_sync(
    database_path: Path,
    *,
    source_kind: str,
    source_id: str,
    project_ref: str | None,
    dry_run: bool,
    plan: dict[str, Any],
    sync_result: dict[str, Any] | None,
) -> int:
    init_gitlab_storage(database_path)
    return insert_and_return_id(
        database_path,
        """
        INSERT INTO gitlab_syncs (
            source_kind, source_id, project_ref, dry_run, plan_json, sync_json
        ) VALUES (
            :source_kind, :source_id, :project_ref, :dry_run, :plan_json, :sync_json
        )
        """,
        {
            "source_kind": source_kind,
            "source_id": source_id,
            "project_ref": project_ref,
            "dry_run": 1 if dry_run else 0,
            "plan_json": json.dumps(plan),
            "sync_json": json.dumps(sync_result) if sync_result is not None else None,
        },
    )
