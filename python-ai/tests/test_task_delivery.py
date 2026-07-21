from __future__ import annotations

from pathlib import Path

import pytest

from boardsight_ai.config import AppConfig
from boardsight_ai import task_delivery
from boardsight_ai.service import app


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(project_root=tmp_path, output_root=tmp_path / "output")


def _plan() -> dict:
    return {
        "issues": [
            {
                "local_key": "GL-1",
                "title": "Publish board packet",
                "description": "Prepare the final governance packet.",
                "owner": "Kashmira",
                "due_date": "2026-07-25",
                "dependencies": [],
            }
        ],
        "issue_links": [],
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("gitlab", "gitlab"),
        ("notion", "notion"),
        ("trello", "trello"),
        ("microsoft", "microsoft-todo"),
        ("ms_todo", "microsoft-todo"),
    ],
)
def test_normalize_assignment_provider(value: str, expected: str) -> None:
    assert task_delivery.normalize_assignment_provider(value) == expected


def test_notion_sync_creates_database_page(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict] = []

    def fake_request(url: str, **kwargs):
        calls.append({"url": url, **kwargs})
        if kwargs.get("method") == "POST":
            return {"id": "page-1", "url": "https://notion.so/page-1"}
        return {"properties": {"Task": {"type": "title"}}}

    monkeypatch.setattr(task_delivery, "_request_json", fake_request)
    result = task_delivery.sync_plan_to_provider(
        "notion",
        _plan(),
        _config(tmp_path),
        connection_overrides={"target_id": "database-1", "access_token": "secret"},
    )

    assert result["status"] == "synced"
    assert result["created_tasks"][0]["id"] == "page-1"
    assert calls[1]["payload"]["properties"]["Task"]["title"][0]["text"]["content"] == "Publish board packet"


def test_trello_sync_preserves_string_member_ids(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict = {}

    def fake_request(url: str, **kwargs):
        captured.update(kwargs.get("payload") or {})
        return {"id": "card-1", "name": "Publish board packet", "shortUrl": "https://trello.com/c/card-1"}

    monkeypatch.setattr(task_delivery, "_request_json", fake_request)
    result = task_delivery.sync_plan_to_provider(
        "trello",
        _plan(),
        _config(tmp_path),
        connection_overrides={
            "target_id": "list-1",
            "api_key": "key",
            "access_token": "token",
            "assignee_map": {"kashmira": "member-abc"},
        },
    )

    assert result["created_tasks"][0]["id"] == "card-1"
    assert captured["idMembers"] == ["member-abc"]
    assert captured["due"].startswith("2026-07-25")


def test_microsoft_todo_missing_credentials_stays_dry_run(tmp_path: Path) -> None:
    result = task_delivery.sync_plan_to_provider("microsoft-todo", _plan(), _config(tmp_path))
    assert result["status"] == "dry-run-only"
    assert "Graph access token" in result["reason"]


def test_microsoft_todo_sync_maps_due_date(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict = {}

    def fake_request(url: str, **kwargs):
        captured.update(kwargs.get("payload") or {})
        return {"id": "todo-1", "title": "Publish board packet"}

    monkeypatch.setattr(task_delivery, "_request_json", fake_request)
    result = task_delivery.sync_plan_to_provider(
        "microsoft-todo",
        _plan(),
        _config(tmp_path),
        connection_overrides={"target_id": "list-1", "access_token": "graph-token"},
    )

    assert result["created_tasks"][0]["id"] == "todo-1"
    assert captured["dueDateTime"]["timeZone"] == "UTC"
    assert captured["body"]["contentType"] == "text"


def test_provider_connection_summary_never_returns_token(tmp_path: Path) -> None:
    summary = task_delivery.provider_connection_summary(
        "notion",
        _config(tmp_path),
        {"target_id": "database-1", "access_token": "do-not-return"},
    )
    assert summary["has_access_token"] is True
    assert "access_token" not in summary


@pytest.mark.parametrize(
    ("provider", "overrides", "response", "expected_url", "destination_name"),
    [
        (
            "gitlab",
            {"base_url": "https://gitlab.example", "target_id": "group/project", "access_token": "secret"},
            {"path_with_namespace": "group/project"},
            "https://gitlab.example/api/v4/projects/group%2Fproject",
            "group/project",
        ),
        (
            "notion",
            {"target_id": "database-1", "access_token": "secret"},
            {"title": [{"plain_text": "Launch Board"}]},
            "https://api.notion.com/v1/databases/database-1",
            "Launch Board",
        ),
        (
            "trello",
            {"target_id": "list-1", "api_key": "key", "access_token": "secret"},
            {"name": "Launch Tasks"},
            "https://api.trello.com/1/lists/list-1",
            "Launch Tasks",
        ),
    ],
)
def test_validate_provider_connection_masks_secrets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: str,
    overrides: dict,
    response: dict,
    expected_url: str,
    destination_name: str,
) -> None:
    captured: dict = {}

    def fake_request(url: str, **kwargs):
        captured.update({"url": url, **kwargs})
        return response

    monkeypatch.setattr(task_delivery, "_request_json", fake_request)
    result = task_delivery.validate_provider_connection(provider, _config(tmp_path), overrides)

    assert captured["url"].startswith(expected_url)
    assert result["status"] == "connected"
    assert result["destination_name"] == destination_name
    assert result["has_access_token"] is True
    assert "access_token" not in result


def test_recorded_and_live_assignment_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}
    assert "/api/v1/meetings/{meeting_id}/assignments/{provider}/preview" in paths
    assert "/api/v1/meetings/{meeting_id}/assignments/{provider}/sync" in paths
    assert "/api/v1/live/{session_id}/assignments/{provider}/preview" in paths
    assert "/api/v1/live/{session_id}/assignments/{provider}/sync" in paths
    assert "/api/v1/workspaces/{organization_id}/integrations" in paths
    assert "/api/v1/workspaces/{organization_id}/integrations/{provider}" in paths
