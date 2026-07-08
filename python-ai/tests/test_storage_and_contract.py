from __future__ import annotations

import json
from pathlib import Path

from boardsight_ai.database import execute, table_columns
from boardsight_ai.agentic_contract import build_agentic_contract
from boardsight_ai.storage import create_live_session, get_meeting_result, init_storage, list_live_sessions, list_meeting_results, save_meeting_result


def test_save_meeting_result_round_trips_sqlite_record(tmp_path: Path, sample_pipeline_result) -> None:
    db_path = tmp_path / "meetings.db"
    output_dir = tmp_path / "web-run-123"
    output_dir.mkdir()
    result_file = output_dir / "boardsight_result.json"
    result_file.write_text(json.dumps(sample_pipeline_result.to_dict()), encoding="utf-8")

    meeting_id = save_meeting_result(
        db_path,
        sample_pipeline_result,
        output_dir=output_dir,
        result_file=result_file,
        user_id=7,
        username="admin",
    )

    listing = list_meeting_results(db_path, user_id=7)
    stored = get_meeting_result(db_path, meeting_id, user_id=7)

    assert meeting_id > 0
    assert len(listing) == 1
    assert listing[0]["decision_count"] == 1
    assert listing[0]["execution_task_count"] == 2
    assert stored is not None
    assert stored["username"] == "admin"
    assert stored["result_file"] == str(result_file)


def test_build_agentic_contract_includes_actions_and_risk_signals(sample_pipeline_result) -> None:
    contract = build_agentic_contract(
        sample_pipeline_result,
        analysis_profile="recorded-fast",
        source_mode="recorded",
        contract_version="2026-06-10",
    )

    assert contract["contract_version"] == "2026-06-10"
    assert contract["meeting_digest"]["input_video"] == "demo-meeting.mp4"
    assert len(contract["entities"]["decisions"]) == 1
    assert len(contract["entities"]["actions"]) == 2
    assert len(contract["entities"]["risk_signals"]) >= 2
    assert contract["execution_graph"]["top_decision_id"] == "DM-1"


def test_init_storage_migrates_legacy_live_session_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-live.db"
    execute(
        db_path,
        """
        CREATE TABLE live_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL
        )
        """,
    )

    init_storage(db_path)
    session_id = create_live_session(db_path, "Legacy session", user_id=3, username="admin")
    rows = list_live_sessions(db_path, user_id=3, status="active")
    migrated_columns = table_columns(db_path, "live_sessions")

    assert session_id > 0
    assert rows
    assert rows[0]["title"] == "Legacy session"
    assert {"user_id", "username", "status", "transcript_text", "last_copilot_source", "last_copilot_answer"} <= migrated_columns


def test_create_live_session_works_with_legacy_session_id_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-session-id.db"
    execute(
        db_path,
        """
        CREATE TABLE live_sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER,
            username TEXT,
            title TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            transcript_json TEXT NOT NULL DEFAULT '[]',
            state_json TEXT NOT NULL DEFAULT '{}',
            final_result_json TEXT
        )
        """,
    )

    session_id = create_live_session(db_path, "Legacy key session", user_id=9, username="admin")
    rows = list_live_sessions(db_path, user_id=9, status="active")

    assert session_id > 0
    assert rows
    assert rows[0]["id"] == session_id
    assert rows[0]["title"] == "Legacy key session"
