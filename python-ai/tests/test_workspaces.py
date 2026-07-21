from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from boardsight_ai.auth import authenticate_user, create_user
from boardsight_ai.database import execute, fetchall, fetchone
from boardsight_ai.storage import get_meeting_result, init_storage, list_meeting_results, save_meeting_result
from boardsight_ai.workspaces import (
    accept_invitation,
    assert_workspace_access,
    commit_minutes,
    create_invitation,
    create_workspace,
    ensure_personal_workspace,
    delete_workspace_integration,
    get_workspace_integration,
    get_workspace_for_user,
    init_workspace_storage,
    list_workspace_integrations,
    release_minutes,
    request_subscription_change,
    reserve_minutes,
    save_workspace_integration,
    update_member,
    usage_summary,
)
from boardsight_ai.service import app


def _user(user_id: int, email: str, name: str = "BoardSight User") -> dict:
    return {"user_id": user_id, "username": email.split("@", 1)[0], "email": email, "display_name": name}


def test_personal_workspace_backfills_existing_user_content(tmp_path, sample_pipeline_result) -> None:
    db_path = tmp_path / "workspace.db"
    init_storage(db_path)
    meeting_id = save_meeting_result(db_path, sample_pipeline_result, user_id=7, username="kash")

    workspace = ensure_personal_workspace(db_path, _user(7, "kash@example.com", "Kash"))
    stored = get_meeting_result(db_path, meeting_id, organization_id=int(workspace["id"]))

    assert workspace["membership_role"] == "owner"
    assert workspace["plan_code"] == "personal"
    assert stored is not None
    assert stored["organization_id"] == workspace["id"]
    assert stored["created_by_user_id"] == 7


