from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def init_gitlab_storage(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
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
            """
        )
        connection.commit()


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
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO gitlab_syncs (
                source_kind, source_id, project_ref, dry_run, plan_json, sync_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                source_kind,
                source_id,
                project_ref,
                1 if dry_run else 0,
                json.dumps(plan),
                json.dumps(sync_result) if sync_result is not None else None,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
