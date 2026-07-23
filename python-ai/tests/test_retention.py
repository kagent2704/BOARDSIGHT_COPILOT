from __future__ import annotations

import json
from pathlib import Path

from boardsight_ai.database import execute, fetchall, fetchone
from boardsight_ai.retention import cleanup_expired_data
from boardsight_ai.storage import append_live_session_event, create_live_session, init_storage


def test_cleanup_expired_data_removes_old_meetings_live_sessions_and_reports(tmp_path: Path) -> None:
    db_path = tmp_path / "meetings.db"
    output_root = tmp_path / "output"
    output_root.mkdir()
    init_storage(db_path)

    old_dir = output_root / "old-run"
    old_dir.mkdir()
    old_result = old_dir / "boardsight_result.json"
    old_result.write_text("{}", encoding="utf-8")

    execute_payload = {
        "user_id": 7,
        "username": "kash",
        "run_name": "old-run",
        "input_video": "demo.mp4",
        "output_dir": str(old_dir),
        "result_file": str(old_result),
        "transcript_text": "hello",
        "speaker_count": 1,
        "decision_count": 1,
        "visual_artifact_count": 0,
        "top_decision_id": "D1",
        "overall_attention": 50.0,
        "overall_sentiment": "neutral",
        "impact_score": 50.0,
        "productivity_score": 50.0,
        "execution_readiness": 50.0,
        "dominance_ratio": 50.0,
        "runtime_profile": "test",
        "data_contract_version": "v1",
        "analysis_profile": "recorded-fast",
        "source_mode": "recorded",
        "run_status": "completed",
        "execution_task_count": 1,
        "risk_signal_count": 0,
        "contract_version": "v1",
        "result_json": json.dumps({"title": "old"}),
    }
    execute(
        db_path,
        """
        INSERT INTO meetings (
            user_id, username, run_name, input_video, output_dir, result_file, transcript_text,
            speaker_count, decision_count, visual_artifact_count, top_decision_id, overall_attention,
            overall_sentiment, impact_score, productivity_score, execution_readiness, dominance_ratio,
            runtime_profile, data_contract_version, analysis_profile, source_mode, run_status,
            execution_task_count, risk_signal_count, contract_version, result_json, created_at
        ) VALUES (
            :user_id, :username, :run_name, :input_video, :output_dir, :result_file, :transcript_text,
            :speaker_count, :decision_count, :visual_artifact_count, :top_decision_id, :overall_attention,
            :overall_sentiment, :impact_score, :productivity_score, :execution_readiness, :dominance_ratio,
            :runtime_profile, :data_contract_version, :analysis_profile, :source_mode, :run_status,
            :execution_task_count, :risk_signal_count, :contract_version, :result_json, '2000-01-01 00:00:00'
        )
        """,
        execute_payload,
    )

    session_id = create_live_session(db_path, "Old Live Session", user_id=7, username="kash")
    append_live_session_event(db_path, session_id, "Legacy transcript.", speaker="Kash", start_seconds=0, end_seconds=2)
    execute(
        db_path,
        "UPDATE live_sessions SET started_at = '2000-01-01 00:00:00', updated_at = '2000-01-01 00:00:00' WHERE id = :session_id",
        {"session_id": session_id},
    )

    cleanup = cleanup_expired_data(
        db_path,
        output_root=output_root,
        meeting_retention_days=30,
        live_session_retention_days=14,
        report_retention_days=30,
    )

    assert cleanup["deleted_meetings"] == 1
    assert cleanup["deleted_live_sessions"] == 1
    assert not old_dir.exists()
    assert fetchone(db_path, "SELECT id FROM meetings") is None
    assert fetchone(db_path, "SELECT id FROM live_sessions") is None


def test_cleanup_preserves_permanent_sample_meetings(tmp_path: Path) -> None:
    db_path = tmp_path / "meetings.db"
    output_root = tmp_path / "output"
    output_root.mkdir()
    init_storage(db_path)
    execute(
        db_path,
        """
        INSERT INTO meetings (user_id, username, run_name, input_video, result_json, created_at)
        VALUES (7, 'kashmira_admin', 'boardsight sample: board review launch readiness', 'sample.mp4', '{}', '2000-01-01 00:00:00')
        """,
    )
    execute(
        db_path,
        """
        INSERT INTO meetings (user_id, username, run_name, input_video, result_json, created_at)
        VALUES (7, 'kashmira_admin', 'ordinary old run', 'old.mp4', '{}', '2000-01-01 00:00:00')
        """,
    )

    cleanup = cleanup_expired_data(
        db_path,
        output_root=output_root,
        meeting_retention_days=30,
        live_session_retention_days=14,
        report_retention_days=30,
    )

    rows = fetchall(db_path, "SELECT run_name FROM meetings ORDER BY id")
    assert cleanup["deleted_meetings"] == 1
    assert [row["run_name"] for row in rows] == ["boardsight sample: board review launch readiness"]
