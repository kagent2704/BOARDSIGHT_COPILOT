from __future__ import annotations

import json
from pathlib import Path

from boardsight_ai.database import execute, table_columns
from boardsight_ai.agentic_contract import build_agentic_contract
from boardsight_ai.models import pipeline_result_from_dict
from boardsight_ai.storage import (
    create_live_session,
    get_live_session,
    get_meeting_result,
    init_storage,
    list_live_sessions,
    list_meeting_results,
    protect_sensitive_storage,
    save_meeting_result,
)


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


def test_finalized_live_session_is_saved_to_history_once(tmp_path: Path, sample_pipeline_result) -> None:
    db_path = tmp_path / "meetings.db"

    first_id = save_meeting_result(
        db_path,
        sample_pipeline_result,
        output_dir=Path("Live-Board-Review"),
        user_id=7,
        username="admin",
        organization_id=3,
        live_session_id=42,
    )
    second_id = save_meeting_result(
        db_path,
        sample_pipeline_result,
        output_dir=Path("Live-Board-Review"),
        user_id=7,
        username="admin",
        organization_id=3,
        live_session_id=42,
    )

    listing = list_meeting_results(db_path, organization_id=3)
    assert second_id == first_id
    assert len(listing) == 1
    assert listing[0]["source_mode"] == sample_pipeline_result.metadata.get("source_mode")


def test_sensitive_storage_is_encrypted_at_rest_and_decrypted_on_read(tmp_path: Path, sample_pipeline_result, monkeypatch) -> None:
    monkeypatch.setenv("BOARDSIGHT_DATA_ENCRYPTION_KEY", "boardsight-test-encryption-key")
    db_path = tmp_path / "meetings.db"
    output_dir = tmp_path / "secure-run"
    output_dir.mkdir()
    result_file = output_dir / "boardsight_result.json"
    result_file.write_text(json.dumps(sample_pipeline_result.to_dict()), encoding="utf-8")

    meeting_id = save_meeting_result(
        db_path,
        sample_pipeline_result,
        output_dir=output_dir,
        result_file=result_file,
        user_id=9,
        username="secure-user",
    )
    session_id = create_live_session(db_path, "Protected session", user_id=9, username="secure-user")

    raw_meeting = execute_and_fetch(
        db_path,
        "SELECT transcript_text, result_json FROM meetings WHERE id = :meeting_id",
        {"meeting_id": meeting_id},
    )
    raw_session = execute_and_fetch(
        db_path,
        "SELECT title FROM live_sessions WHERE id = :session_id",
        {"session_id": session_id},
    )
    assert raw_meeting is not None
    assert raw_session is not None
    assert str(raw_meeting["transcript_text"]).startswith("bsenc:v1:")
    assert str(raw_meeting["result_json"]).startswith("bsenc:v1:")
    assert str(raw_session["title"]).startswith("bsenc:v1:")

    stored = get_meeting_result(db_path, meeting_id, user_id=9)
    live_session = get_live_session(db_path, session_id, user_id=9)

    assert stored is not None
    assert live_session is not None
    assert stored["transcript_text"] == sample_pipeline_result.transcript.full_text
    assert json.loads(str(stored["result_json"]))["input_video"] == sample_pipeline_result.input_video
    assert live_session["title"] == "Protected session"


def test_pipeline_result_from_dict_round_trips_sample(sample_pipeline_result) -> None:
    restored = pipeline_result_from_dict(sample_pipeline_result.to_dict())

    assert restored.input_video == sample_pipeline_result.input_video
    assert restored.transcript.full_text == sample_pipeline_result.transcript.full_text
    assert len(restored.transcript.segments) == len(sample_pipeline_result.transcript.segments)
    assert restored.visual_artifacts[0].artifact_type == sample_pipeline_result.visual_artifacts[0].artifact_type
    assert restored.workflow_model.execution_plan[0]["title"] == sample_pipeline_result.workflow_model.execution_plan[0]["title"]


def test_protect_sensitive_storage_encrypts_legacy_plaintext_rows(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BOARDSIGHT_DATA_ENCRYPTION_KEY", "boardsight-test-encryption-key")
    db_path = tmp_path / "legacy.db"
    init_storage(db_path)

    execute(
        db_path,
        """
        INSERT INTO meetings (
            user_id, username, run_name, input_video, transcript_text,
            result_json, speaker_count, decision_count, visual_artifact_count
        ) VALUES (
            1, 'legacy', 'legacy-run', 'demo.mp4', 'plain transcript',
            '{"title":"legacy"}', 1, 1, 0
        )
        """,
    )

    protection = protect_sensitive_storage(db_path)
    row = execute_and_fetch(db_path, "SELECT transcript_text, result_json FROM meetings WHERE username = 'legacy'")

    assert protection["updated_rows"] >= 1
    assert row is not None
    assert str(row["transcript_text"]).startswith("bsenc:v1:")
    assert str(row["result_json"]).startswith("bsenc:v1:")


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


def execute_and_fetch(db_path: Path, sql: str, params: dict | None = None):
    from boardsight_ai.database import fetchone

    return fetchone(db_path, sql, params or {})
