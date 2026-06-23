from __future__ import annotations

import json
import os
from typing import Any

import httpx
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool


def _backend_url() -> str:
    value = os.getenv("BOARDSIGHT_AGENT_BACKEND_URL", "").strip().rstrip("/")
    if not value:
        raise RuntimeError("BOARDSIGHT_AGENT_BACKEND_URL is not configured.")
    return value


def _default_headers() -> dict[str, str]:
    headers = {"accept": "application/json"}
    api_key = os.getenv("BOARDSIGHT_AGENT_BACKEND_API_KEY", "").strip() or os.getenv("BOARDSIGHT_AGENT_API_KEY", "").strip()
    if api_key:
        headers["X-BoardSight-Agent-Key"] = api_key
    bearer = os.getenv("BOARDSIGHT_AGENT_BACKEND_BEARER", "").strip()
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    return headers


def _gitlab_defaults() -> dict[str, str]:
    return {
        "gitlab_base_url": os.getenv("BOARDSIGHT_GITLAB_BASE_URL", "").strip(),
        "gitlab_project_id": os.getenv("BOARDSIGHT_GITLAB_PROJECT_ID", "").strip(),
        "gitlab_private_token": os.getenv("BOARDSIGHT_GITLAB_PRIVATE_TOKEN", "").strip(),
    }


def _request(method: str, path: str, *, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{_backend_url()}{path}"
    with httpx.Client(timeout=60.0) as client:
        response = client.request(method, url, headers=_default_headers(), json=json_body)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        return data
    return {"result": data}


def get_capabilities() -> dict[str, Any]:
    """Return the BoardSight backend agent capabilities and expected workflow."""
    return _request("GET", "/api/v1/agent/capabilities")


def list_sources(limit_per_type: int = 10) -> dict[str, Any]:
    """List recent recorded meetings and live sessions visible to the BoardSight agent."""
    payload = _request("GET", "/api/v1/agent/sources")
    items = payload.get("items", {}) if isinstance(payload.get("items"), dict) else {}
    meetings = list(items.get("meetings", []) or [])[: max(1, limit_per_type)]
    live = list(items.get("live", []) or [])[: max(1, limit_per_type)]
    return {"items": {"meetings": meetings, "live": live}}


def get_source_context(source_kind: str, source_id: str) -> dict[str, Any]:
    """Fetch normalized context, meeting summary, and agentic contract for a live or recorded meeting source."""
    kind = source_kind.strip().lower()
    if kind not in {"meeting", "live"}:
        raise ValueError("source_kind must be 'meeting' or 'live'.")
    if not source_id.strip():
        raise ValueError("source_id is required.")
    return _request("GET", f"/api/v1/agent/context/{kind}/{source_id.strip()}")


def preview_execution(
    source_kind: str,
    source_id: str,
    assignee_map_json: str = "",
) -> dict[str, Any]:
    """Build a GitLab execution preview from a meeting source without writing to GitLab."""
    kind = source_kind.strip().lower()
    if kind not in {"meeting", "live"}:
        raise ValueError("source_kind must be 'meeting' or 'live'.")
    if not source_id.strip():
        raise ValueError("source_id is required.")
    assignee_map: dict[str, Any] = {}
    if assignee_map_json.strip():
        assignee_map = json.loads(assignee_map_json)
        if not isinstance(assignee_map, dict):
            raise ValueError("assignee_map_json must decode to a JSON object.")
    return _request(
        "POST",
        "/api/v1/agent/execution/preview",
        json_body={
            "source_kind": kind,
            "source_id": source_id.strip(),
            "assignee_map": assignee_map,
        },
    )


def approve_execution(
    approval_id: str,
    gitlab_project_id: str = "",
    gitlab_base_url: str = "",
    gitlab_private_token: str = "",
) -> dict[str, Any]:
    """Execute an approved GitLab sync for a previously previewed BoardSight plan."""
    resolved_approval_id = approval_id.strip()
    if not resolved_approval_id:
        raise ValueError("approval_id is required.")
    defaults = _gitlab_defaults()
    payload = {
        "approval_id": resolved_approval_id,
        "gitlab_project_id": gitlab_project_id.strip() or defaults["gitlab_project_id"],
        "gitlab_base_url": gitlab_base_url.strip() or defaults["gitlab_base_url"],
        "gitlab_private_token": gitlab_private_token.strip() or defaults["gitlab_private_token"],
    }
    if not payload["gitlab_project_id"] or not payload["gitlab_base_url"] or not payload["gitlab_private_token"]:
        raise RuntimeError(
            "GitLab defaults are incomplete. Set BOARDSIGHT_GITLAB_BASE_URL, "
            "BOARDSIGHT_GITLAB_PROJECT_ID, and BOARDSIGHT_GITLAB_PRIVATE_TOKEN."
        )
    return _request("POST", "/api/v1/agent/execution/approve", json_body=payload)


def get_execution_status(approval_id: str) -> dict[str, Any]:
    """Fetch the status of a previously previewed or approved BoardSight execution run."""
    resolved_approval_id = approval_id.strip()
    if not resolved_approval_id:
        raise ValueError("approval_id is required.")
    return _request("GET", f"/api/v1/agent/execution/{resolved_approval_id}")


root_agent = LlmAgent(
    model=os.getenv("BOARDSIGHT_AGENT_MODEL", "gemini-2.5-flash"),
    name="boardsight_execution_agent",
    description="Turns BoardSight live or recorded meeting context into approval-gated GitLab execution plans.",
    instruction=(
        "You are the BoardSight execution agent for governance and delivery teams. "
        "Start by using BoardSight tools to inspect available meeting sources or load source context. "
        "Use the normalized meeting context and the agentic contract to explain what happened in the meeting. "
        "When the user asks for follow-through, first call preview_execution and summarize the proposed GitLab plan. "
        "Never call approve_execution until the user clearly asks you to proceed. "
        "After approval, report the execution status and the created work items clearly. "
        "If the source is still live, mention that the meeting can continue to evolve and use the latest available context."
    ),
    tools=[
        get_capabilities,
        list_sources,
        get_source_context,
        preview_execution,
        FunctionTool(approve_execution, require_confirmation=True),
        get_execution_status,
    ],
)
