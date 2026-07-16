from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from boardsight_ai.auth import authenticate_user, create_user
from boardsight_ai.models import pipeline_result_from_dict
from boardsight_ai.service import app
from boardsight_ai.storage import get_meeting_result, save_meeting_result, update_meeting_workflow_editor


def _sample_workflow_editor(meeting_id: int) -> dict:
    return {
        "meetingId": str(meeting_id),
        "title": "Board Approval Flow",
        "nodes": [
            {
                "id": "node-start",
                "type": "start",
                "title": "Intake",
                "owner": "BoardSight",
                "status": "Ready",
                "summary": "Meeting loaded",
                "description": "Initial intake with context, transcript coverage, and operating baseline.",
                "notes": "Use the imported transcript and speaker map.",
                "handoffNotes": "Hand off to reviewer after intake validation.",
                "acceptanceCriteria": "Meeting is identified and transcript is available.",
                "decisionId": "",
                "traceId": "",
                "sourceStage": "start",
                "dueDate": "",
                "priority": "Medium",
            },
            {
                "id": "node-review",
                "type": "review",
                "title": "Review evidence",
                "owner": "Kashmira",
                "status": "In review",
                "summary": "Confirm decisions and follow-through.",
                "description": "Review transcript evidence, blockers, and next actions before board circulation.",
                "notes": "Prioritize unresolved ownership gaps.",
                "handoffNotes": "Escalate unresolved blockers to the governance lead.",
                "acceptanceCriteria": "Every decision has an owner or explicit escalation path.",
                "decisionId": "DM-1",
                "traceId": "TRACE-1",
                "sourceStage": "review",
                "dueDate": "2026-07-20",
                "priority": "High",
            },
        ],
        "links": [{"from": "node-start", "to": "node-review", "label": "next"}],
        "meta": {
            "derivedFrom": "heuristic-workflow-engine",
            "status": "saved",
            "overview": "Board approval flow with manual review checkpoints.",
            "notes": "This workflow should stay editable after the first save.",
            "savedAt": "2026-07-15T10:00:00Z",
        },
    }


def test_update_meeting_workflow_editor_persists_rich_fields(tmp_path: Path, sample_pipeline_result) -> None:
    db_path = tmp_path / "meetings.db"
    output_dir = tmp_path / "workflow-run"
    output_dir.mkdir()
    result_file = output_dir / "boardsight_result.json"
    result_file.write_text(json.dumps(sample_pipeline_result.to_dict()), encoding="utf-8")

    meeting_id = save_meeting_result(
        db_path,
        sample_pipeline_result,
        output_dir=output_dir,
        result_file=result_file,
        user_id=7,
        username="tester",
    )
    workflow_editor = _sample_workflow_editor(meeting_id)

    updated = update_meeting_workflow_editor(db_path, meeting_id, workflow_editor, user_id=7)

    assert updated is not None
    payload = json.loads(str(updated["result_json"]))
    assert payload["workflow_editor"]["meta"]["overview"] == "Board approval flow with manual review checkpoints."
    assert payload["workflow_editor"]["nodes"][1]["description"].startswith("Review transcript evidence")
    assert payload["workflow_editor"]["nodes"][1]["handoffNotes"].startswith("Escalate unresolved blockers")
    assert payload["workflow_editor"]["nodes"][1]["acceptanceCriteria"].startswith("Every decision has an owner")
    assert payload["workflow_editor"]["nodes"][1]["traceId"] == "TRACE-1"


def test_update_meeting_workflow_api_saves_server_side_draft(tmp_path: Path, sample_pipeline_result, monkeypatch) -> None:
    auth_db = tmp_path / "auth.db"
    meeting_db = tmp_path / "meetings.db"
    output_dir = tmp_path / "workflow-api-run"
    output_dir.mkdir()
    result_file = output_dir / "boardsight_result.json"
    result_file.write_text(json.dumps(sample_pipeline_result.to_dict()), encoding="utf-8")

    create_user(
        auth_db,
        username="kashmira",
        password="secret123",
        display_name="Kashmira",
        email="kashmira@example.com",
        role="admin",
    )
    session = authenticate_user(auth_db, "kashmira", "secret123")
    assert session is not None

    meeting_id = save_meeting_result(
        meeting_db,
        sample_pipeline_result,
        output_dir=output_dir,
        result_file=result_file,
        user_id=1,
        username="kashmira",
    )

    monkeypatch.setattr("boardsight_ai.service.AUTH_DB_PATH", auth_db)
    monkeypatch.setattr("boardsight_ai.service.MEETING_DB_PATH", meeting_db)

    client = TestClient(app)
    workflow_editor = _sample_workflow_editor(meeting_id)
    response = client.put(
        f"/api/v1/meetings/{meeting_id}/workflow",
        headers={"Authorization": f"Bearer {session['token']}"},
        json={"workflow_editor": workflow_editor},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "saved"
    assert payload["workflow_editor"]["nodes"][1]["description"].startswith("Review transcript evidence")
    assert payload["workflow_editor"]["meta"]["notes"] == "This workflow should stay editable after the first save."
    assert payload["workflow_editor"]["nodes"][1]["traceId"] == "TRACE-1"

    stored = get_meeting_result(meeting_db, meeting_id, user_id=1)
    assert stored is not None
    stored_payload = json.loads(str(stored["result_json"]))
    restored = pipeline_result_from_dict(stored_payload)
    assert restored.workflow_model.execution_plan[0]["title"] == sample_pipeline_result.workflow_model.execution_plan[0]["title"]
    assert stored_payload["workflow_editor"]["nodes"][1]["handoffNotes"].startswith("Escalate unresolved blockers")
