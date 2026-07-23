from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from boardsight_ai.database import execute, fetchall


PERMANENT_SAMPLE_PREFIX = "boardsight sample:"
PERMANENT_DEMO_USERNAME = os.getenv("BOARDSIGHT_DEMO_USERNAME", "boardsight_demo").strip().lower() or "boardsight_demo"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _cutoff(days: int) -> str:
    cutoff = _utcnow() - timedelta(days=max(1, days))
    return cutoff.strftime("%Y-%m-%d %H:%M:%S")


def _safe_remove_path(candidate: str, root: Path) -> bool:
    if not candidate:
        return False
    path = Path(candidate).resolve()
    root_resolved = root.resolve()
    if not str(path).startswith(str(root_resolved)):
        return False
    if not path.exists():
        return False
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)
    return True


def cleanup_expired_data(
    database_path: Path,
    *,
    output_root: Path,
    meeting_retention_days: int,
    live_session_retention_days: int,
    report_retention_days: int,
) -> dict[str, Any]:
    meeting_cutoff = _cutoff(meeting_retention_days)
    live_cutoff = _cutoff(live_session_retention_days)
    report_cutoff = _cutoff(report_retention_days)

    report_rows = fetchall(
        database_path,
        """
        SELECT id, output_dir, result_file
        FROM meetings
        WHERE created_at <= :report_cutoff
          AND LOWER(COALESCE(run_name, '')) NOT LIKE :sample_prefix
          AND (COALESCE(output_dir, '') <> '' OR COALESCE(result_file, '') <> '')
        """,
        {"report_cutoff": report_cutoff, "sample_prefix": f"{PERMANENT_SAMPLE_PREFIX}%"},
    )
    removed_report_paths = 0
    for row in report_rows:
        removed_dir = _safe_remove_path(str(row.get("output_dir") or ""), output_root)
        removed_file = _safe_remove_path(str(row.get("result_file") or ""), output_root)
        if removed_dir or removed_file:
            removed_report_paths += int(removed_dir) + int(removed_file)
        execute(
            database_path,
            """
            UPDATE meetings
            SET output_dir = NULL,
                result_file = NULL
            WHERE id = :meeting_id
            """,
            {"meeting_id": int(row["id"])},
        )

    expired_meeting_rows = fetchall(
        database_path,
        """
        SELECT id, output_dir, result_file
        FROM meetings
        WHERE created_at <= :meeting_cutoff
          AND LOWER(COALESCE(run_name, '')) NOT LIKE :sample_prefix
        """,
        {"meeting_cutoff": meeting_cutoff, "sample_prefix": f"{PERMANENT_SAMPLE_PREFIX}%"},
    )
    deleted_meetings = len(expired_meeting_rows)
    for row in expired_meeting_rows:
        _safe_remove_path(str(row.get("output_dir") or ""), output_root)
        _safe_remove_path(str(row.get("result_file") or ""), output_root)
    execute(
        database_path,
        "DELETE FROM meetings WHERE created_at <= :meeting_cutoff AND LOWER(COALESCE(run_name, '')) NOT LIKE :sample_prefix",
        {"meeting_cutoff": meeting_cutoff, "sample_prefix": f"{PERMANENT_SAMPLE_PREFIX}%"},
    )

    expired_live_rows = fetchall(
        database_path,
        """
        SELECT id
        FROM live_sessions
        WHERE COALESCE(finalized_at, updated_at, started_at) <= :live_cutoff
          AND LOWER(COALESCE(username, '')) <> :demo_username
        """,
        {"live_cutoff": live_cutoff, "demo_username": PERMANENT_DEMO_USERNAME},
    )
    deleted_live_sessions = len(expired_live_rows)
    if expired_live_rows:
        session_ids = [int(row["id"]) for row in expired_live_rows]
        for session_id in session_ids:
            execute(database_path, "DELETE FROM live_session_events WHERE session_id = :session_id", {"session_id": session_id})
            execute(database_path, "DELETE FROM live_session_visual_events WHERE session_id = :session_id", {"session_id": session_id})
            execute(database_path, "DELETE FROM live_sessions WHERE id = :session_id", {"session_id": session_id})

    return {
        "deleted_meetings": deleted_meetings,
        "deleted_live_sessions": deleted_live_sessions,
        "cleared_report_paths": removed_report_paths,
        "meeting_retention_days": meeting_retention_days,
        "live_session_retention_days": live_session_retention_days,
        "report_retention_days": report_retention_days,
    }
