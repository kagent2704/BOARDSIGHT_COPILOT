from __future__ import annotations

from pathlib import Path

from boardsight_ai.config import AppConfig
from boardsight_ai.live_session import answer_live_copilot, build_live_session_payload
from boardsight_ai.storage import (
    append_live_session_event,
    create_live_session,
    finalize_live_session,
    get_live_session,
    get_live_session_events,
)


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(project_root=tmp_path, output_root=tmp_path / "out", analysis_profile="production")


def test_live_session_storage_roundtrip(tmp_path: Path) -> None:
    database_path = tmp_path / "meetings.db"
    session_id = create_live_session(database_path, "Board review", user_id=7, username="kash")
    append_live_session_event(database_path, session_id, "We approved the agenda.", speaker="Kash", start_seconds=0, end_seconds=4)
    append_live_session_event(database_path, session_id, "I will share the report tomorrow.", speaker="Akanksha", start_seconds=5, end_seconds=9)

    session_row = get_live_session(database_path, session_id, user_id=7)
    event_rows = get_live_session_events(database_path, session_id)

    assert session_row is not None
    assert session_row["title"] == "Board review"
    assert "Kash: We approved the agenda." in session_row["transcript_text"]
    assert len(event_rows) == 2

    finalize_live_session(database_path, session_id)
    finalized_row = get_live_session(database_path, session_id, user_id=7)
    assert finalized_row is not None
    assert finalized_row["status"] == "finalized"


def test_live_copilot_answers_from_live_context(tmp_path: Path) -> None:
    config = _config(tmp_path)
    session_row = {
        "id": 4,
        "title": "Governance sync",
        "status": "active",
        "started_at": "2026-07-08T10:00:00",
        "updated_at": "2026-07-08T10:05:00",
        "finalized_at": "",
        "username": "kash",
    }
    event_rows = [
        {"speaker": "Kash", "text": "We approved the roadmap for Q3.", "start_seconds": 0, "end_seconds": 4},
        {"speaker": "Akanksha", "text": "I will share the metrics deck by Friday.", "start_seconds": 6, "end_seconds": 10},
        {"speaker": "Kash", "text": "The blocker is delayed vendor access.", "start_seconds": 12, "end_seconds": 16},
    ]

    payload = build_live_session_payload(session_row, event_rows, config)
    answer, source = answer_live_copilot(payload, "What action items should I know right now?", config)

    assert payload["session"]["event_count"] == 3
    assert payload["copilot_context"]["summary"]
    assert "share the metrics deck" in answer.lower()
    assert source in {"live-heuristic", payload["copilot_context"]["source"]}
