from __future__ import annotations

from pathlib import Path

from boardsight_ai import demo_mode


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
