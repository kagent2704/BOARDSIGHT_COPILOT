from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import tempfile
import threading
from datetime import datetime
from urllib.parse import unquote
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = CURRENT_DIR.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

try:
    from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.background import BackgroundTask
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
    import uvicorn
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "FastAPI service dependencies are missing. Install python-ai/requirements-core.txt first."
    ) from exc

from boardsight_ai.pipeline import run_pipeline, write_result
from boardsight_ai.live_session import answer_live_copilot, build_live_session_payload
from boardsight_ai.providers.media import clip_video_fast, probe_video
from boardsight_ai.auth import (
    authenticate_credentials,
    authenticate_user,
    cleanup_expired_sessions,
    cleanup_expired_verification_tokens,
    create_user,
    get_session_user,
    get_user_by_email,
    get_user_by_identifier,
    get_user_by_username,
    init_auth_storage,
    issue_email_verification_token,
    revoke_session,
    session_ttl_seconds,
    upsert_admin_user,
    verify_email_token,
)
from boardsight_ai.agent_storage import (
    create_agent_execution_run,
    get_agent_execution_run,
    init_agent_storage,
    protect_agent_storage,
    update_agent_execution_run,
)
from boardsight_ai.config import _load_local_env, default_config
from boardsight_ai.data_protection import data_encryption_enabled, data_encryption_key_fingerprint
from boardsight_ai.emailer import send_verification_email
from boardsight_ai.gitlab_execution import build_gitlab_execution_plan, normalize_gitlab_plan_source, sync_plan_to_gitlab
from boardsight_ai.gitlab_storage import init_gitlab_storage, protect_gitlab_storage, save_gitlab_sync
from boardsight_ai.providers.speech import _faster_whisper_model
from boardsight_ai.providers.vision import analyze_sparse_frame
from boardsight_ai.retention import cleanup_expired_data
from boardsight_ai.storage import (
    append_live_session_event,
    append_live_visual_event,
    create_live_session,
    execute,
    finalize_live_session,
    fetchone,
    get_live_session,
    get_live_session_events,
    get_live_session_visual_events,
    get_meeting_result,
    init_storage,
    list_live_sessions,
    list_meeting_results,
    protect_sensitive_storage,
    save_live_copilot_reply,
    save_meeting_result,
    update_meeting_workflow_editor,
)
from boardsight_ai.reporting import write_structured_reports
from boardsight_ai.models import pipeline_result_from_dict
from boardsight_ai.demo_mode import create_demo_session, ensure_demo_workspace
from boardsight_ai.workspaces import (
    accept_invitation,
    assert_workspace_access,
    commit_minutes,
    create_invitation,
    create_workspace,
    ensure_personal_workspace,
    get_workspace_for_user,
    init_workspace_storage,
    list_workspace_members,
    list_workspaces_for_user,
    release_minutes,
    reserve_minutes,
    set_subscription,
    update_member,
    usage_summary,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "output" / "appdata"
AUTH_DB_PATH = DATA_DIR / "boardsight_auth.db"
MEETING_DB_PATH = DATA_DIR / "boardsight_meetings.db"
_load_local_env(PROJECT_ROOT)
init_auth_storage(AUTH_DB_PATH)
init_storage(MEETING_DB_PATH)
init_workspace_storage(MEETING_DB_PATH)
init_agent_storage(MEETING_DB_PATH)
init_gitlab_storage(MEETING_DB_PATH)

app = FastAPI(title="BoardSight AI Service", version="0.1.0")
WARM_MODELS_ON_STARTUP = os.getenv("BOARDSIGHT_WARM_MODELS", "0").strip().lower() in {"1", "true", "yes", "on"}
WARMUP_STATE: dict[str, object] = {
    "enabled": WARM_MODELS_ON_STARTUP,
    "completed": False,
    "in_progress": False,
    "steps": [],
}


def _cors_origins() -> list[str]:
    configured = [
        origin.strip().rstrip("/")
        for origin in os.getenv("BOARDSIGHT_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    defaults = [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://boardsight.in",
        "https://www.boardsight.in",
        "https://boardsight-copilot.vercel.app",
    ]
    public_app_url = os.getenv("BOARDSIGHT_PUBLIC_APP_URL", "").strip().rstrip("/")
    if public_app_url:
        defaults.append(public_app_url)
    return sorted({origin for origin in [*defaults, *configured] if origin})


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _bootstrap_admin_from_env() -> None:
    username = os.getenv("BOARDSIGHT_BOOTSTRAP_ADMIN_USERNAME", "").strip()
    password = os.getenv("BOARDSIGHT_BOOTSTRAP_ADMIN_PASSWORD", "").strip()
    if not username or not password:
        return
    email = os.getenv("BOARDSIGHT_BOOTSTRAP_ADMIN_EMAIL", f"{username}@boardsight.local").strip().lower()
    display_name = os.getenv("BOARDSIGHT_BOOTSTRAP_ADMIN_DISPLAY_NAME", "BoardSight Admin").strip() or "BoardSight Admin"
    upsert_admin_user(
        AUTH_DB_PATH,
        username=username,
        password=password,
        email=email,
        display_name=display_name,
    )


def _assign_orphaned_runs_to_bootstrap_admin() -> None:
    if not _env_bool("BOARDSIGHT_ASSIGN_ORPHANED_RUNS_TO_BOOTSTRAP_ADMIN", "false"):
        return
    username = os.getenv("BOARDSIGHT_BOOTSTRAP_ADMIN_USERNAME", "").strip()
    if not username:
        return
    admin_row = fetchone(
        AUTH_DB_PATH,
        "SELECT id, username FROM users WHERE LOWER(username) = LOWER(:username)",
        {"username": username},
    )
    if admin_row is None:
        return
    execute(
        MEETING_DB_PATH,
        """
        UPDATE meetings
        SET user_id = :user_id, username = COALESCE(username, :username)
        WHERE user_id IS NULL
        """,
        {"user_id": int(admin_row["id"]), "username": str(admin_row["username"])},
    )


def _migrate_legacy_admin_runs_to_bootstrap_admin() -> None:
    if not _env_bool("BOARDSIGHT_MIGRATE_LEGACY_ADMIN_RUNS", "false"):
        return
    bootstrap_username = os.getenv("BOARDSIGHT_BOOTSTRAP_ADMIN_USERNAME", "").strip()
    legacy_username = os.getenv("BOARDSIGHT_LEGACY_ADMIN_USERNAME", "admin").strip()
    if not bootstrap_username or not legacy_username:
        return
    bootstrap_row = fetchone(
        AUTH_DB_PATH,
        "SELECT id, username FROM users WHERE LOWER(username) = LOWER(:username)",
        {"username": bootstrap_username},
    )
    if bootstrap_row is None:
        return
    execute(
        MEETING_DB_PATH,
        """
        UPDATE meetings
        SET user_id = :user_id,
            username = :username
        WHERE LOWER(COALESCE(username, '')) = LOWER(:legacy_username)
        """,
        {
            "user_id": int(bootstrap_row["id"]),
            "username": str(bootstrap_row["username"]),
            "legacy_username": legacy_username,
        },
    )
    execute(
        MEETING_DB_PATH,
        """
        UPDATE live_sessions
        SET user_id = :user_id,
            username = :username
        WHERE LOWER(COALESCE(username, '')) = LOWER(:legacy_username)
        """,
        {
            "user_id": int(bootstrap_row["id"]),
            "username": str(bootstrap_row["username"]),
            "legacy_username": legacy_username,
        },
    )


def _retention_days(name: str, default_days: int) -> int:
    return max(1, int(os.getenv(name, str(default_days))))


def _verification_base_url(request: Request | None = None) -> str:
    configured = os.getenv("BOARDSIGHT_PUBLIC_APP_URL", "").strip().rstrip("/")
    if configured:
        return configured
    if request is not None:
        return str(request.base_url).rstrip("/")
    return "http://localhost:8000"


def _verification_return_url(request: Request | None = None) -> str:
    base_url = _verification_base_url(request)
    return f"{base_url}/"


def _email_provider_is_configured() -> bool:
    return bool(os.getenv("BOARDSIGHT_EMAIL_FROM", "").strip()) and bool(
        (os.getenv("BOARDSIGHT_RESEND_API_KEY") or os.getenv("RESEND_API_KEY") or "").strip()
    )


def _send_verification_email_safe(*, to_email: str, display_name: str, verification_url: str) -> None:
    try:
        send_verification_email(
            to_email=to_email,
            display_name=display_name,
            verification_url=verification_url,
        )
    except Exception:
        pass


def _queue_verification_email(*, to_email: str, display_name: str, verification_url: str) -> None:
    threading.Thread(
        target=_send_verification_email_safe,
        kwargs={
            "to_email": to_email,
            "display_name": display_name,
            "verification_url": verification_url,
        },
        daemon=True,
        name="boardsight-verification-email",
    ).start()


def _render_verification_result_page(*, status: str, email: str, app_url: str, detail: str) -> HTMLResponse:
    title = "Email Verified" if status == "verified" else "Verification Issue"
    eyebrow = "BoardSight Account Ready" if status == "verified" else "Verification Needs Attention"
    headline = (
        "Your account is verified and ready to use."
        if status == "verified"
        else "This verification link is invalid or has expired."
    )
    tone_class = "verified" if status == "verified" else "error"
    body_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | BoardSight</title>
  <meta http-equiv="refresh" content="4;url={app_url}">
  <style>
    :root {{
      color-scheme: dark;
      --bg: #080f19;
      --surface: rgba(17, 24, 39, 0.92);
      --border: rgba(145, 163, 255, 0.12);
      --text: #f8fafc;
      --muted: #94a3b8;
      --primary: #6366f1;
      --accent: #22d3ee;
      --success: #22c55e;
      --danger: #f97316;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: Inter, "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(99,102,241,0.18), transparent 28%),
        radial-gradient(circle at bottom right, rgba(34,211,238,0.12), transparent 24%),
        var(--bg);
      display: grid;
      place-items: center;
      padding: 24px;
    }}
    .card {{
      width: min(760px, 100%);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 28px;
      padding: 32px;
      box-shadow: 0 28px 80px rgba(0,0,0,0.32);
      display: grid;
      gap: 18px;
    }}
    .eyebrow {{
      display: inline-flex;
      width: fit-content;
      padding: 8px 12px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      background: rgba(99,102,241,0.14);
      color: #c7d2fe;
    }}
    .status-dot {{
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: {"var(--success)" if status == "verified" else "var(--danger)"};
      box-shadow: 0 0 0 8px {"rgba(34,197,94,0.12)" if status == "verified" else "rgba(249,115,22,0.12)"};
    }}
    .status-row {{
      display: flex;
      align-items: center;
      gap: 14px;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(34px, 4vw, 54px);
      line-height: 1.02;
      letter-spacing: -0.04em;
    }}
    p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
      font-size: 16px;
    }}
    .detail {{
      padding: 18px;
      border-radius: 18px;
      background: rgba(12, 20, 34, 0.68);
      border: 1px solid var(--border);
      display: grid;
      gap: 8px;
    }}
    .email {{
      color: var(--text);
      font-weight: 700;
    }}
    .actions {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 8px;
    }}
    .primary, .secondary {{
      min-height: 48px;
      padding: 12px 18px;
      border-radius: 14px;
      text-decoration: none;
      font-weight: 700;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }}
    .primary {{
      background: linear-gradient(135deg, var(--primary), #8b5cf6);
      color: white;
    }}
    .secondary {{
      border: 1px solid var(--border);
      color: var(--text);
      background: transparent;
    }}
  </style>
</head>
<body>
  <main class="card">
    <span class="eyebrow">{eyebrow}</span>
    <div class="status-row">
      <span class="status-dot"></span>
      <div>
        <h1>{headline}</h1>
      </div>
    </div>
    <p>{detail}</p>
    <div class="detail">
      <strong class="email">{email or "BoardSight user"}</strong>
      <p>You can return to BoardSight now. This page will automatically send you back in a few seconds.</p>
    </div>
    <div class="actions">
      <a class="primary" href="{app_url}">Open BoardSight</a>
      <a class="secondary" href="{app_url}?auth=signin">Go to Sign In</a>
    </div>
  </main>
</body>
</html>"""
    return HTMLResponse(content=body_html)


def _run_retention_maintenance() -> dict[str, object]:
    meeting_cleanup = cleanup_expired_data(
        MEETING_DB_PATH,
        output_root=PROJECT_ROOT / "output",
        meeting_retention_days=_retention_days("BOARDSIGHT_MEETING_RETENTION_DAYS", 30),
        live_session_retention_days=_retention_days("BOARDSIGHT_LIVE_SESSION_RETENTION_DAYS", 14),
        report_retention_days=_retention_days("BOARDSIGHT_REPORT_RETENTION_DAYS", 90),
    )
    auth_session_cleanup = cleanup_expired_sessions(AUTH_DB_PATH)
    verification_cleanup = cleanup_expired_verification_tokens(AUTH_DB_PATH)
    return {
        **meeting_cleanup,
        "deleted_auth_sessions": auth_session_cleanup,
        "deleted_verification_tokens": verification_cleanup,
    }


def _run_data_protection_maintenance() -> dict[str, object]:
    if not data_encryption_enabled():
        return {
            "enabled": False,
            "meeting_storage_updated_rows": 0,
            "gitlab_storage_updated_rows": 0,
            "agent_storage_updated_rows": 0,
            "key_fingerprint": "",
        }
    meeting_protection = protect_sensitive_storage(MEETING_DB_PATH)
    gitlab_protection = protect_gitlab_storage(MEETING_DB_PATH)
    agent_protection = protect_agent_storage(MEETING_DB_PATH)
    return {
        "enabled": True,
        "meeting_storage_updated_rows": int(meeting_protection.get("updated_rows", 0)),
        "gitlab_storage_updated_rows": int(gitlab_protection.get("updated_rows", 0)),
        "agent_storage_updated_rows": int(agent_protection.get("updated_rows", 0)),
        "key_fingerprint": data_encryption_key_fingerprint(),
    }


_bootstrap_admin_from_env()
_assign_orphaned_runs_to_bootstrap_admin()
_migrate_legacy_admin_runs_to_bootstrap_admin()
_run_data_protection_maintenance()
_run_retention_maintenance()


def _warm_model_caches() -> None:
    WARMUP_STATE["in_progress"] = True
    config = default_config()
    steps: list[dict[str, str]] = []

    def record_step(name: str, loaded: bool) -> None:
        steps.append({"name": name, "status": "loaded" if loaded else "unavailable"})

    whisper_model = _faster_whisper_model(config.faster_whisper_model)
    record_step(f"faster-whisper:{config.faster_whisper_model}", whisper_model is not None)
    record_step("pipeline:boardsight-production-lightweight-v1", True)

    WARMUP_STATE["completed"] = True
    WARMUP_STATE["in_progress"] = False
    WARMUP_STATE["steps"] = steps


@app.on_event("startup")
def warm_models_on_startup() -> None:
    _run_retention_maintenance()
    if not WARM_MODELS_ON_STARTUP:
        return

    def _run_background_warmup() -> None:
        try:
            _warm_model_caches()
        except Exception as exc:
            WARMUP_STATE["completed"] = False
            WARMUP_STATE["in_progress"] = False
            WARMUP_STATE["error"] = str(exc)

    threading.Thread(target=_run_background_warmup, name="boardsight-model-warmup", daemon=True).start()


@app.get("/health")
def health() -> dict[str, str]:
    payload = {"status": "ok"}
    if WARM_MODELS_ON_STARTUP:
        if WARMUP_STATE.get("completed"):
            payload["model_warmup"] = "complete"
        elif WARMUP_STATE.get("in_progress"):
            payload["model_warmup"] = "warming"
        else:
            payload["model_warmup"] = "pending"
    return payload


async def _collect_request_payload(request: Request, payload: dict | None = None) -> dict:
    request_payload = dict(payload or {})
    if request_payload:
        return request_payload

    try:
        parsed_json = await request.json()
        if isinstance(parsed_json, dict):
            request_payload.update(parsed_json)
    except Exception:
        pass

    if not request_payload:
        try:
            raw_body = await request.body()
            if raw_body:
                parsed_raw = json.loads(raw_body.decode("utf-8"))
                if isinstance(parsed_raw, dict):
                    request_payload.update(parsed_raw)
        except Exception:
            pass

    if not request_payload:
        try:
            form = await request.form()
            request_payload.update({str(key): str(value) for key, value in form.items()})
        except Exception:
            pass

    if request.query_params:
        for key, value in request.query_params.items():
            request_payload.setdefault(str(key), str(value))

    return request_payload


@app.post("/api/v1/auth/login")
async def login(request: Request, payload: dict | None = None) -> dict:
    request_payload = await _collect_request_payload(request, payload)
    identifier = str(request_payload.get("identifier", "") or request_payload.get("username", "") or request_payload.get("email", ""))
    password = str(request_payload.get("password", ""))
    session = authenticate_user(AUTH_DB_PATH, identifier, password)
    if session is None:
        user, reason = authenticate_credentials(AUTH_DB_PATH, identifier, password)
        if reason == "email_not_verified" and user is not None:
            raise HTTPException(status_code=403, detail="Email verification is required before signing in.")
        raise HTTPException(status_code=401, detail="Invalid username, email, or password.")
    return session


@app.post("/api/v1/demo/session")
def demo_session() -> dict:
    try:
        return create_demo_session(AUTH_DB_PATH, MEETING_DB_PATH)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to prepare the demo workspace right now.") from exc


@app.post("/api/v1/demo/reset")
def reset_demo_session() -> dict:
    try:
        manifest = ensure_demo_workspace(AUTH_DB_PATH, MEETING_DB_PATH, reset=True)
        return {"status": "reset", "demo": manifest}
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to reset the demo workspace right now.") from exc


@app.post("/api/v1/auth/register")
async def register(request: Request, background_tasks: BackgroundTasks, payload: dict | None = None) -> dict:
    request_payload = await _collect_request_payload(request, payload)
    username = str(request_payload.get("username", "")).strip()
    email = str(request_payload.get("email", "")).strip().lower()
    password = str(request_payload.get("password", "")).strip()
    confirm_password = str(request_payload.get("confirm_password", "")).strip()
    requested_role = str(request_payload.get("role", "analyst")).strip().lower().replace(" ", "_") or "analyst"
    role = requested_role if requested_role in {"analyst", "executive_observer", "board_member"} else "analyst"
    display_name = str(request_payload.get("display_name", username)).strip() or username
    if not username or not email or not password or not confirm_password:
        raise HTTPException(status_code=400, detail="Username, email, password, and confirmation are required.")
    if confirm_password != password:
        raise HTTPException(status_code=400, detail="Password confirmation does not match.")
    created = create_user(
        AUTH_DB_PATH,
        username,
        password,
        role,
        display_name=display_name,
        email=email,
        email_verified=False,
    )
    if not created:
        raise HTTPException(status_code=409, detail="An account with that username or email already exists.")
    user = get_user_by_username(AUTH_DB_PATH, username)
    if user is None:
        raise HTTPException(status_code=500, detail="Unable to create account verification state.")
    raw_token = issue_email_verification_token(AUTH_DB_PATH, int(user["user_id"]), email)
    verification_url = f"{_verification_base_url(request)}/api/v1/auth/verify-email?token={raw_token}"
    if _email_provider_is_configured():
        _queue_verification_email(
            to_email=email,
            display_name=display_name,
            verification_url=verification_url,
        )
    return {
        "status": "verification_pending",
        "username": username,
        "email": email,
        "display_name": display_name,
        "role": role,
        "verification_sent": _email_provider_is_configured(),
        "email_delivery": {
            "sent": _email_provider_is_configured(),
            "queued": _email_provider_is_configured(),
            "reason": "" if _email_provider_is_configured() else "email_provider_not_configured",
        },
    }


@app.get("/api/v1/auth/verify-email")
def verify_email(token: str, request: Request):
    accept_header = str(request.headers.get("accept") or "")
    wants_json = "application/json" in accept_header and "text/html" not in accept_header
    app_url = _verification_return_url(request)
    verified = verify_email_token(AUTH_DB_PATH, token)
    if verified is None:
        if wants_json:
            raise HTTPException(status_code=400, detail="Verification token is invalid or has expired.")
        return _render_verification_result_page(
            status="error",
            email="",
            app_url=app_url,
            detail="The verification link is invalid or has expired. Request a new verification email from the sign-in screen.",
        )
    if wants_json:
        return {
            "status": "verified",
            "email": verified["email"],
        }
    return _render_verification_result_page(
        status="verified",
        email=str(verified["email"]),
        app_url=app_url,
        detail="Your email has been verified successfully. You can sign in to BoardSight and access your workspace now.",
    )


@app.post("/api/v1/auth/resend-verification")
async def resend_verification(request: Request, background_tasks: BackgroundTasks, payload: dict | None = None) -> dict:
    request_payload = await _collect_request_payload(request, payload)
    identifier = str(request_payload.get("identifier", "") or request_payload.get("username", "") or request_payload.get("email", "")).strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="Username or email is required.")
    user = get_user_by_identifier(AUTH_DB_PATH, identifier)
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    if bool(user.get("email_verified")):
        return {"status": "already_verified", "email": user["email"]}
    raw_token = issue_email_verification_token(AUTH_DB_PATH, int(user["id"]), str(user["email"]))
    verification_url = f"{_verification_base_url(request)}/api/v1/auth/verify-email?token={raw_token}"
    if _email_provider_is_configured():
        _queue_verification_email(
            to_email=str(user["email"]),
            display_name=str(user.get("display_name") or user.get("username") or "there"),
            verification_url=verification_url,
        )
    return {
        "status": "verification_resent",
        "email": user["email"],
        "verification_sent": _email_provider_is_configured(),
        "email_delivery": {
            "sent": _email_provider_is_configured(),
            "queued": _email_provider_is_configured(),
            "reason": "" if _email_provider_is_configured() else "email_provider_not_configured",
        },
    }


@app.post("/api/v1/auth/logout")
def logout(request: Request) -> dict:
    auth_header = request.headers.get("authorization", "")
    token = auth_header.removeprefix("Bearer ").strip() if auth_header else ""
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token.")
    revoke_session(AUTH_DB_PATH, token)
    return {"status": "logged_out"}


def _require_session_user(request: Request) -> dict:
    auth_header = request.headers.get("authorization", "")
    token = auth_header.removeprefix("Bearer ").strip() if auth_header else ""
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token.")
    user = get_session_user(AUTH_DB_PATH, token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session token.")
    return user


def _require_admin_user(request: Request) -> dict:
    user = _require_session_user(request)
    if str(user.get("role") or "").strip().lower() != "admin":
        raise HTTPException(status_code=403, detail="Admin access is required.")
    return user


def _workspace_context(
    request: Request,
    user: dict,
    *,
    require_admin: bool = False,
    require_license: bool = False,
) -> dict:
    personal = ensure_personal_workspace(MEETING_DB_PATH, user)
    requested_id = str(request.headers.get("x-boardsight-workspace-id") or request.query_params.get("workspace_id") or "").strip()
    workspace = personal
    if requested_id:
        try:
            workspace = get_workspace_for_user(MEETING_DB_PATH, int(requested_id), int(user["user_id"]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid workspace identifier.") from exc
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace was not found for this account.")
    try:
        assert_workspace_access(workspace, require_admin=require_admin, require_license=require_license)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return workspace


def _workspace_payload(workspace: dict) -> dict:
    organization_id = int(workspace["id"])
    return {
        "id": organization_id,
        "name": workspace.get("name"),
        "slug": workspace.get("slug"),
        "is_personal": bool(workspace.get("is_personal")),
        "role": workspace.get("membership_role"),
        "license_status": workspace.get("license_status"),
        "plan_code": workspace.get("plan_code"),
        "subscription_status": workspace.get("subscription_status"),
        "usage": usage_summary(MEETING_DB_PATH, organization_id),
    }


def _user_with_workspace(request: Request, user: dict, *, require_license: bool = False) -> dict:
    workspace = _workspace_context(request, user, require_license=require_license)
    return {**user, "_workspace_id": int(workspace["id"]), "_workspace": workspace}


def _summarize_meeting_row(row: dict) -> dict:
    meeting_id = int(row["id"])
    run_name = str(row.get("run_name") or f"meeting-{meeting_id}")
    sentiment = str(row.get("overall_sentiment") or "analysis ready").strip()
    return {
        "id": str(meeting_id),
        "meetingId": meeting_id,
        "title": run_name.replace("-", " ").replace("_", " ").strip().title() or f"Meeting {meeting_id}",
        "conclusion": f"Sentiment: {sentiment.capitalize()} | Attention {float(row.get('overall_attention') or 0):.1f}% | Impact {float(row.get('impact_score') or 0):.1f}",
        "decisions": int(row.get("decision_count") or 0),
        "createdAt": str(row.get("created_at") or datetime.utcnow().isoformat()),
        "speakerCount": int(row.get("speaker_count") or 0),
        "visualArtifactCount": int(row.get("visual_artifact_count") or 0),
        "overallAttention": float(row.get("overall_attention") or 0),
        "overallSentiment": row.get("overall_sentiment"),
        "impactScore": float(row.get("impact_score") or 0),
        "productivityScore": float(row.get("productivity_score") or 0),
        "executionReadiness": float(row.get("execution_readiness") or 0),
        "runtimeProfile": row.get("runtime_profile"),
        "dataContractVersion": row.get("data_contract_version"),
    }


def _resolve_owned_meeting_record(meeting_id: int, user: dict) -> dict:
    workspace_id = user.get("_workspace_id")
    record = get_meeting_result(
        MEETING_DB_PATH,
        meeting_id,
        user_id=int(user["user_id"]) if workspace_id is None else None,
        organization_id=int(workspace_id) if workspace_id is not None else None,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Stored analysis not found.")
    return record


def _sanitize_workflow_editor_payload(payload: dict) -> dict:
    workflow_editor = dict(payload.get("workflow_editor") or payload.get("workflowEditor") or payload)
    nodes = workflow_editor.get("nodes") or []
    links = workflow_editor.get("links") or []
    meta = workflow_editor.get("meta") or {}
    title = str(workflow_editor.get("title") or "BoardSight Workflow").strip() or "BoardSight Workflow"
    meeting_id = str(workflow_editor.get("meetingId") or payload.get("meeting_id") or "").strip()

    sanitized_nodes: list[dict[str, object]] = []
    for index, raw_node in enumerate(nodes):
        if not isinstance(raw_node, dict):
            continue
        node_id = str(raw_node.get("id") or f"node-{index + 1}").strip() or f"node-{index + 1}"
        node_type = str(raw_node.get("type") or "review").strip().lower() or "review"
        sanitized_nodes.append(
            {
                "id": node_id,
                "type": node_type,
                "title": str(raw_node.get("title") or "").strip(),
                "owner": str(raw_node.get("owner") or "").strip(),
                "status": str(raw_node.get("status") or "").strip(),
                "summary": str(raw_node.get("summary") or "").strip(),
                "description": str(raw_node.get("description") or raw_node.get("detailedDescription") or "").strip(),
                "notes": str(raw_node.get("notes") or "").strip(),
                "handoffNotes": str(raw_node.get("handoffNotes") or "").strip(),
                "acceptanceCriteria": str(raw_node.get("acceptanceCriteria") or "").strip(),
                "decisionId": str(raw_node.get("decisionId") or "").strip(),
                "traceId": str(raw_node.get("traceId") or "").strip(),
                "sourceStage": str(raw_node.get("sourceStage") or raw_node.get("stage") or "").strip(),
                "dueDate": str(raw_node.get("dueDate") or "").strip(),
                "priority": str(raw_node.get("priority") or "Medium").strip() or "Medium",
            }
        )

    if not sanitized_nodes:
        raise HTTPException(status_code=400, detail="Workflow must include at least one node.")

    valid_node_ids = {str(node["id"]) for node in sanitized_nodes}
    sanitized_links: list[dict[str, str]] = []
    for raw_link in links:
        if not isinstance(raw_link, dict):
            continue
        from_id = str(raw_link.get("from") or "").strip()
        to_id = str(raw_link.get("to") or "").strip()
        if not from_id or not to_id or from_id not in valid_node_ids or to_id not in valid_node_ids:
            continue
        sanitized_links.append(
            {
                "from": from_id,
                "to": to_id,
                "label": str(raw_link.get("label") or "next").strip() or "next",
            }
        )

    sanitized_meta = {
        "derivedFrom": str(meta.get("derivedFrom") or "BoardSight workflow editor").strip() or "BoardSight workflow editor",
        "status": str(meta.get("status") or "saved").strip() or "saved",
        "overview": str(meta.get("overview") or "").strip(),
        "notes": str(meta.get("notes") or "").strip(),
        "savedAt": str(meta.get("savedAt") or datetime.utcnow().isoformat()).strip(),
    }

    return {
        "meetingId": meeting_id,
        "title": title,
        "nodes": sanitized_nodes,
        "links": sanitized_links,
        "meta": sanitized_meta,
    }


@app.get("/api/v1/me")
def me(request: Request) -> dict:
    user = _require_session_user(request)
    workspace = _workspace_context(request, user)
    return {**user, "workspace": _workspace_payload(workspace)}


@app.get("/api/v1/workspaces")
def workspaces(request: Request) -> dict:
    user = _require_session_user(request)
    ensure_personal_workspace(MEETING_DB_PATH, user)
    items = list_workspaces_for_user(MEETING_DB_PATH, int(user["user_id"]))
    return {"items": [_workspace_payload(item) for item in items]}


@app.post("/api/v1/workspaces")
async def create_workspace_endpoint(request: Request, payload: dict | None = None) -> dict:
    user = _require_session_user(request)
    request_payload = await _collect_request_payload(request, payload)
    try:
        workspace = create_workspace(MEETING_DB_PATH, str(request_payload.get("name") or ""), int(user["user_id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"workspace": _workspace_payload(workspace)}


@app.get("/api/v1/workspaces/{organization_id}")
def workspace_detail(organization_id: int, request: Request) -> dict:
    user = _require_session_user(request)
    workspace = get_workspace_for_user(MEETING_DB_PATH, organization_id, int(user["user_id"]))
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace was not found for this account.")
    return {"workspace": _workspace_payload(workspace)}


@app.get("/api/v1/workspaces/{organization_id}/members")
def workspace_members(organization_id: int, request: Request) -> dict:
    user = _require_session_user(request)
    workspace = get_workspace_for_user(MEETING_DB_PATH, organization_id, int(user["user_id"]))
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace was not found for this account.")
    members = list_workspace_members(MEETING_DB_PATH, organization_id)
    for member in members:
        identity = fetchone(AUTH_DB_PATH, "SELECT username, email, display_name FROM users WHERE id = :user_id", {"user_id": member["user_id"]})
        if identity:
            member.update(identity)
    return {"items": members}


@app.post("/api/v1/workspaces/{organization_id}/invitations")
async def invite_workspace_member(organization_id: int, request: Request, payload: dict | None = None) -> dict:
    user = _require_session_user(request)
    workspace = get_workspace_for_user(MEETING_DB_PATH, organization_id, int(user["user_id"]))
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace was not found for this account.")
    try:
        assert_workspace_access(workspace, require_admin=True)
        request_payload = await _collect_request_payload(request, payload)
        invitation = create_invitation(MEETING_DB_PATH, organization_id, str(request_payload.get("email") or ""), str(request_payload.get("role") or "member"), int(user["user_id"]))
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400 if isinstance(exc, ValueError) else 403, detail=str(exc)) from exc
    # Until transactional email templates are added, the token is returned to the owner
    # so initial customer onboarding can be completed manually.
    return {"status": "invited", "invitation": invitation}


@app.post("/api/v1/workspaces/invitations/{token}/accept")
def accept_workspace_invitation(token: str, request: Request) -> dict:
    user = _require_session_user(request)
    try:
        workspace = accept_invitation(MEETING_DB_PATH, token, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "accepted", "workspace": _workspace_payload(workspace)}


@app.patch("/api/v1/workspaces/{organization_id}/members/{member_user_id}")
async def update_workspace_member(organization_id: int, member_user_id: int, request: Request, payload: dict | None = None) -> dict:
    user = _require_session_user(request)
    workspace = get_workspace_for_user(MEETING_DB_PATH, organization_id, int(user["user_id"]))
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace was not found for this account.")
    try:
        assert_workspace_access(workspace, require_admin=True)
        request_payload = await _collect_request_payload(request, payload)
        member = update_member(MEETING_DB_PATH, organization_id, member_user_id, role=request_payload.get("role"), license_status=request_payload.get("license_status"))
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400 if isinstance(exc, ValueError) else 403, detail=str(exc)) from exc
    return {"status": "updated", "member": member}


@app.get("/api/v1/workspaces/{organization_id}/usage")
def workspace_usage(organization_id: int, request: Request) -> dict:
    user = _require_session_user(request)
    workspace = get_workspace_for_user(MEETING_DB_PATH, organization_id, int(user["user_id"]))
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace was not found for this account.")
    return {"usage": usage_summary(MEETING_DB_PATH, organization_id)}


@app.put("/api/v1/admin/workspaces/{organization_id}/subscription")
async def administer_workspace_subscription(organization_id: int, request: Request, payload: dict | None = None) -> dict:
    _require_admin_user(request)
    request_payload = await _collect_request_payload(request, payload)
    try:
        subscription = set_subscription(MEETING_DB_PATH, organization_id, str(request_payload.get("plan_code") or ""), str(request_payload.get("status") or "active"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "updated", "subscription": subscription}


@app.get("/api/v1/privacy/settings")
def privacy_settings() -> dict:
    return {
        "meeting_retention_days": _retention_days("BOARDSIGHT_MEETING_RETENTION_DAYS", 30),
        "live_session_retention_days": _retention_days("BOARDSIGHT_LIVE_SESSION_RETENTION_DAYS", 14),
        "report_retention_days": _retention_days("BOARDSIGHT_REPORT_RETENTION_DAYS", 90),
        "session_ttl_seconds": session_ttl_seconds(),
        "email_verification_required": True,
        "email_provider_configured": bool(os.getenv("BOARDSIGHT_RESEND_API_KEY") or os.getenv("RESEND_API_KEY")),
        "data_encryption_enabled": data_encryption_enabled(),
        "data_encryption_key_fingerprint": data_encryption_key_fingerprint(),
        "operator_blindness_mode": "application-layer-encryption",
    }


@app.post("/api/v1/admin/maintenance/cleanup")
def run_retention_cleanup(request: Request) -> dict:
    _require_admin_user(request)
    return {
        "status": "completed",
        "cleanup": _run_retention_maintenance(),
        "protection": _run_data_protection_maintenance(),
    }


@app.get("/api/v1/meetings")
def meetings(request: Request) -> dict:
    user = _user_with_workspace(request, _require_session_user(request))
    rows = list_meeting_results(MEETING_DB_PATH, organization_id=int(user["_workspace_id"]))
    return {"items": [_summarize_meeting_row(row) for row in rows]}


@app.get("/api/v1/meetings/{meeting_id}")
def meeting_detail(meeting_id: int, request: Request) -> dict:
    user = _user_with_workspace(request, _require_session_user(request))
    record = _resolve_owned_meeting_record(meeting_id, user)
    payload = json.loads(str(record.get("result_json") or "{}"))
    payload["storage"] = {
        "meeting_id": int(record["id"]),
        "output_dir": str(record.get("output_dir") or ""),
        "result_file": str(record.get("result_file") or ""),
        "created_at": str(record.get("created_at") or ""),
        "username": str(record.get("username") or ""),
    }
    return payload


@app.put("/api/v1/meetings/{meeting_id}/workflow")
async def update_meeting_workflow(meeting_id: int, request: Request, payload: dict | None = None) -> dict:
    user = _user_with_workspace(request, _require_session_user(request), require_license=True)
    request_payload = await _collect_request_payload(request, payload)
    workflow_editor = _sanitize_workflow_editor_payload(request_payload)
    workflow_editor["meetingId"] = str(meeting_id)
    updated_record = update_meeting_workflow_editor(
        MEETING_DB_PATH,
        meeting_id,
        workflow_editor,
        organization_id=int(user["_workspace_id"]),
    )
    if updated_record is None:
        raise HTTPException(status_code=404, detail="Stored analysis not found.")
    updated_payload = json.loads(str(updated_record.get("result_json") or "{}"))
    updated_payload["storage"] = {
        "meeting_id": int(updated_record["id"]),
        "output_dir": str(updated_record.get("output_dir") or ""),
        "result_file": str(updated_record.get("result_file") or ""),
        "created_at": str(updated_record.get("created_at") or ""),
        "username": str(updated_record.get("username") or ""),
    }
    return {
        "status": "saved",
        "workflow_editor": workflow_editor,
        "meeting": updated_payload,
    }


@app.post("/api/v1/meetings/{meeting_id}/gitlab/preview")
async def meeting_gitlab_preview(meeting_id: int, request: Request, payload: dict | None = None) -> dict:
    user = _user_with_workspace(request, _require_session_user(request), require_license=True)
    request_payload = await _collect_request_payload(request, payload)
    return _create_meeting_gitlab_preview(meeting_id, user, request_payload)


@app.post("/api/v1/meetings/{meeting_id}/gitlab/sync")
async def meeting_gitlab_sync(meeting_id: int, request: Request, payload: dict | None = None) -> dict:
    user = _user_with_workspace(request, _require_session_user(request), require_license=True)
    request_payload = await _collect_request_payload(request, payload)
    return _sync_meeting_gitlab_preview(meeting_id, user, request_payload)


@app.get("/api/v1/meetings/{meeting_id}/reports/{file_name}")
def meeting_report(meeting_id: int, file_name: str, request: Request):
    user = _user_with_workspace(request, _require_session_user(request))
    record = _resolve_owned_meeting_record(meeting_id, user)
    output_dir = Path(str(record.get("output_dir") or "")).resolve()
    if output_dir.exists():
        candidate = (output_dir / file_name).resolve()
        if not str(candidate).startswith(str(output_dir)):
            raise HTTPException(status_code=400, detail="Invalid report path.")
        if candidate.exists():
            return FileResponse(candidate, filename=candidate.name)
    regenerated = _regenerate_meeting_report_from_record(record, file_name)
    if regenerated is None:
        raise HTTPException(status_code=404, detail="Requested report file was not found.")
    return FileResponse(
        regenerated,
        filename=Path(file_name).name,
        background=BackgroundTask(_cleanup_temp_report_artifact, regenerated.parent),
    )


def _cleanup_temp_report_artifact(path: Path) -> None:
    try:
        if path.exists():
            for child in path.iterdir():
                child.unlink(missing_ok=True)
            path.rmdir()
    except Exception:
        pass


def _regenerate_meeting_report_from_record(record: dict, file_name: str) -> Path | None:
    allowed_reports = {
        "structured_report.pdf",
        "structured_report.docx",
        "structured_report.xlsx",
        "transcript.csv",
        "summary_card.png",
    }
    safe_name = Path(file_name).name
    if safe_name not in allowed_reports:
        return None
    payload = json.loads(str(record.get("result_json") or "{}"))
    result = pipeline_result_from_dict(payload)
    temp_dir = Path(tempfile.mkdtemp(prefix=f"boardsight-report-{int(record['id'])}-"))
    report_files = write_structured_reports(result, temp_dir)
    key_lookup = {
        "structured_report.pdf": "pdf",
        "structured_report.docx": "docx",
        "structured_report.xlsx": "xlsx",
        "transcript.csv": "excel_ready_csv",
        "summary_card.png": "image",
    }
    report_key = key_lookup[safe_name]
    resolved = report_files.get(report_key)
    if not resolved:
        return None
    candidate = Path(str(resolved)).resolve()
    if not candidate.exists():
        return None
    return candidate


def _resolve_owned_live_session(session_id: int, user: dict) -> dict:
    workspace_id = user.get("_workspace_id")
    record = get_live_session(
        MEETING_DB_PATH,
        session_id,
        user_id=int(user["user_id"]) if workspace_id is None else None,
        organization_id=int(workspace_id) if workspace_id is not None else None,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Live session not found.")
    return record


def _meeting_title_from_payload(source_kind: str, source_id: str, payload: dict[str, Any]) -> str:
    session = payload.get("session") or {}
    title = str(session.get("title") or "").strip()
    if title:
        return title
    metadata = payload.get("metadata") or {}
    for candidate in (
        metadata.get("run_name"),
        metadata.get("title"),
        payload.get("title"),
    ):
        resolved = str(candidate or "").strip()
        if resolved:
            return resolved
    return f"{source_kind.replace('-', ' ').title()} {source_id}"


def _build_assignee_map(raw_value: Any) -> dict[str, int]:
    if raw_value is None or raw_value == "":
        return {}
    payload = raw_value
    if isinstance(raw_value, str):
        payload = json.loads(raw_value)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="assignee_map must be a JSON object.")
    normalized: dict[str, int] = {}
    for key, value in payload.items():
        name = str(key).strip().lower()
        if not name:
            continue
        normalized[name] = int(value)
    return normalized


def _gitlab_connection_overrides(request_payload: dict[str, Any]) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for request_key, output_key in (
        ("base_url", "base_url"),
        ("project_id", "project_id"),
        ("private_token", "private_token"),
    ):
        value = str(request_payload.get(request_key) or "").strip()
        if value:
            overrides[output_key] = value
    return overrides


def _create_gitlab_preview_for_payload(
    *,
    source_kind: str,
    source_id: str,
    source_payload: dict[str, Any],
    user: dict[str, Any],
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    workspace = _workspace_context(user, require_license=True)
    config = default_config()
    meeting_title = _meeting_title_from_payload(source_kind, source_id, source_payload)
    plan = build_gitlab_execution_plan(
        normalize_gitlab_plan_source(source_payload),
        source_kind=source_kind,
        source_id=source_id,
        meeting_title=meeting_title,
        assignee_map=_build_assignee_map(request_payload.get("assignee_map")),
    )
    execution_run = create_agent_execution_run(
        MEETING_DB_PATH,
        source_kind=source_kind,
        source_id=source_id,
        meeting_title=plan["meeting_title"],
        created_by_user_id=int(user["user_id"]),
        plan=plan,
    )
    connection_overrides = _gitlab_connection_overrides(request_payload)
    save_gitlab_sync(
        MEETING_DB_PATH,
        organization_id=int(workspace["id"]),
        source_kind=source_kind,
        source_id=source_id,
        project_ref=str(connection_overrides.get("project_id") or config.gitlab_project_id or ""),
        dry_run=True,
        plan=plan,
        sync_result=None,
    )
    return {
        "approval_id": execution_run.get("approval_id"),
        "status": "previewed",
        "meeting_title": plan["meeting_title"],
        "plan": plan,
        "connection": {
            "base_url": connection_overrides.get("base_url") or config.gitlab_base_url or "",
            "project_id": connection_overrides.get("project_id") or config.gitlab_project_id or "",
            "has_private_token": bool(connection_overrides.get("private_token") or config.gitlab_private_token),
        },
    }


def _create_gitlab_preview(
    session_id: int,
    user: dict[str, Any],
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    session_row = _resolve_owned_live_session(session_id, user)
    event_rows = get_live_session_events(MEETING_DB_PATH, session_id)
    visual_rows = get_live_session_visual_events(MEETING_DB_PATH, session_id)
    config = default_config()
    live_payload = build_live_session_payload(session_row, event_rows, config, visual_rows=visual_rows)
    return _create_gitlab_preview_for_payload(
        source_kind="live-session",
        source_id=str(session_id),
        source_payload=live_payload,
        user=user,
        request_payload=request_payload,
    )


def _create_meeting_gitlab_preview(
    meeting_id: int,
    user: dict[str, Any],
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    record = _resolve_owned_meeting_record(meeting_id, user)
    meeting_payload = json.loads(str(record.get("result_json") or "{}"))
    meeting_payload["storage"] = {
        "meeting_id": int(record["id"]),
        "output_dir": str(record.get("output_dir") or ""),
        "result_file": str(record.get("result_file") or ""),
        "created_at": str(record.get("created_at") or ""),
        "username": str(record.get("username") or ""),
    }
    meeting_payload.setdefault("metadata", {})
    if isinstance(meeting_payload["metadata"], dict):
        meeting_payload["metadata"].setdefault("run_name", str(record.get("run_name") or ""))
    return _create_gitlab_preview_for_payload(
        source_kind="meeting",
        source_id=str(meeting_id),
        source_payload=meeting_payload,
        user=user,
        request_payload=request_payload,
    )


def _sync_gitlab_preview(
    *,
    source_kind: str,
    source_id: str,
    user: dict[str, Any],
    request_payload: dict[str, Any],
    preview_builder,
) -> dict[str, Any]:
    workspace = _workspace_context(user, require_license=True)
    approval_id = str(request_payload.get("approval_id") or "").strip()
    execution_run = get_agent_execution_run(MEETING_DB_PATH, approval_id) if approval_id else None
    if execution_run is None:
        preview_payload = preview_builder()
        approval_id = str(preview_payload.get("approval_id") or "")
        execution_run = get_agent_execution_run(MEETING_DB_PATH, approval_id)
    if execution_run is None:
        raise HTTPException(status_code=500, detail="Unable to create a GitLab assignment preview.")

    config = default_config()
    connection_overrides = _gitlab_connection_overrides(request_payload)
    plan = dict(execution_run.get("plan_json") or {})
    sync_result = sync_plan_to_gitlab(plan, config, connection_overrides=connection_overrides)
    update_agent_execution_run(
        MEETING_DB_PATH,
        approval_id,
        status=str(sync_result.get("status") or "synced"),
        approved_by_user_id=int(user["user_id"]),
        connection={
            "base_url": connection_overrides.get("base_url") or config.gitlab_base_url or "",
            "project_id": connection_overrides.get("project_id") or config.gitlab_project_id or "",
            "has_private_token": bool(connection_overrides.get("private_token") or config.gitlab_private_token),
        },
        sync_result=sync_result,
    )
    save_gitlab_sync(
        MEETING_DB_PATH,
        organization_id=int(workspace["id"]),
        source_kind=source_kind,
        source_id=source_id,
        project_ref=str(connection_overrides.get("project_id") or config.gitlab_project_id or ""),
        dry_run=sync_result.get("status") != "synced",
        plan=plan,
        sync_result=sync_result,
    )
    return {
        "approval_id": approval_id,
        "status": str(sync_result.get("status") or "unknown"),
        "meeting_title": str(execution_run.get("meeting_title") or ""),
        "plan": plan,
        "sync_result": sync_result,
    }


def _sync_live_gitlab_preview(
    session_id: int,
    user: dict[str, Any],
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    return _sync_gitlab_preview(
        source_kind="live-session",
        source_id=str(session_id),
        user=user,
        request_payload=request_payload,
        preview_builder=lambda: _create_gitlab_preview(session_id, user, request_payload),
    )


def _sync_meeting_gitlab_preview(
    meeting_id: int,
    user: dict[str, Any],
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    return _sync_gitlab_preview(
        source_kind="meeting",
        source_id=str(meeting_id),
        user=user,
        request_payload=request_payload,
        preview_builder=lambda: _create_meeting_gitlab_preview(meeting_id, user, request_payload),
    )


def _decode_base64_frame(image_base64: str):
    cv2 = __import__("cv2")
    numpy = __import__("numpy")
    normalized = str(image_base64 or "").strip()
    if "," in normalized:
        normalized = normalized.split(",", 1)[1]
    raw_bytes = base64.b64decode(normalized)
    array = numpy.frombuffer(raw_bytes, dtype=numpy.uint8)
    frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Unable to decode image frame.")
    return frame


@app.get("/api/v1/live/active")
def live_active(request: Request) -> dict:
    user = _user_with_workspace(request, _require_session_user(request))
    sessions = list_live_sessions(MEETING_DB_PATH, organization_id=int(user["_workspace_id"]), status="active")
    if not sessions:
        return {"session": None}
    config = default_config()
    session_row = sessions[0]
    event_rows = get_live_session_events(MEETING_DB_PATH, int(session_row["id"]))
    visual_rows = get_live_session_visual_events(MEETING_DB_PATH, int(session_row["id"]))
    return build_live_session_payload(session_row, event_rows, config, visual_rows=visual_rows)


@app.post("/api/v1/live/start")
async def start_live_session(request: Request, payload: dict | None = None) -> dict:
    user = _user_with_workspace(request, _require_session_user(request), require_license=True)
    request_payload = await _collect_request_payload(request, payload)
    title = str(request_payload.get("title", "")).strip() or f"Live Session {datetime.utcnow().strftime('%H:%M')}"
    session_id = create_live_session(
        MEETING_DB_PATH,
        title,
        user_id=int(user["user_id"]),
        username=str(user["username"]),
        organization_id=int(user["_workspace_id"]),
    )
    expected_minutes = max(1.0, float(request_payload.get("expected_minutes") or 60.0))
    try:
        reserve_minutes(
            MEETING_DB_PATH,
            int(user["_workspace_id"]),
            int(user["user_id"]),
            expected_minutes,
            usage_type="live_session",
            event_key=f"live:{session_id}",
        )
    except (PermissionError, OverflowError) as exc:
        execute(MEETING_DB_PATH, "DELETE FROM live_sessions WHERE id = :session_id", {"session_id": session_id})
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    session_row = _resolve_owned_live_session(session_id, user)
    return {
        "session": {
            "id": session_id,
            "title": title,
            "status": session_row.get("status", "active"),
            "started_at": session_row.get("started_at", ""),
        }
    }


@app.get("/api/v1/live/{session_id}")
def live_session_detail(session_id: int, request: Request) -> dict:
    user = _user_with_workspace(request, _require_session_user(request))
    session_row = _resolve_owned_live_session(session_id, user)
    event_rows = get_live_session_events(MEETING_DB_PATH, session_id)
    visual_rows = get_live_session_visual_events(MEETING_DB_PATH, session_id)
    config = default_config()
    return build_live_session_payload(session_row, event_rows, config, visual_rows=visual_rows)


@app.post("/api/v1/live/{session_id}/events")
async def append_live_event(session_id: int, request: Request, payload: dict | None = None) -> dict:
    user = _user_with_workspace(request, _require_session_user(request), require_license=True)
    _resolve_owned_live_session(session_id, user)
    request_payload = await _collect_request_payload(request, payload)
    text = str(request_payload.get("text", "")).strip()
    speaker = str(request_payload.get("speaker", "")).strip() or str(user.get("display_name") or user.get("username") or "Participant")
    start_seconds = _parse_optional_float(request_payload.get("start_seconds"))
    end_seconds = _parse_optional_float(request_payload.get("end_seconds"))
    if not text:
        raise HTTPException(status_code=400, detail="Live transcript text is required.")
    try:
        event_id = append_live_session_event(
            MEETING_DB_PATH,
            session_id,
            text,
            speaker=speaker,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session_row = _resolve_owned_live_session(session_id, user)
    event_rows = get_live_session_events(MEETING_DB_PATH, session_id)
    visual_rows = get_live_session_visual_events(MEETING_DB_PATH, session_id)
    config = default_config()
    payload = build_live_session_payload(session_row, event_rows, config, visual_rows=visual_rows)
    payload["event_id"] = event_id
    return payload


@app.post("/api/v1/live/{session_id}/visual")
async def append_live_visual(session_id: int, request: Request, payload: dict | None = None) -> dict:
    user = _user_with_workspace(request, _require_session_user(request), require_license=True)
    session_row = _resolve_owned_live_session(session_id, user)
    request_payload = await _collect_request_payload(request, payload)
    image_base64 = str(request_payload.get("image_base64", "")).strip()
    timestamp_seconds = _parse_optional_float(request_payload.get("timestamp_seconds"))
    if not image_base64:
        raise HTTPException(status_code=400, detail="image_base64 is required.")
    try:
        frame = _decode_base64_frame(image_base64)
        config = default_config()
        analysis = analyze_sparse_frame(frame, config)
        visual_event_id = append_live_visual_event(
            MEETING_DB_PATH,
            session_id,
            timestamp_seconds=float(timestamp_seconds or 0.0),
            artifact_type=str(analysis.get("artifact_type") or ""),
            display_mode=str(analysis.get("display_mode") or ""),
            visible_people_count=int(analysis.get("visible_people_count") or 0),
            screen_present=bool(analysis.get("screen_present")),
            chart_present=bool(analysis.get("chart_present")),
            document_present=bool(analysis.get("document_present")),
            textual_content=str(analysis.get("textual_content") or ""),
            summary=str(analysis.get("summary") or ""),
            confidence=float(analysis.get("confidence") or 0.0),
            detections=list(analysis.get("detections") or []),
            source=str(analysis.get("source") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Live visual analysis failed: {exc}") from exc

    event_rows = get_live_session_events(MEETING_DB_PATH, session_id)
    visual_rows = get_live_session_visual_events(MEETING_DB_PATH, session_id)
    config = default_config()
    live_payload = build_live_session_payload(session_row, event_rows, config, visual_rows=visual_rows)
    live_payload["visual_event_id"] = visual_event_id
    live_payload["latest_visual_analysis"] = analysis
    return live_payload


@app.post("/api/v1/live/{session_id}/copilot")
async def live_copilot(session_id: int, request: Request, payload: dict | None = None) -> dict:
    user = _user_with_workspace(request, _require_session_user(request), require_license=True)
    session_row = _resolve_owned_live_session(session_id, user)
    request_payload = await _collect_request_payload(request, payload)
    question = str(request_payload.get("question", "")).strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required.")
    event_rows = get_live_session_events(MEETING_DB_PATH, session_id)
    visual_rows = get_live_session_visual_events(MEETING_DB_PATH, session_id)
    config = default_config()
    live_payload = build_live_session_payload(session_row, event_rows, config, visual_rows=visual_rows)
    answer, source = answer_live_copilot(live_payload, question, config)
    save_live_copilot_reply(MEETING_DB_PATH, session_id, answer, source)
    return {
        "session_id": session_id,
        "question": question,
        "answer": answer,
        "source": source,
        "event_count": live_payload["session"]["event_count"],
        "summary": live_payload["copilot_context"]["summary"],
    }


@app.post("/api/v1/live/{session_id}/gitlab/preview")
async def live_gitlab_preview(session_id: int, request: Request, payload: dict | None = None) -> dict:
    user = _user_with_workspace(request, _require_session_user(request), require_license=True)
    request_payload = await _collect_request_payload(request, payload)
    return _create_gitlab_preview(session_id, user, request_payload)


@app.post("/api/v1/live/{session_id}/gitlab/sync")
async def live_gitlab_sync(session_id: int, request: Request, payload: dict | None = None) -> dict:
    user = _user_with_workspace(request, _require_session_user(request), require_license=True)
    request_payload = await _collect_request_payload(request, payload)
    return _sync_live_gitlab_preview(session_id, user, request_payload)


@app.post("/api/v1/live/{session_id}/finalize")
def finalize_live(session_id: int, request: Request) -> dict:
    user = _user_with_workspace(request, _require_session_user(request), require_license=True)
    _resolve_owned_live_session(session_id, user)
    finalize_live_session(MEETING_DB_PATH, session_id)
    event_rows = get_live_session_events(MEETING_DB_PATH, session_id)
    actual_seconds = max((float(row.get("end_seconds") or 0.0) for row in event_rows), default=0.0)
    commit_minutes(MEETING_DB_PATH, f"live:{session_id}", max(0.01, actual_seconds / 60.0), live_session_id=session_id)
    session_row = _resolve_owned_live_session(session_id, user)
    return {
        "session": {
            "id": session_id,
            "title": session_row.get("title", ""),
            "status": session_row.get("status", "finalized"),
            "started_at": session_row.get("started_at", ""),
            "finalized_at": session_row.get("finalized_at", ""),
        }
    }


def _build_output_payload(result, output_dir: Path, user: dict | None = None, *, usage_event_key: str | None = None, usage_minutes: float | None = None) -> dict:
    result_path = write_result(result, output_dir / "boardsight_result.json")
    meeting_id = save_meeting_result(
        MEETING_DB_PATH,
        result,
        output_dir=output_dir,
        result_file=result_path,
        user_id=int(user["user_id"]) if user is not None else None,
        username=str(user["username"]) if user is not None else None,
        organization_id=int(user["_workspace_id"]) if user is not None and user.get("_workspace_id") is not None else None,
    )
    if usage_event_key:
        commit_minutes(MEETING_DB_PATH, usage_event_key, float(usage_minutes or 0.0), meeting_id=meeting_id)
    payload = result.to_dict()
    payload["storage"] = {
        "meeting_id": meeting_id,
        "auth_db": str(AUTH_DB_PATH),
        "meeting_db": str(MEETING_DB_PATH),
        "output_dir": str(output_dir),
        "result_file": str(result_path),
    }
    return payload


def _resolve_output_dir(output_dir_name: str | None) -> Path:
    output_root = PROJECT_ROOT / "output"
    run_name = (output_dir_name or f"service-run-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}").strip()
    safe_run_name = "".join(char if char.isalnum() or char in "-_." else "_" for char in run_name) or "service-run"
    output_dir = output_root / safe_run_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _parse_optional_float(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)


def _resolve_analysis_input(
    source_video_path: Path,
    output_dir: Path,
    start_seconds: float | None,
    end_seconds: float | None,
) -> tuple[Path, dict | None]:
    if start_seconds is None and end_seconds is None:
        return source_video_path, None
    clipped_path = output_dir / "analysis_input.mp4"
    analysis_range = clip_video_fast(source_video_path, clipped_path, start_seconds, end_seconds)
    return Path(str(analysis_range["output_path"])).resolve(), analysis_range


def _analysis_minutes(video_path: Path, analysis_range: dict | None = None) -> float:
    duration_seconds = None
    if analysis_range:
        duration_seconds = analysis_range.get("duration_seconds")
        if duration_seconds is None and analysis_range.get("end_seconds") is not None:
            duration_seconds = max(0.0, float(analysis_range["end_seconds"]) - float(analysis_range.get("start_seconds") or 0.0))
    if duration_seconds is None:
        duration_seconds = probe_video(video_path).get("duration_sec")
    if duration_seconds is None:
        raise HTTPException(status_code=400, detail="Unable to determine meeting duration for workspace usage.")
    return max(0.01, float(duration_seconds) / 60.0)


def _run_pipeline_for_shared_path(
    shared_file_path: str,
    output_dir_name: str | None,
    user: dict | None = None,
    start_seconds: float | None = None,
    end_seconds: float | None = None,
    analysis_profile: str | None = None,
) -> dict:
    candidate_path = Path(unquote(shared_file_path)).resolve()
    output_root = PROJECT_ROOT / "output"
    if not str(candidate_path).startswith(str(output_root.resolve())):
        raise HTTPException(status_code=400, detail="Shared file path must be inside the output directory.")
    if not candidate_path.exists():
        raise HTTPException(status_code=400, detail="Shared file path does not exist for AI processing.")
    output_dir = _resolve_output_dir(output_dir_name)
    analysis_input_path, analysis_range = _resolve_analysis_input(candidate_path, output_dir, start_seconds, end_seconds)
    usage_minutes = _analysis_minutes(analysis_input_path, analysis_range)
    usage_key = f"recorded:{int(user['_workspace_id'])}:{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}" if user and user.get("_workspace_id") else None
    if usage_key:
        try:
            reserve_minutes(MEETING_DB_PATH, int(user["_workspace_id"]), int(user["user_id"]), usage_minutes, usage_type="recorded_analysis", event_key=usage_key)
        except (PermissionError, OverflowError) as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from exc
    try:
        result = run_pipeline(analysis_input_path, output_dir, analysis_range=analysis_range, analysis_profile=analysis_profile)
        return _build_output_payload(result, output_dir, user=user, usage_event_key=usage_key, usage_minutes=usage_minutes)
    except Exception:
        if usage_key:
            release_minutes(MEETING_DB_PATH, usage_key)
        raise


@app.post("/api/v1/pipeline/run-path")
async def run_pipeline_path_endpoint(request: Request, payload: dict | None = None) -> dict:
    user = _user_with_workspace(request, _require_session_user(request), require_license=True)
    request_payload = payload or {}
    if not request_payload:
        try:
            request_payload = await request.json()
        except Exception:
            request_payload = {}

    file_path = str(request_payload.get("file_path", "")).strip() or str(request.query_params.get("file_path", "")).strip()
    output_dir_name = (
        str(request_payload.get("output_dir_name", "")).strip()
        or str(request.query_params.get("output_dir_name", "")).strip()
        or None
    )
    analysis_profile = (
        str(request_payload.get("analysis_profile", "")).strip()
        or str(request.query_params.get("analysis_profile", "")).strip()
        or None
    )
    start_seconds = _parse_optional_float(request_payload.get("start_seconds", request.query_params.get("start_seconds")))
    end_seconds = _parse_optional_float(request_payload.get("end_seconds", request.query_params.get("end_seconds")))
    if not file_path:
        raise HTTPException(status_code=400, detail="file_path is required.")
    return _run_pipeline_for_shared_path(
        file_path,
        output_dir_name,
        user=user,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        analysis_profile=analysis_profile,
    )


@app.post("/api/v1/pipeline/run")
async def run_pipeline_endpoint(
    request: Request,
    file: UploadFile | None = File(default=None),
    upload: UploadFile | None = File(default=None),
    meeting_file: UploadFile | None = File(default=None),
    output_dir_name: str | None = Form(default=None),
) -> dict:
    user = _user_with_workspace(request, _require_session_user(request), require_license=True)
    resolved_upload = file or upload or meeting_file
    request_query = request.query_params
    request_payload: dict = {}

    if output_dir_name is None:
        output_dir_name = request_query.get("output_dir_name")

    request_content_type = request.headers.get("content-type", "")
    if "application/json" in request_content_type.lower():
        try:
            request_payload = await request.json()
        except Exception:
            request_payload = {}
        if output_dir_name is None:
            output_dir_name = str(request_payload.get("output_dir_name", "")).strip() or None

    if resolved_upload is None:
        try:
            form = await request.form()
        except Exception:
            form = None
        if form is not None:
            for field_name in ("file", "upload", "meeting_file"):
                candidate = form.get(field_name)
                if candidate is not None and hasattr(candidate, "filename") and hasattr(candidate, "read"):
                    resolved_upload = candidate
                    break

    raw_upload_bytes = b""
    raw_upload_name = request.headers.get("X-Filename") or request_query.get("filename") or "meeting.mp4"
    shared_file_path = str(request_payload.get("file_path", "")).strip() or request_query.get("file_path")
    start_seconds = _parse_optional_float(request_payload.get("start_seconds", request_query.get("start_seconds")))
    end_seconds = _parse_optional_float(request_payload.get("end_seconds", request_query.get("end_seconds")))
    analysis_profile = (
        str(request_payload.get("analysis_profile", "")).strip()
        or str(request_query.get("analysis_profile", "")).strip()
        or None
    )
    if resolved_upload is None:
        if shared_file_path:
            return _run_pipeline_for_shared_path(
                shared_file_path,
                output_dir_name,
                user=user,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                analysis_profile=analysis_profile,
            )

        try:
            raw_upload_bytes = await request.body()
        except Exception:
            raw_upload_bytes = b""
        if not raw_upload_bytes:
            raise HTTPException(status_code=400, detail="No uploaded file was provided to the AI service.")

    resolved_name = resolved_upload.filename if resolved_upload is not None else unquote(raw_upload_name)
    suffix = Path(resolved_name or "meeting.mp4").suffix or ".mp4"
    output_dir = _resolve_output_dir(output_dir_name)

    with tempfile.TemporaryDirectory(prefix="boardsight-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        video_path = temp_dir / f"upload{suffix}"
        if resolved_upload is not None:
            video_path.write_bytes(await resolved_upload.read())
        else:
            video_path.write_bytes(raw_upload_bytes)

        if not video_path.exists():
            raise HTTPException(status_code=400, detail="Failed to persist uploaded file.")

        analysis_input_path, analysis_range = _resolve_analysis_input(video_path, output_dir, start_seconds, end_seconds)
        usage_minutes = _analysis_minutes(analysis_input_path, analysis_range)
        usage_key = f"recorded:{int(user['_workspace_id'])}:{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
        try:
            reserve_minutes(MEETING_DB_PATH, int(user["_workspace_id"]), int(user["user_id"]), usage_minutes, usage_type="recorded_analysis", event_key=usage_key)
        except (PermissionError, OverflowError) as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from exc
        try:
            result = run_pipeline(analysis_input_path, output_dir, analysis_range=analysis_range, analysis_profile=analysis_profile)
            return _build_output_payload(result, output_dir, user=user, usage_event_key=usage_key, usage_minutes=usage_minutes)
        except Exception:
            release_minutes(MEETING_DB_PATH, usage_key)
            raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
