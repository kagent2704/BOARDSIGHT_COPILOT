from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import text

from boardsight_ai.database import execute, fetchall, fetchone, get_engine, insert_and_return_id, is_postgres, table_columns


PLAN_ENTITLEMENTS: dict[str, dict[str, int]] = {
    "personal": {"licensed_members": 1, "monthly_minutes": 300, "retention_days": 30},
    "starter": {"licensed_members": 3, "monthly_minutes": 1200, "retention_days": 60},
    "growth": {"licensed_members": 10, "monthly_minutes": 4000, "retention_days": 180},
    "custom": {"licensed_members": 1000000, "monthly_minutes": 1000000000, "retention_days": 365},
}

PLAN_PRICING: dict[str, dict[str, Any]] = {
    "personal": {"name": "Personal", "monthly_price_inr": 199, "annual_price_inr": 1990, "additional_member_price_inr": None, "overage_price_inr": 0.50},
    "starter": {"name": "Starter Workspace", "monthly_price_inr": 499, "annual_price_inr": 4990, "additional_member_price_inr": 99, "overage_price_inr": 0.50},
    "growth": {"name": "Growth Workspace", "monthly_price_inr": 999, "annual_price_inr": 9990, "additional_member_price_inr": 99, "overage_price_inr": 0.50},
    "custom": {"name": "Custom", "monthly_price_inr": None, "annual_price_inr": None, "additional_member_price_inr": None, "overage_price_inr": None},
}

