from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from boardsight_ai.data_protection import decrypt_json_text, encrypt_text
from boardsight_ai.database import execute, insert_and_return_id, is_postgres


def init_gitlab_storage(database_path: Path) -> None:
    if is_postgres(database_path):
        execute(
            database_path,
            """
            CREATE TABLE IF NOT EXISTS gitlab_syncs (
                id BIGSERIAL PRIMARY KEY,
                organization_id BIGINT,
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
                organization_id INTEGER,
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
    try:
        execute(database_path, "ALTER TABLE gitlab_syncs ADD COLUMN organization_id BIGINT")
    except Exception:
        pass


def save_gitlab_sync(
    database_path: Path,
    *,
    source_kind: str,
    source_id: str,
    organization_id: int | None = None,
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
            organization_id, source_kind, source_id, project_ref, dry_run, plan_json, sync_json
        ) VALUES (
            :organization_id, :source_kind, :source_id, :project_ref, :dry_run, :plan_json, :sync_json
        )
        """,
        {
            "organization_id": organization_id,
            "source_kind": source_kind,
            "source_id": source_id,
            "project_ref": project_ref,
            "dry_run": 1 if dry_run else 0,
            "plan_json": encrypt_text(json.dumps(plan)),
            "sync_json": encrypt_text(json.dumps(sync_result)) if sync_result is not None else None,
        },
    )


def protect_gitlab_storage(database_path: Path) -> dict[str, int]:
    init_gitlab_storage(database_path)
    rows_updated = 0
    rows = []
    try:
        from boardsight_ai.database import fetchall

        rows = fetchall(database_path, "SELECT id, plan_json, sync_json FROM gitlab_syncs")
    except Exception:
        return {"updated_rows": 0}
    for row in rows:
        updates: dict[str, object] = {"id": row["id"]}
        assignments: list[str] = []
        for column in ("plan_json", "sync_json"):
            if row.get(column) is None:
                continue
            encrypted = encrypt_text(decrypt_json_text(row.get(column)))
            if encrypted != row.get(column):
                updates[column] = encrypted
                assignments.append(f"{column} = :{column}")
        if assignments:
            execute(database_path, f"UPDATE gitlab_syncs SET {', '.join(assignments)} WHERE id = :id", updates)
            rows_updated += 1
    return {"updated_rows": rows_updated}
