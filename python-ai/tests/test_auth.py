from __future__ import annotations

from pathlib import Path

from boardsight_ai.auth import (
    authenticate_credentials,
    authenticate_user,
    cleanup_expired_sessions,
    create_user,
    get_session_user,
    get_user_by_email,
    get_user_by_username,
    issue_email_verification_token,
    legacy_hash_password,
    revoke_session,
    upsert_admin_user,
    verify_email_token,
)
from boardsight_ai.database import execute, fetchone


def test_create_user_and_authenticate_by_username_and_email(tmp_path: Path) -> None:
    db_path = tmp_path / "auth.db"

    created = create_user(
        db_path,
        username="admin",
        password="boardsight123",
        role="admin",
        display_name="BoardSight Admin",
        email="admin@example.com",
        email_verified=True,
    )

    assert created is True
    assert create_user(db_path, "admin", "boardsight123") is False

    by_username = authenticate_user(db_path, "admin", "boardsight123")
    assert by_username is not None
    assert by_username["username"] == "admin"
    assert by_username["display_name"] == "BoardSight Admin"

    by_email = authenticate_user(db_path, "admin@example.com", "boardsight123")
    assert by_email is not None
    assert by_email["email"] == "admin@example.com"
    assert str(by_email["expires_at"])

    session_user = get_session_user(db_path, by_email["token"])
    assert session_user is not None
    assert session_user["role"] == "admin"


def test_unverified_user_cannot_authenticate_until_token_is_verified(tmp_path: Path) -> None:
    db_path = tmp_path / "auth.db"
    created = create_user(
        db_path,
        username="newuser",
        password="super-secret",
        role="analyst",
        display_name="New User",
        email="newuser@example.com",
        email_verified=False,
    )
    assert created is True

    session = authenticate_user(db_path, "newuser@example.com", "super-secret")
    assert session is None

    user, reason = authenticate_credentials(db_path, "newuser@example.com", "super-secret")
    assert user is not None
    assert reason == "email_not_verified"

    token = issue_email_verification_token(db_path, int(user["user_id"]), "newuser@example.com")
    verified = verify_email_token(db_path, token)
    assert verified is not None
    assert verified["email"] == "newuser@example.com"

    verified_session = authenticate_user(db_path, "newuser@example.com", "super-secret")
    assert verified_session is not None
    assert verified_session["email_verified"] is True


def test_session_revocation_and_cleanup(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "auth.db"
    monkeypatch.setenv("BOARDSIGHT_SESSION_TTL_SECONDS", "600")
    create_user(db_path, "kash", "secret", display_name="Kash Mira", email="kash@example.com")

    session = authenticate_user(db_path, "kash", "secret")
    assert session is not None
    assert get_session_user(db_path, session["token"]) is not None

    revoke_session(db_path, session["token"])
    assert get_session_user(db_path, session["token"]) is None

    deleted_count = cleanup_expired_sessions(db_path)
    assert deleted_count == 1


def test_legacy_sha256_hash_is_upgraded_after_successful_login(tmp_path: Path) -> None:
    db_path = tmp_path / "auth.db"
    create_user(db_path, "legacy", "secret", display_name="Legacy User", email="legacy@example.com")
    execute(
        db_path,
        "UPDATE users SET password_hash = :password_hash WHERE LOWER(username) = LOWER(:username)",
        {
            "username": "legacy",
            "password_hash": legacy_hash_password("secret"),
        },
    )

    session = authenticate_user(db_path, "legacy", "secret")
    assert session is not None

    row = fetchone(db_path, "SELECT password_hash FROM users WHERE LOWER(username) = LOWER(:username)", {"username": "legacy"})
    assert row is not None
    assert str(row["password_hash"]).startswith("$argon2")


def test_get_user_lookup_helpers_are_case_insensitive(tmp_path: Path) -> None:
    db_path = tmp_path / "auth.db"
    create_user(db_path, "Kash", "secret", display_name="Kash Mira", email="kash@example.com")

    by_username = get_user_by_username(db_path, "kash")
    by_email = get_user_by_email(db_path, "KASH@example.com")

    assert by_username is not None
    assert by_username["username"] == "Kash"
    assert by_username["display_name"] == "Kash Mira"
    assert by_email is not None
    assert by_email["username"] == "Kash"


def test_upsert_admin_user_promotes_existing_email_owner(tmp_path: Path) -> None:
    db_path = tmp_path / "auth.db"
    create_user(
        db_path,
        "kashnt007",
        "secret",
        role="executive_observer",
        display_name="Kashmira",
        email="kashmiraspatil@gmail.com",
    )

    admin_user = upsert_admin_user(
        db_path,
        username="kashmira_admin",
        password="kashmira1234",
        email="kashmiraspatil@gmail.com",
        display_name="Kashmira Admin",
    )

    assert admin_user["username"] == "kashmira_admin"
    assert admin_user["role"] == "admin"
    assert admin_user["email"] == "kashmiraspatil@gmail.com"

    session = authenticate_user(db_path, "kashmira_admin", "kashmira1234")
    assert session is not None