WORKSPACE_ROLES = {"owner", "admin", "member", "viewer"}
LICENSED_ROLES = {"owner", "admin", "member"}
PERMANENT_SPONSORED_EMAILS = {
    "kashmiraspatil@gmail.com",
    "umeshgirase19@gmail.com",
    "umeshgirase852@gmail.com",
    "kashmirasanjaypatil@gmail.com",
    "patilkashmirasanjay@gmail.com",
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _cycle_start() -> str:
    now = _utcnow()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def _slugify(value: str) -> str:
    slug = "".join(character.lower() if character.isalnum() else "-" for character in value.strip())
    slug = "-".join(part for part in slug.split("-") if part)
    return slug[:48] or "workspace"


def init_workspace_storage(database_path: Path) -> None:
    postgres = is_postgres(database_path)
    id_type = "BIGSERIAL PRIMARY KEY" if postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    user_id_type = "BIGINT" if postgres else "INTEGER"
    timestamp_type = "TIMESTAMP" if postgres else "TEXT"
    bool_type = "BOOLEAN" if postgres else "INTEGER"
    true_value = "TRUE" if postgres else "1"

    execute(
        database_path,
        f"""
        CREATE TABLE IF NOT EXISTS organizations (
            id {id_type},
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            created_by_user_id {user_id_type} NOT NULL,
            is_personal {bool_type} NOT NULL DEFAULT {true_value},
            status TEXT NOT NULL DEFAULT 'active',
            created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )
    execute(
        database_path,
        f"""
        CREATE TABLE IF NOT EXISTS organization_members (
            id {id_type},
            organization_id {user_id_type} NOT NULL,
            user_id {user_id_type} NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            license_status TEXT NOT NULL DEFAULT 'active',
            joined_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (organization_id, user_id)
        )
        """,
    )
    execute(
        database_path,
        f"""
        CREATE TABLE IF NOT EXISTS organization_invitations (
            id {id_type},
            organization_id {user_id_type} NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            token_hash TEXT NOT NULL UNIQUE,
            invited_by_user_id {user_id_type} NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            expires_at {timestamp_type} NOT NULL,
            accepted_by_user_id {user_id_type},
            accepted_at {timestamp_type},
            created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )
    execute(
        database_path,
        f"""
        CREATE TABLE IF NOT EXISTS plan_entitlements (
            plan_code TEXT PRIMARY KEY,
            licensed_members INTEGER NOT NULL,
            monthly_minutes INTEGER NOT NULL,
            retention_days INTEGER NOT NULL,
            updated_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )
    execute(
        database_path,
        f"""
        CREATE TABLE IF NOT EXISTS billing_sponsorships (
            id {id_type},
            email TEXT NOT NULL UNIQUE,
            user_id {user_id_type},
            sponsorship_type TEXT NOT NULL DEFAULT 'founder',
            status TEXT NOT NULL DEFAULT 'active',
            is_permanent {bool_type} NOT NULL DEFAULT {true_value},
            reason TEXT NOT NULL,
            created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
            updated_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )
    execute(
        database_path,
        f"""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id {id_type},
            organization_id {user_id_type} NOT NULL UNIQUE,
            plan_code TEXT NOT NULL DEFAULT 'personal',
            status TEXT NOT NULL DEFAULT 'active',
            licensed_member_limit INTEGER,
            monthly_minute_limit INTEGER,
            current_period_start {timestamp_type},
            current_period_end {timestamp_type},
            provider TEXT,
            provider_customer_id TEXT,
            provider_subscription_id TEXT,
            billing_mode TEXT NOT NULL DEFAULT 'customer',
            sponsorship_id {user_id_type},
            updated_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
            created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )
    execute(
        database_path,
        f"""
        CREATE TABLE IF NOT EXISTS subscription_change_requests (
            id {id_type},
            organization_id {user_id_type} NOT NULL,
            requested_by_user_id {user_id_type} NOT NULL,
            current_plan_code TEXT NOT NULL,
            requested_plan_code TEXT NOT NULL,
            billing_cycle TEXT NOT NULL DEFAULT 'monthly',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
            resolved_at {timestamp_type}
        )
        """,
    )
    execute(
        database_path,
        f"""
        CREATE TABLE IF NOT EXISTS organization_integrations (
            id {id_type},
            organization_id {user_id_type} NOT NULL,
            provider TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'inactive',
            encrypted_config TEXT,
            created_by_user_id {user_id_type} NOT NULL,
            updated_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
            created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (organization_id, provider)
        )
        """,
    )
    execute(
        database_path,
        f"""
        CREATE TABLE IF NOT EXISTS usage_events (
            id {id_type},
            event_key TEXT NOT NULL UNIQUE,
            organization_id {user_id_type} NOT NULL,
            user_id {user_id_type} NOT NULL,
            meeting_id {user_id_type},
            live_session_id {user_id_type},
            usage_type TEXT NOT NULL,
            quantity_minutes DOUBLE PRECISION NOT NULL DEFAULT 0,
            reserved_minutes DOUBLE PRECISION NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'reserved',
            metadata_json TEXT NOT NULL DEFAULT '{{}}',
            billing_disposition TEXT NOT NULL DEFAULT 'customer_billable',
            sponsorship_id {user_id_type},
            created_at {timestamp_type} DEFAULT CURRENT_TIMESTAMP,
            committed_at {timestamp_type}
        )
        """,
    )
    execute(database_path, "CREATE INDEX IF NOT EXISTS idx_org_members_user ON organization_members(user_id)")
    execute(database_path, "CREATE INDEX IF NOT EXISTS idx_usage_org_created ON usage_events(organization_id, created_at)")
    execute(database_path, "CREATE INDEX IF NOT EXISTS idx_subscription_requests_org ON subscription_change_requests(organization_id, created_at)")
    execute(database_path, "CREATE INDEX IF NOT EXISTS idx_billing_sponsorships_user ON billing_sponsorships(user_id)")

    subscription_columns = table_columns(database_path, "subscriptions")
    if "billing_mode" not in subscription_columns:
        execute(database_path, "ALTER TABLE subscriptions ADD COLUMN billing_mode TEXT NOT NULL DEFAULT 'customer'")
    if "sponsorship_id" not in subscription_columns:
        execute(database_path, f"ALTER TABLE subscriptions ADD COLUMN sponsorship_id {user_id_type}")
    usage_columns = table_columns(database_path, "usage_events")
    if "billing_disposition" not in usage_columns:
        execute(database_path, "ALTER TABLE usage_events ADD COLUMN billing_disposition TEXT NOT NULL DEFAULT 'customer_billable'")
    if "sponsorship_id" not in usage_columns:
        execute(database_path, f"ALTER TABLE usage_events ADD COLUMN sponsorship_id {user_id_type}")

    for sponsored_email in sorted(PERMANENT_SPONSORED_EMAILS):
        sponsorship = fetchone(database_path, "SELECT id FROM billing_sponsorships WHERE email = :email", {"email": sponsored_email})
        if sponsorship is None:
            execute(
                database_path,
                """
                INSERT INTO billing_sponsorships (email, sponsorship_type, status, is_permanent, reason)
                VALUES (:email, 'founder', 'active', :is_permanent, 'Permanent BoardSight operator access')
                """,
                {"email": sponsored_email, "is_permanent": True},
            )

    for plan_code, entitlements in PLAN_ENTITLEMENTS.items():
        existing = fetchone(database_path, "SELECT plan_code FROM plan_entitlements WHERE plan_code = :plan_code", {"plan_code": plan_code})
        params = {"plan_code": plan_code, **entitlements}
        if existing:
            execute(
                database_path,
                """
                UPDATE plan_entitlements
                SET licensed_members = :licensed_members,
                    monthly_minutes = :monthly_minutes,
                    retention_days = :retention_days,
                    updated_at = CURRENT_TIMESTAMP
                WHERE plan_code = :plan_code
                """,
                params,
            )
        else:
            execute(
                database_path,
                """
                INSERT INTO plan_entitlements (plan_code, licensed_members, monthly_minutes, retention_days)
                VALUES (:plan_code, :licensed_members, :monthly_minutes, :retention_days)
                """,
                params,
            )


def _unique_slug(database_path: Path, base: str) -> str:
    candidate = _slugify(base)
    suffix = 1
    while fetchone(database_path, "SELECT id FROM organizations WHERE slug = :slug", {"slug": candidate}):
        suffix += 1
        candidate = f"{_slugify(base)[:40]}-{suffix}"
    return candidate


def plan_catalog() -> list[dict[str, Any]]:
    return [
        {"plan_code": plan_code, **PLAN_PRICING[plan_code], **entitlements}
        for plan_code, entitlements in PLAN_ENTITLEMENTS.items()
    ]


def get_active_sponsorship_for_email(database_path: Path, email: str) -> dict[str, Any] | None:
    init_workspace_storage(database_path)
    normalized_email = str(email or "").strip().lower()
    if not normalized_email:
        return None
    return fetchone(
        database_path,
        "SELECT * FROM billing_sponsorships WHERE email = :email AND status = 'active'",
        {"email": normalized_email},
    )


def apply_sponsorship_for_user(database_path: Path, user: dict[str, Any], organization_id: int | None = None) -> dict[str, Any] | None:
    sponsorship = get_active_sponsorship_for_email(database_path, str(user.get("email") or ""))
    if sponsorship is None:
        return None
    user_id = int(user["user_id"])
    sponsorship_id = int(sponsorship["id"])
    linked_user_id = sponsorship.get("user_id")
    if linked_user_id is not None and int(linked_user_id) != user_id:
        raise PermissionError("This sponsored email is already linked to another BoardSight account.")
    execute(
        database_path,
        "UPDATE billing_sponsorships SET user_id = :user_id, updated_at = CURRENT_TIMESTAMP WHERE id = :sponsorship_id",
        {"user_id": user_id, "sponsorship_id": sponsorship_id},
    )
    if organization_id is not None:
        execute(
            database_path,
            """
            UPDATE subscriptions
            SET billing_mode = 'internal_sponsored', sponsorship_id = :sponsorship_id,
                status = 'active', provider = NULL, provider_customer_id = NULL,
                provider_subscription_id = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE organization_id = :organization_id
            """,
            {"sponsorship_id": sponsorship_id, "organization_id": organization_id},
        )
    return fetchone(database_path, "SELECT * FROM billing_sponsorships WHERE id = :id", {"id": sponsorship_id})


def ensure_personal_workspace(database_path: Path, user: dict[str, Any]) -> dict[str, Any]:
    init_workspace_storage(database_path)
    user_id = int(user["user_id"])
    existing = fetchone(
        database_path,
        """
        SELECT o.*, m.role AS membership_role, m.license_status
        FROM organization_members m
        JOIN organizations o ON o.id = m.organization_id
        WHERE m.user_id = :user_id
        ORDER BY o.is_personal DESC, o.id
        LIMIT 1
        """,
        {"user_id": user_id},
    )
    if existing is not None:
        apply_sponsorship_for_user(database_path, user, int(existing["id"]))
        return get_workspace_for_user(database_path, int(existing["id"]), user_id) or existing

    display_name = str(user.get("display_name") or user.get("username") or "BoardSight User").strip()
    organization_id = insert_and_return_id(
        database_path,
        """
        INSERT INTO organizations (name, slug, created_by_user_id, is_personal)
        VALUES (:name, :slug, :user_id, :is_personal)
        """,
        {
            "name": f"{display_name}'s Workspace",
            "slug": _unique_slug(database_path, str(user.get("username") or display_name)),
            "user_id": user_id,
            "is_personal": True,
        },
    )
    execute(
        database_path,
        """
        INSERT INTO organization_members (organization_id, user_id, role, license_status)
        VALUES (:organization_id, :user_id, 'owner', 'active')
        """,
        {"organization_id": organization_id, "user_id": user_id},
    )
    execute(
        database_path,
        """
        INSERT INTO subscriptions (organization_id, plan_code, status, current_period_start)
        VALUES (:organization_id, 'personal', 'active', :period_start)
        """,
        {"organization_id": organization_id, "period_start": _cycle_start()},
    )
    apply_sponsorship_for_user(database_path, user, organization_id)
    _backfill_user_content(database_path, user_id, organization_id)
    return get_workspace_for_user(database_path, organization_id, user_id) or {}


def _backfill_user_content(database_path: Path, user_id: int, organization_id: int) -> None:
    for table_name in ("meetings", "live_sessions"):
        try:
            execute(
                database_path,
                f"UPDATE {table_name} SET organization_id = :organization_id, created_by_user_id = COALESCE(created_by_user_id, user_id) WHERE user_id = :user_id AND organization_id IS NULL",
                {"organization_id": organization_id, "user_id": user_id},
            )
        except Exception:
            # Storage migrations may not have run yet during a first startup.
            continue


def list_workspaces_for_user(database_path: Path, user_id: int) -> list[dict[str, Any]]:
    init_workspace_storage(database_path)
    return fetchall(
        database_path,
        """
        SELECT o.*, m.role AS membership_role, m.license_status,
               s.plan_code, s.status AS subscription_status, s.billing_mode, s.sponsorship_id,
               bs.id AS user_sponsorship_id, bs.sponsorship_type AS user_sponsorship_type
        FROM organization_members m
        JOIN organizations o ON o.id = m.organization_id
        LEFT JOIN subscriptions s ON s.organization_id = o.id
        LEFT JOIN billing_sponsorships bs ON bs.user_id = m.user_id AND bs.status = 'active'
        WHERE m.user_id = :user_id AND o.status = 'active'
        ORDER BY o.is_personal DESC, o.name
        """,
        {"user_id": user_id},
    )


def get_workspace_for_user(database_path: Path, organization_id: int, user_id: int) -> dict[str, Any] | None:
    init_workspace_storage(database_path)
    return fetchone(
        database_path,
        """
        SELECT o.*, m.role AS membership_role, m.license_status,
               s.plan_code, s.status AS subscription_status,
               s.billing_mode, s.sponsorship_id,
               bs.id AS user_sponsorship_id, bs.sponsorship_type AS user_sponsorship_type,
               COALESCE(s.licensed_member_limit, p.licensed_members) AS licensed_member_limit,
               COALESCE(s.monthly_minute_limit, p.monthly_minutes) AS monthly_minute_limit,
               p.retention_days
        FROM organization_members m
        JOIN organizations o ON o.id = m.organization_id
        LEFT JOIN subscriptions s ON s.organization_id = o.id
        LEFT JOIN plan_entitlements p ON p.plan_code = s.plan_code
        LEFT JOIN billing_sponsorships bs ON bs.user_id = m.user_id AND bs.status = 'active'
        WHERE o.id = :organization_id AND m.user_id = :user_id AND o.status = 'active'
        """,
        {"organization_id": organization_id, "user_id": user_id},
    )


def create_workspace(database_path: Path, name: str, owner_user_id: int) -> dict[str, Any]:
    init_workspace_storage(database_path)
    resolved_name = name.strip()
    if len(resolved_name) < 2:
        raise ValueError("Workspace name must contain at least two characters.")
    organization_id = insert_and_return_id(
        database_path,
        "INSERT INTO organizations (name, slug, created_by_user_id, is_personal) VALUES (:name, :slug, :user_id, :is_personal)",
        {"name": resolved_name, "slug": _unique_slug(database_path, resolved_name), "user_id": owner_user_id, "is_personal": False},
    )
    execute(database_path, "INSERT INTO organization_members (organization_id, user_id, role, license_status) VALUES (:organization_id, :user_id, 'owner', 'active')", {"organization_id": organization_id, "user_id": owner_user_id})
    execute(database_path, "INSERT INTO subscriptions (organization_id, plan_code, status, current_period_start) VALUES (:organization_id, 'starter', 'trialing', :period_start)", {"organization_id": organization_id, "period_start": _cycle_start()})
    sponsorship = fetchone(database_path, "SELECT id FROM billing_sponsorships WHERE user_id = :user_id AND status = 'active'", {"user_id": owner_user_id})
    if sponsorship is not None:
        execute(
            database_path,
            "UPDATE subscriptions SET billing_mode = 'internal_sponsored', sponsorship_id = :sponsorship_id, status = 'active' WHERE organization_id = :organization_id",
            {"sponsorship_id": sponsorship["id"], "organization_id": organization_id},
        )
    return get_workspace_for_user(database_path, organization_id, owner_user_id) or {}


def list_workspace_members(database_path: Path, organization_id: int) -> list[dict[str, Any]]:
    init_workspace_storage(database_path)
    return fetchall(database_path, "SELECT id, organization_id, user_id, role, license_status, joined_at FROM organization_members WHERE organization_id = :organization_id ORDER BY id", {"organization_id": organization_id})


def create_invitation(database_path: Path, organization_id: int, email: str, role: str, invited_by_user_id: int) -> dict[str, Any]:
    init_workspace_storage(database_path)
    normalized_role = role.strip().lower()
    if normalized_role not in WORKSPACE_ROLES - {"owner"}:
        raise ValueError("Invitation role must be admin, member, or viewer.")
    normalized_email = email.strip().lower()
    if "@" not in normalized_email:
        raise ValueError("A valid email address is required.")
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = _timestamp(_utcnow() + timedelta(days=7))
    invitation_id = insert_and_return_id(
        database_path,
        """
        INSERT INTO organization_invitations (organization_id, email, role, token_hash, invited_by_user_id, expires_at)
        VALUES (:organization_id, :email, :role, :token_hash, :invited_by_user_id, :expires_at)
        """,
        {"organization_id": organization_id, "email": normalized_email, "role": normalized_role, "token_hash": token_hash, "invited_by_user_id": invited_by_user_id, "expires_at": expires_at},
    )
    return {"invitation_id": invitation_id, "email": normalized_email, "role": normalized_role, "token": raw_token, "expires_at": expires_at}


def accept_invitation(database_path: Path, token: str, user: dict[str, Any]) -> dict[str, Any]:
    init_workspace_storage(database_path)
    token_hash = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()
    invitation = fetchone(database_path, "SELECT * FROM organization_invitations WHERE token_hash = :token_hash AND status = 'pending'", {"token_hash": token_hash})
    if invitation is None:
        raise ValueError("Invitation is invalid or has already been used.")
    if str(invitation.get("expires_at") or "") < _timestamp(_utcnow()):
        execute(database_path, "UPDATE organization_invitations SET status = 'expired' WHERE id = :id", {"id": invitation["id"]})
        raise ValueError("Invitation has expired.")
    if str(user.get("email") or "").strip().lower() != str(invitation["email"]).strip().lower():
        raise ValueError("Invitation email does not match the signed-in account.")
    user_id = int(user["user_id"])
    if invitation["role"] != "viewer":
        summary = usage_summary(database_path, int(invitation["organization_id"]))
        if int(summary["active_licenses"]) >= int(summary["licensed_member_limit"]):
            raise ValueError("Workspace has no available licensed member seats.")
    existing = fetchone(database_path, "SELECT id FROM organization_members WHERE organization_id = :organization_id AND user_id = :user_id", {"organization_id": invitation["organization_id"], "user_id": user_id})
    if existing is None:
        execute(database_path, "INSERT INTO organization_members (organization_id, user_id, role, license_status) VALUES (:organization_id, :user_id, :role, :license_status)", {"organization_id": invitation["organization_id"], "user_id": user_id, "role": invitation["role"], "license_status": "inactive" if invitation["role"] == "viewer" else "active"})
    execute(database_path, "UPDATE organization_invitations SET status = 'accepted', accepted_by_user_id = :user_id, accepted_at = CURRENT_TIMESTAMP WHERE id = :id", {"user_id": user_id, "id": invitation["id"]})
    return get_workspace_for_user(database_path, int(invitation["organization_id"]), user_id) or {}


def update_member(database_path: Path, organization_id: int, member_user_id: int, *, role: str | None = None, license_status: str | None = None) -> dict[str, Any]:
    membership = fetchone(database_path, "SELECT * FROM organization_members WHERE organization_id = :organization_id AND user_id = :user_id", {"organization_id": organization_id, "user_id": member_user_id})
    if membership is None:
        raise ValueError("Workspace member was not found.")
    new_role = (role or str(membership["role"])).strip().lower()
    new_license = (license_status or str(membership["license_status"])).strip().lower()
    if new_role not in WORKSPACE_ROLES or new_license not in {"active", "inactive"}:
        raise ValueError("Invalid workspace role or license status.")
    if membership["role"] == "owner" and new_role != "owner":
        raise ValueError("Workspace ownership must be transferred before changing the owner role.")
    activating = new_role in LICENSED_ROLES and new_license == "active" and not (
        str(membership["role"]) in LICENSED_ROLES and str(membership["license_status"]) == "active"
    )
    if activating:
        summary = usage_summary(database_path, organization_id)
        if int(summary["active_licenses"]) >= int(summary["licensed_member_limit"]):
            raise ValueError("Workspace has no available licensed member seats.")
    execute(database_path, "UPDATE organization_members SET role = :role, license_status = :license_status WHERE id = :id", {"role": new_role, "license_status": new_license, "id": membership["id"]})
    return fetchone(database_path, "SELECT * FROM organization_members WHERE id = :id", {"id": membership["id"]}) or {}


def assert_workspace_access(workspace: dict[str, Any], *, require_admin: bool = False, require_license: bool = False) -> None:
    role = str(workspace.get("membership_role") or "").lower()
    if require_admin and role not in {"owner", "admin"}:
        raise PermissionError("Workspace owner or admin access is required.")
    if require_license and (role not in LICENSED_ROLES or str(workspace.get("license_status") or "").lower() != "active"):
        raise PermissionError("An active workspace license is required.")
    is_sponsored = bool(workspace.get("user_sponsorship_id")) or str(workspace.get("billing_mode") or "").lower() == "internal_sponsored"
    if require_license and not is_sponsored and str(workspace.get("subscription_status") or "").lower() not in {"active", "trialing"}:
        raise PermissionError("The workspace subscription is not active.")


def usage_summary(database_path: Path, organization_id: int) -> dict[str, Any]:
    workspace_subscription = fetchone(
        database_path,
        """
        SELECT s.plan_code, s.status, s.billing_mode, s.sponsorship_id,
               COALESCE(s.monthly_minute_limit, p.monthly_minutes) AS monthly_minute_limit,
               COALESCE(s.licensed_member_limit, p.licensed_members) AS licensed_member_limit
        FROM subscriptions s JOIN plan_entitlements p ON p.plan_code = s.plan_code
        WHERE s.organization_id = :organization_id
        """,
        {"organization_id": organization_id},
    ) or {"plan_code": "personal", "status": "inactive", "billing_mode": "customer", "sponsorship_id": None, "monthly_minute_limit": 0, "licensed_member_limit": 0}
    usage = fetchone(database_path, "SELECT COALESCE(SUM(CASE WHEN status = 'committed' THEN quantity_minutes ELSE reserved_minutes END), 0) AS used_minutes FROM usage_events WHERE organization_id = :organization_id AND status IN ('reserved','committed') AND created_at >= :cycle_start", {"organization_id": organization_id, "cycle_start": _cycle_start()}) or {"used_minutes": 0}
    licenses = fetchone(database_path, "SELECT COUNT(*) AS count FROM organization_members WHERE organization_id = :organization_id AND license_status = 'active' AND role IN ('owner','admin','member')", {"organization_id": organization_id}) or {"count": 0}
    limit = float(workspace_subscription.get("monthly_minute_limit") or 0)
    used = float(usage.get("used_minutes") or 0)
    return {
        **workspace_subscription,
        "is_sponsored": str(workspace_subscription.get("billing_mode") or "") == "internal_sponsored",
        "used_minutes": round(used, 2),
        "remaining_minutes": round(max(0.0, limit - used), 2),
        "active_licenses": int(licenses.get("count") or 0),
    }


def reserve_minutes(database_path: Path, organization_id: int, user_id: int, minutes: float, *, usage_type: str, event_key: str | None = None, metadata_json: str = "{}") -> dict[str, Any]:
    requested = max(0.01, float(minutes))
    key = event_key or f"usage-{secrets.token_hex(16)}"
    engine = get_engine(database_path)
    with engine.begin() as connection:
        if engine.dialect.name.startswith("postgres"):
            connection.execute(text("SELECT id FROM organizations WHERE id = :organization_id FOR UPDATE"), {"organization_id": organization_id})
        existing = connection.execute(text("SELECT * FROM usage_events WHERE event_key = :event_key"), {"event_key": key}).mappings().first()
        if existing is not None:
            return dict(existing)
        entitlement = connection.execute(text("""
            SELECT s.status, COALESCE(s.monthly_minute_limit, p.monthly_minutes) AS monthly_minute_limit,
                   bs.id AS sponsorship_id
            FROM subscriptions s JOIN plan_entitlements p ON p.plan_code = s.plan_code
            LEFT JOIN billing_sponsorships bs ON bs.user_id = :user_id AND bs.status = 'active'
            WHERE s.organization_id = :organization_id
        """), {"organization_id": organization_id, "user_id": user_id}).mappings().first()
        sponsorship_id = int(entitlement["sponsorship_id"]) if entitlement is not None and entitlement.get("sponsorship_id") is not None else None
        if entitlement is None or (sponsorship_id is None and str(entitlement["status"]) not in {"active", "trialing"}):
            raise PermissionError("The workspace subscription is not active.")
        used = connection.execute(text("SELECT COALESCE(SUM(CASE WHEN status = 'committed' THEN quantity_minutes ELSE reserved_minutes END), 0) AS used FROM usage_events WHERE organization_id = :organization_id AND status IN ('reserved','committed') AND created_at >= :cycle_start"), {"organization_id": organization_id, "cycle_start": _cycle_start()}).mappings().first()
        remaining = float(entitlement["monthly_minute_limit"] or 0) - float((used or {}).get("used") or 0)
        if sponsorship_id is None and requested > remaining:
            raise OverflowError(f"Workspace has {max(0.0, remaining):.1f} processing minutes remaining.")
        statement = """
            INSERT INTO usage_events (
                event_key, organization_id, user_id, usage_type, reserved_minutes, status, metadata_json,
                billing_disposition, sponsorship_id
            )
            VALUES (
                :event_key, :organization_id, :user_id, :usage_type, :reserved_minutes, 'reserved', :metadata_json,
                :billing_disposition, :sponsorship_id
            )
        """
        if engine.dialect.name.startswith("postgres"):
            statement += " RETURNING id"
        result = connection.execute(text(statement), {
            "event_key": key,
            "organization_id": organization_id,
            "user_id": user_id,
            "usage_type": usage_type,
            "reserved_minutes": requested,
            "metadata_json": metadata_json,
            "billing_disposition": "internally_sponsored" if sponsorship_id is not None else "customer_billable",
            "sponsorship_id": sponsorship_id,
        })
        usage_id = int(result.scalar_one() if engine.dialect.name.startswith("postgres") else result.lastrowid)
    return fetchone(database_path, "SELECT * FROM usage_events WHERE id = :id", {"id": usage_id}) or {}


def commit_minutes(database_path: Path, event_key: str, actual_minutes: float, *, meeting_id: int | None = None, live_session_id: int | None = None) -> None:
    execute(database_path, """
        UPDATE usage_events
        SET quantity_minutes = :actual_minutes, status = 'committed', meeting_id = :meeting_id,
            live_session_id = :live_session_id, committed_at = CURRENT_TIMESTAMP
        WHERE event_key = :event_key AND status = 'reserved'
    """, {"actual_minutes": max(0.0, float(actual_minutes)), "meeting_id": meeting_id, "live_session_id": live_session_id, "event_key": event_key})


def release_minutes(database_path: Path, event_key: str) -> None:
    execute(database_path, "UPDATE usage_events SET status = 'released', reserved_minutes = 0 WHERE event_key = :event_key AND status = 'reserved'", {"event_key": event_key})


def request_subscription_change(database_path: Path, organization_id: int, user_id: int, requested_plan_code: str, billing_cycle: str = "monthly") -> dict[str, Any]:
    init_workspace_storage(database_path)
    if requested_plan_code not in PLAN_ENTITLEMENTS:
        raise ValueError("Invalid requested plan.")
    if billing_cycle not in {"monthly", "annual"}:
        raise ValueError("Billing cycle must be monthly or annual.")
    subscription = fetchone(database_path, "SELECT plan_code FROM subscriptions WHERE organization_id = :organization_id", {"organization_id": organization_id})
    if subscription is None:
        raise ValueError("Workspace subscription was not found.")
    existing = fetchone(
        database_path,
        """
        SELECT * FROM subscription_change_requests
        WHERE organization_id = :organization_id AND requested_plan_code = :requested_plan_code
          AND billing_cycle = :billing_cycle AND status = 'pending'
        ORDER BY id DESC LIMIT 1
        """,
        {"organization_id": organization_id, "requested_plan_code": requested_plan_code, "billing_cycle": billing_cycle},
    )
    if existing is not None:
        return existing
    request_id = insert_and_return_id(
        database_path,
        """
        INSERT INTO subscription_change_requests (
            organization_id, requested_by_user_id, current_plan_code, requested_plan_code, billing_cycle
        ) VALUES (
            :organization_id, :requested_by_user_id, :current_plan_code, :requested_plan_code, :billing_cycle
        )
        """,
        {
            "organization_id": organization_id,
            "requested_by_user_id": user_id,
            "current_plan_code": subscription["plan_code"],
            "requested_plan_code": requested_plan_code,
            "billing_cycle": billing_cycle,
        },
    )
    return fetchone(database_path, "SELECT * FROM subscription_change_requests WHERE id = :id", {"id": request_id}) or {}


def set_subscription(database_path: Path, organization_id: int, plan_code: str, status: str = "active") -> dict[str, Any]:
    if plan_code not in PLAN_ENTITLEMENTS or status not in {"active", "trialing", "past_due", "canceled"}:
        raise ValueError("Invalid plan or subscription status.")
    execute(database_path, "UPDATE subscriptions SET plan_code = :plan_code, status = :status, updated_at = CURRENT_TIMESTAMP WHERE organization_id = :organization_id", {"plan_code": plan_code, "status": status, "organization_id": organization_id})
    return fetchone(database_path, "SELECT * FROM subscriptions WHERE organization_id = :organization_id", {"organization_id": organization_id}) or {}
