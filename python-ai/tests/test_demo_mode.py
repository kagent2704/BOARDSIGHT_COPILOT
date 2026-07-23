from __future__ import annotations

from pathlib import Path

from boardsight_ai import demo_mode
from boardsight_ai.auth import create_user, get_user_by_username, init_auth_storage
from boardsight_ai.storage import init_storage, list_meeting_results
from boardsight_ai.workspaces import ensure_personal_workspace, init_workspace_storage


def test_existing_demo_session_skips_password_authentication(monkeypatch, tmp_path: Path) -> None:
    auth_db_path = tmp_path / "auth.db"
    meeting_db_path = tmp_path / "meetings.db"
    manifest = {"featuredMeetingId": 42, "preferredView": "dashboard"}
    user = {
        "user_id": 7,
        "username": "boardsight_demo",
        "email": "boardsight_demo@boardsight.local",
        "display_name": "BoardSight Demo",
        "role": "admin",
        "email_verified": True,
    }

    monkeypatch.setattr(demo_mode, "ensure_demo_workspace", lambda *_args, **_kwargs: manifest)
    monkeypatch.setattr(demo_mode, "_get_demo_user", lambda *_args, **_kwargs: user)
    monkeypatch.setattr(
        demo_mode,
        "create_session_for_user",
        lambda database_path, trusted_user: {"token": "demo-token", **trusted_user},
    )

    session = demo_mode.create_demo_session(auth_db_path, meeting_db_path)

    assert session["token"] == "demo-token"
    assert session["demo"] == manifest


def test_initialized_service_path_skips_schema_setup(monkeypatch, tmp_path: Path) -> None:
    user = {"user_id": 7, "username": "boardsight_demo"}
    manifest = {"featuredMeetingId": 42}

    monkeypatch.setattr(demo_mode, "init_auth_storage", lambda *_args: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(demo_mode, "init_storage", lambda *_args: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(demo_mode, "_upsert_demo_user", lambda *_args: user)
    monkeypatch.setattr(demo_mode, "_existing_demo_workspace", lambda *_args: manifest)

    result = demo_mode.ensure_demo_workspace(
        tmp_path / "auth.db",
        tmp_path / "meetings.db",
        initialize=False,
    )

    assert result == manifest


def test_permanent_sample_runs_are_workspace_scoped_and_idempotent(tmp_path: Path) -> None:
    auth_db_path = tmp_path / "auth.db"
    meeting_db_path = tmp_path / "meetings.db"
    init_auth_storage(auth_db_path)
    init_storage(meeting_db_path)
    init_workspace_storage(meeting_db_path)
    assert create_user(
        auth_db_path,
        "kashmira_admin",
        "safe-test-password",
        "admin",
        display_name="Kashmira Admin",
        email="kashmira@example.com",
        email_verified=True,
    )

    first = demo_mode.ensure_permanent_sample_workspaces(
        auth_db_path,
        meeting_db_path,
        usernames=("kashmira_admin",),
    )
    second = demo_mode.ensure_permanent_sample_workspaces(
        auth_db_path,
        meeting_db_path,
        usernames=("kashmira_admin",),
    )

    user = get_user_by_username(auth_db_path, "kashmira_admin")
    assert user is not None
    workspace = ensure_personal_workspace(meeting_db_path, user)
    rows = list_meeting_results(meeting_db_path, organization_id=int(workspace["id"]))
    sample_rows = [row for row in rows if str(row.get("run_name") or "").startswith(demo_mode.SAMPLE_RUN_PREFIX)]
    assert first["seeded"] == ["kashmira_admin"]
    assert second["already_present"] == ["kashmira_admin"]
    assert len(sample_rows) == 3
