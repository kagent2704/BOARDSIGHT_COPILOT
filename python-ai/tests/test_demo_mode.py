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
    monkeypatch.setattr(demo_mode, "get_user_by_username", lambda *_args, **_kwargs: user)
    monkeypatch.setattr(
        demo_mode,
        "create_session_for_user",
        lambda database_path, trusted_user: {"token": "demo-token", **trusted_user},
    )

    session = demo_mode.create_demo_session(auth_db_path, meeting_db_path)

    assert session["token"] == "demo-token"
    assert session["demo"] == manifest
