from __future__ import annotations

from fastapi.testclient import TestClient

from boardsight_ai.auth import create_user, get_user_by_username, issue_email_verification_token
from boardsight_ai.service import app


def test_register_returns_verification_pending_without_blocking_delivery(tmp_path, monkeypatch) -> None:
    auth_db = tmp_path / "auth.db"
    meeting_db = tmp_path / "meetings.db"

    monkeypatch.setattr("boardsight_ai.service.AUTH_DB_PATH", auth_db)
    monkeypatch.setattr("boardsight_ai.service.MEETING_DB_PATH", meeting_db)
    monkeypatch.setattr("boardsight_ai.service._email_provider_is_configured", lambda: True)

    delivery_calls: list[dict[str, str]] = []

    def fake_send_verification_email_safe(*, to_email: str, display_name: str, verification_url: str) -> None:
        delivery_calls.append(
            {
                "to_email": to_email,
                "display_name": display_name,
                "verification_url": verification_url,
            }
        )

    monkeypatch.setattr("boardsight_ai.service._send_verification_email_safe", fake_send_verification_email_safe)

    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "newgovernanceuser",
            "email": "newgovernanceuser@example.com",
            "password": "super-secret",
            "confirm_password": "super-secret",
            "display_name": "New Governance User",
            "role": "analyst",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "verification_pending"
    assert payload["verification_sent"] is True
    assert payload["email_delivery"]["queued"] is True
    assert delivery_calls
    assert delivery_calls[0]["to_email"] == "newgovernanceuser@example.com"


def test_verify_email_renders_html_for_browser_requests(tmp_path, monkeypatch) -> None:
    auth_db = tmp_path / "auth.db"
    meeting_db = tmp_path / "meetings.db"

    monkeypatch.setattr("boardsight_ai.service.AUTH_DB_PATH", auth_db)
    monkeypatch.setattr("boardsight_ai.service.MEETING_DB_PATH", meeting_db)

    create_user(
        auth_db,
        username="verifyme",
        password="secret",
        display_name="Verify Me",
        email="verifyme@example.com",
        email_verified=False,
    )
    user = get_user_by_username(auth_db, "verifyme")
    assert user is not None
    token = issue_email_verification_token(auth_db, int(user["user_id"]), "verifyme@example.com")

    client = TestClient(app)
    response = client.get(
        f"/api/v1/auth/verify-email?token={token}",
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Your account is verified and ready to use." in response.text
    assert "Open BoardSight" in response.text


def test_verify_email_keeps_json_for_api_clients(tmp_path, monkeypatch) -> None:
    auth_db = tmp_path / "auth.db"
    meeting_db = tmp_path / "meetings.db"

    monkeypatch.setattr("boardsight_ai.service.AUTH_DB_PATH", auth_db)
    monkeypatch.setattr("boardsight_ai.service.MEETING_DB_PATH", meeting_db)

    create_user(
        auth_db,
        username="jsonverify",
        password="secret",
        display_name="Json Verify",
        email="jsonverify@example.com",
        email_verified=False,
    )
    user = get_user_by_username(auth_db, "jsonverify")
    assert user is not None
    token = issue_email_verification_token(auth_db, int(user["user_id"]), "jsonverify@example.com")

    client = TestClient(app)
    response = client.get(
        f"/api/v1/auth/verify-email?token={token}",
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "verified"
    assert response.json()["email"] == "jsonverify@example.com"