def test_workspace_integration_credentials_are_encrypted_and_round_trip(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "integrations.db"
    monkeypatch.setenv("BOARDSIGHT_DATA_ENCRYPTION_KEY", "workspace-integration-test-key")
    workspace = ensure_personal_workspace(db_path, _user(7, "kash@example.com", "Kash"))
    workspace_id = int(workspace["id"])

    save_workspace_integration(
        db_path,
        workspace_id,
        "notion",
        {"target_id": "database-1", "access_token": "secret-notion-token", "destination_name": "Launch Board"},
        7,
    )

    raw = fetchone(db_path, "SELECT encrypted_config FROM organization_integrations WHERE organization_id = :organization_id", {"organization_id": workspace_id})
    stored = get_workspace_integration(db_path, workspace_id, "notion")
    listed = list_workspace_integrations(db_path, workspace_id)

    assert raw is not None
    assert str(raw["encrypted_config"]).startswith("bsenc:v1:")
    assert "secret-notion-token" not in str(raw["encrypted_config"])
    assert stored is not None and stored["config"]["access_token"] == "secret-notion-token"
    assert listed[0]["config"]["destination_name"] == "Launch Board"

    delete_workspace_integration(db_path, workspace_id, "notion")
    assert get_workspace_integration(db_path, workspace_id, "notion") is None


def test_permanent_sponsorship_exists_before_registration_and_bypasses_customer_charging(tmp_path) -> None:
    db_path = tmp_path / "sponsorship.db"
    init_workspace_storage(db_path)
    sponsorships = fetchall(db_path, "SELECT email FROM billing_sponsorships")
    unregistered = fetchone(db_path, "SELECT * FROM billing_sponsorships WHERE email = :email", {"email": "kashmiraspatil@gmail.com"})

    user = _user(41, "kashmiraspatil@gmail.com", "Kashmira")
    workspace = ensure_personal_workspace(db_path, user)
    execute(db_path, "UPDATE subscriptions SET status = 'past_due' WHERE organization_id = :organization_id", {"organization_id": workspace["id"]})
    sponsored_workspace = get_workspace_for_user(db_path, int(workspace["id"]), 41)
    assert sponsored_workspace is not None
    assert_workspace_access(sponsored_workspace, require_license=True)
    usage = reserve_minutes(db_path, int(workspace["id"]), 41, 500, usage_type="recorded_analysis", event_key="founder-load-test")

    assert {row["email"] for row in sponsorships} == {
        "kashmiraspatil@gmail.com",
        "umeshgirase19@gmail.com",
        "umeshgirase852@gmail.com",
        "kashmirasanjaypatil@gmail.com",
        "patilkashmirasanjay@gmail.com",
    }
    assert unregistered is not None and unregistered["user_id"] is None
    assert sponsored_workspace["billing_mode"] == "internal_sponsored"
    assert sponsored_workspace["user_sponsorship_type"] == "founder"
    assert usage["billing_disposition"] == "internally_sponsored"
    assert usage["sponsorship_id"] == sponsored_workspace["user_sponsorship_id"]


def test_workspace_members_share_organization_scoped_meetings(tmp_path, sample_pipeline_result) -> None:
    db_path = tmp_path / "shared.db"
    init_storage(db_path)
    owner = _user(1, "owner@example.com", "Owner")
    member = _user(2, "member@example.com", "Member")
    ensure_personal_workspace(db_path, owner)
    workspace = create_workspace(db_path, "Acme Governance", 1)
    invitation = create_invitation(db_path, int(workspace["id"]), member["email"], "member", 1)
    accepted = accept_invitation(db_path, invitation["token"], member)
    meeting_id = save_meeting_result(db_path, sample_pipeline_result, user_id=1, username="owner", organization_id=int(workspace["id"]))

    shared_rows = list_meeting_results(db_path, organization_id=int(accepted["id"]))
    shared_meeting = get_meeting_result(db_path, meeting_id, organization_id=int(accepted["id"]))

    assert len(shared_rows) == 1
    assert shared_meeting is not None


def test_invitation_rejects_wrong_email_and_license_limit(tmp_path) -> None:
    db_path = tmp_path / "licenses.db"
    owner = _user(1, "owner@example.com", "Owner")
    ensure_personal_workspace(db_path, owner)
    workspace = create_workspace(db_path, "Licensed Workspace", 1)
    workspace_id = int(workspace["id"])

    wrong_email_invite = create_invitation(db_path, workspace_id, "member@example.com", "member", 1)
    with pytest.raises(ValueError, match="does not match"):
        accept_invitation(db_path, wrong_email_invite["token"], _user(2, "other@example.com"))

    for user_id in (2, 3):
        member = _user(user_id, f"member{user_id}@example.com")
        invitation = create_invitation(db_path, workspace_id, member["email"], "member", 1)
        accept_invitation(db_path, invitation["token"], member)

    fourth = _user(4, "member4@example.com")
    full_invitation = create_invitation(db_path, workspace_id, fourth["email"], "member", 1)
    with pytest.raises(ValueError, match="no available"):
        accept_invitation(db_path, full_invitation["token"], fourth)


def test_usage_reservations_are_idempotent_and_released_on_failure(tmp_path) -> None:
    db_path = tmp_path / "usage.db"
    user = _user(1, "owner@example.com")
    workspace = ensure_personal_workspace(db_path, user)
    workspace_id = int(workspace["id"])

    first = reserve_minutes(db_path, workspace_id, 1, 120, usage_type="recorded_analysis", event_key="run-1")
    duplicate = reserve_minutes(db_path, workspace_id, 1, 120, usage_type="recorded_analysis", event_key="run-1")
    commit_minutes(db_path, "run-1", 95, meeting_id=42)
    reserve_minutes(db_path, workspace_id, 1, 200, usage_type="recorded_analysis", event_key="run-2")
    release_minutes(db_path, "run-2")

    summary = usage_summary(db_path, workspace_id)
    committed = fetchone(db_path, "SELECT * FROM usage_events WHERE event_key = 'run-1'")

    assert first["id"] == duplicate["id"]
    assert committed is not None and committed["meeting_id"] == 42
    assert summary["used_minutes"] == 95
    assert summary["remaining_minutes"] == 205

    with pytest.raises(OverflowError):
        reserve_minutes(db_path, workspace_id, 1, 206, usage_type="recorded_analysis", event_key="run-3")


def test_viewer_cannot_be_activated_past_seat_limit(tmp_path) -> None:
    db_path = tmp_path / "viewer.db"
    owner = _user(1, "owner@example.com")
    ensure_personal_workspace(db_path, owner)
    workspace = create_workspace(db_path, "Viewer Workspace", 1)
    workspace_id = int(workspace["id"])
    for user_id in (2, 3):
        member = _user(user_id, f"member{user_id}@example.com")
        invite = create_invitation(db_path, workspace_id, member["email"], "member", 1)
        accept_invitation(db_path, invite["token"], member)
    viewer = _user(4, "viewer@example.com")
    viewer_invite = create_invitation(db_path, workspace_id, viewer["email"], "viewer", 1)
    accept_invitation(db_path, viewer_invite["token"], viewer)

    with pytest.raises(ValueError, match="no available"):
        update_member(db_path, workspace_id, 4, role="member", license_status="active")

    assert get_workspace_for_user(db_path, workspace_id, 4)["membership_role"] == "viewer"


def test_subscription_change_request_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "billing.db"
    owner = _user(1, "owner@example.com")
    workspace = ensure_personal_workspace(db_path, owner)

    first = request_subscription_change(db_path, int(workspace["id"]), 1, "starter", "annual")
    duplicate = request_subscription_change(db_path, int(workspace["id"]), 1, "starter", "annual")

    assert first["id"] == duplicate["id"]
    assert first["current_plan_code"] == "personal"
    assert first["requested_plan_code"] == "starter"
    assert first["status"] == "pending"


def test_workspace_api_creates_personal_and_team_workspaces(tmp_path, monkeypatch) -> None:
    auth_db = tmp_path / "auth.db"
    meeting_db = tmp_path / "meetings.db"
    create_user(auth_db, "workspace-owner", "secret", display_name="Workspace Owner", email="owner@example.com")
    session = authenticate_user(auth_db, "workspace-owner", "secret")
    assert session is not None
    monkeypatch.setattr("boardsight_ai.service.AUTH_DB_PATH", auth_db)
    monkeypatch.setattr("boardsight_ai.service.MEETING_DB_PATH", meeting_db)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {session['token']}"}

    me_response = client.get("/api/v1/me", headers=headers)
    create_response = client.post("/api/v1/workspaces", headers=headers, json={"name": "Acme Board"})

    assert me_response.status_code == 200
    assert me_response.json()["workspace"]["plan_code"] == "personal"
    assert create_response.status_code == 200
    team = create_response.json()["workspace"]
    assert team["plan_code"] == "starter"
    assert team["subscription_status"] == "trialing"

    team_headers = {**headers, "X-BoardSight-Workspace-ID": str(team["id"])}
    members_response = client.get(f"/api/v1/workspaces/{team['id']}/members", headers=team_headers)
    plans_response = client.get("/api/v1/plans", headers=headers)
    change_response = client.post(
        f"/api/v1/workspaces/{team['id']}/subscription-change-requests",
        headers=team_headers,
        json={"plan_code": "growth", "billing_cycle": "monthly"},
    )
    assert members_response.status_code == 200
    assert members_response.json()["items"][0]["email"] == "owner@example.com"
    assert plans_response.status_code == 200
    assert plans_response.json()["currency"] == "INR"
    assert plans_response.json()["items"][1]["monthly_price_inr"] == 499
    assert change_response.status_code == 200
    assert change_response.json()["request"]["requested_plan_code"] == "growth"


def test_workspace_owner_connects_provider_with_masked_api_response(tmp_path, monkeypatch) -> None:
    auth_db = tmp_path / "auth.db"
    meeting_db = tmp_path / "meetings.db"
    monkeypatch.setenv("BOARDSIGHT_DATA_ENCRYPTION_KEY", "workspace-api-integration-test-key")
    create_user(auth_db, "integration-owner", "secret", display_name="Integration Owner", email="owner@example.com")
    session = authenticate_user(auth_db, "integration-owner", "secret")
    assert session is not None
    monkeypatch.setattr("boardsight_ai.service.AUTH_DB_PATH", auth_db)
    monkeypatch.setattr("boardsight_ai.service.MEETING_DB_PATH", meeting_db)
    monkeypatch.setattr(
        "boardsight_ai.service.validate_provider_connection",
        lambda provider, config, overrides: {
            "provider": provider,
            "status": "connected",
            "destination_name": "Launch Board",
        },
    )
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {session['token']}"}
    workspace = client.get("/api/v1/me", headers=headers).json()["workspace"]
    workspace_id = int(workspace["id"])

    connect_response = client.put(
        f"/api/v1/workspaces/{workspace_id}/integrations/notion",
        headers=headers,
        json={"target_id": "database-1", "access_token": "do-not-return"},
    )
    list_response = client.get(f"/api/v1/workspaces/{workspace_id}/integrations", headers=headers)
    raw = fetchone(meeting_db, "SELECT encrypted_config FROM organization_integrations WHERE organization_id = :organization_id", {"organization_id": workspace_id})

    assert connect_response.status_code == 200
    assert connect_response.json()["integration"]["has_access_token"] is True
    assert "access_token" not in connect_response.json()["integration"]
    assert "do-not-return" not in connect_response.text
    assert list_response.status_code == 200
    assert list_response.json()["can_manage"] is True
    assert list_response.json()["items"][0]["destination_name"] == "Launch Board"
    assert raw is not None and str(raw["encrypted_config"]).startswith("bsenc:v1:")
    assert "do-not-return" not in str(raw["encrypted_config"])


def test_registration_cannot_self_assign_global_admin(tmp_path, monkeypatch) -> None:
    auth_db = tmp_path / "auth.db"
    meeting_db = tmp_path / "meetings.db"
    monkeypatch.setattr("boardsight_ai.service.AUTH_DB_PATH", auth_db)
    monkeypatch.setattr("boardsight_ai.service.MEETING_DB_PATH", meeting_db)
    monkeypatch.setattr("boardsight_ai.service._email_provider_is_configured", lambda: False)
    client = TestClient(app)

    response = client.post("/api/v1/auth/register", json={
        "username": "not-admin",
        "email": "not-admin@example.com",
        "password": "secret",
        "confirm_password": "secret",
        "display_name": "Not Admin",
        "role": "admin",
    })

    assert response.status_code == 200
    from boardsight_ai.auth import get_user_by_username
    assert get_user_by_username(auth_db, "not-admin")["role"] == "analyst"
