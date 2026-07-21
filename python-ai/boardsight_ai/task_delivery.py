from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from boardsight_ai.config import AppConfig
from boardsight_ai.gitlab_execution import sync_plan_to_gitlab


SUPPORTED_ASSIGNMENT_PROVIDERS = ("gitlab", "notion", "trello", "microsoft-todo")


def normalize_assignment_provider(value: str) -> str:
    provider = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "microsoft": "microsoft-todo",
        "ms-todo": "microsoft-todo",
        "todo": "microsoft-todo",
    }
    provider = aliases.get(provider, provider)
    if provider not in SUPPORTED_ASSIGNMENT_PROVIDERS:
        raise ValueError(f"Unsupported assignment provider: {value}")
    return provider


def _request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | list[Any]:
    request_headers = {"Accept": "application/json", **(headers or {})}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = Request(url, data=body, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"Assignment provider returned HTTP {exc.code}: {detail}") from exc
    return json.loads(raw) if raw else {}


def _missing(provider: str, reason: str) -> dict[str, Any]:
    return {
        "status": "dry-run-only",
        "provider": provider,
        "reason": reason,
        "created_tasks": [],
        "created_links": [],
    }


def _task_description(issue: dict[str, Any]) -> str:
    parts = [str(issue.get("description") or "").strip()]
    owner = str(issue.get("owner") or "Unassigned")
    parts.append(f"BoardSight owner: {owner}")
    dependencies = list(issue.get("dependencies") or [])
    if dependencies:
        parts.append(f"Depends on: {', '.join(str(item) for item in dependencies)}")
    parts.append(f"BoardSight task key: {issue.get('local_key', '')}")
    return "\n\n".join(part for part in parts if part)


def _sync_to_notion(plan: dict[str, Any], config: AppConfig, overrides: dict[str, Any]) -> dict[str, Any]:
    database_id = str(overrides.get("target_id") or overrides.get("database_id") or config.notion_database_id or "").strip()
    token = str(overrides.get("access_token") or overrides.get("token") or config.notion_api_token or "").strip()
    if not database_id or not token:
        return _missing("notion", "Notion integration token or database ID is missing.")
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2026-03-11",
        "Content-Type": "application/json",
    }
    database = _request_json(f"https://api.notion.com/v1/databases/{quote(database_id, safe='')}", headers=headers)
    properties = dict(database.get("properties") or {}) if isinstance(database, dict) else {}
    title_property = next((name for name, value in properties.items() if value.get("type") == "title"), "Name")
    created_tasks: list[dict[str, Any]] = []
    for issue in plan.get("issues", []):
        description = _task_description(issue)
        children = []
        for chunk_start in range(0, len(description), 1800):
            chunk = description[chunk_start:chunk_start + 1800]
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]},
            })
        created = _request_json(
            "https://api.notion.com/v1/pages",
            method="POST",
            headers=headers,
            payload={
                "parent": {"database_id": database_id},
                "properties": {
                    title_property: {"title": [{"type": "text", "text": {"content": str(issue.get('title') or 'BoardSight task')[:200]}}]},
                },
                "children": children[:100],
            },
        )
        created_tasks.append({
            "local_key": issue.get("local_key"),
            "id": created.get("id"),
            "title": issue.get("title"),
            "web_url": created.get("url"),
        })
    return {"status": "synced", "provider": "notion", "target_id": database_id, "created_tasks": created_tasks, "created_links": []}


def _sync_to_trello(plan: dict[str, Any], config: AppConfig, overrides: dict[str, Any]) -> dict[str, Any]:
    list_id = str(overrides.get("target_id") or overrides.get("list_id") or config.trello_list_id or "").strip()
    api_key = str(overrides.get("api_key") or config.trello_api_key or "").strip()
    token = str(overrides.get("access_token") or overrides.get("token") or config.trello_api_token or "").strip()
    if not list_id or not api_key or not token:
        return _missing("trello", "Trello API key, token, or destination list ID is missing.")
    member_map = dict(overrides.get("assignee_map") or {})
    created_tasks: list[dict[str, Any]] = []
    for issue in plan.get("issues", []):
        params = {"key": api_key, "token": token}
        payload: dict[str, Any] = {
            "idList": list_id,
            "name": str(issue.get("title") or "BoardSight task")[:16384],
            "desc": _task_description(issue),
        }
        if issue.get("due_date"):
            payload["due"] = f"{issue['due_date']}T17:00:00.000Z"
        member_id = member_map.get(str(issue.get("owner") or "").lower())
        if member_id:
            payload["idMembers"] = [str(member_id)]
        created = _request_json(
            f"https://api.trello.com/1/cards?{urlencode(params)}",
            method="POST",
            headers={"Content-Type": "application/json"},
            payload=payload,
        )
        created_tasks.append({
            "local_key": issue.get("local_key"),
            "id": created.get("id"),
            "title": created.get("name") or issue.get("title"),
            "web_url": created.get("shortUrl") or created.get("url"),
        })
    return {"status": "synced", "provider": "trello", "target_id": list_id, "created_tasks": created_tasks, "created_links": []}


def _sync_to_microsoft_todo(plan: dict[str, Any], config: AppConfig, overrides: dict[str, Any]) -> dict[str, Any]:
    list_id = str(overrides.get("target_id") or overrides.get("list_id") or config.microsoft_todo_list_id or "").strip()
    token = str(overrides.get("access_token") or overrides.get("token") or config.microsoft_graph_access_token or "").strip()
    if not list_id or not token:
        return _missing("microsoft-todo", "Microsoft Graph access token or To Do list ID is missing.")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    created_tasks: list[dict[str, Any]] = []
    endpoint = f"https://graph.microsoft.com/v1.0/me/todo/lists/{quote(list_id, safe='')}/tasks"
    for issue in plan.get("issues", []):
        payload: dict[str, Any] = {
            "title": str(issue.get("title") or "BoardSight task")[:255],
            "body": {"content": _task_description(issue), "contentType": "text"},
        }
        if issue.get("due_date"):
            payload["dueDateTime"] = {"dateTime": f"{issue['due_date']}T17:00:00.0000000", "timeZone": "UTC"}
        created = _request_json(endpoint, method="POST", headers=headers, payload=payload)
        created_tasks.append({
            "local_key": issue.get("local_key"),
            "id": created.get("id"),
            "title": created.get("title") or issue.get("title"),
            "web_url": created.get("webLink"),
        })
    return {"status": "synced", "provider": "microsoft-todo", "target_id": list_id, "created_tasks": created_tasks, "created_links": []}


def sync_plan_to_provider(
    provider: str,
    plan: dict[str, Any],
    config: AppConfig,
    *,
    connection_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_assignment_provider(provider)
    overrides = connection_overrides or {}
    if normalized == "gitlab":
        gitlab_overrides = {
            "base_url": overrides.get("base_url"),
            "project_id": overrides.get("target_id") or overrides.get("project_id"),
            "private_token": overrides.get("access_token") or overrides.get("private_token"),
        }
        result = sync_plan_to_gitlab(plan, config, connection_overrides=gitlab_overrides)
        created_tasks = [
            {**item, "id": item.get("iid"), "web_url": item.get("web_url")}
            for item in result.get("created_issues", [])
        ]
        return {**result, "provider": "gitlab", "target_id": result.get("project_id"), "created_tasks": created_tasks}
    if normalized == "notion":
        return _sync_to_notion(plan, config, overrides)
    if normalized == "trello":
        return _sync_to_trello(plan, config, overrides)
    return _sync_to_microsoft_todo(plan, config, overrides)


def provider_connection_summary(provider: str, config: AppConfig, overrides: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_assignment_provider(provider)
    target_defaults = {
        "gitlab": config.gitlab_project_id,
        "notion": config.notion_database_id,
        "trello": config.trello_list_id,
        "microsoft-todo": config.microsoft_todo_list_id,
    }
    token_defaults = {
        "gitlab": config.gitlab_private_token,
        "notion": config.notion_api_token,
        "trello": config.trello_api_token,
        "microsoft-todo": config.microsoft_graph_access_token,
    }
    return {
        "provider": normalized,
        "target_id": str(overrides.get("target_id") or target_defaults[normalized] or ""),
        "has_access_token": bool(overrides.get("access_token") or token_defaults[normalized]),
        "has_api_key": bool(overrides.get("api_key") or (config.trello_api_key if normalized == "trello" else None)),
        "base_url": str(overrides.get("base_url") or (config.gitlab_base_url if normalized == "gitlab" else "") or ""),
        "checked_at": datetime.utcnow().isoformat() + "Z",
    }


def validate_provider_connection(provider: str, config: AppConfig, overrides: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_assignment_provider(provider)
    summary = provider_connection_summary(normalized, config, overrides)
    target_id = summary["target_id"]
    if normalized == "gitlab":
        base_url = str(overrides.get("base_url") or config.gitlab_base_url or "https://gitlab.com").rstrip("/")
        token = str(overrides.get("access_token") or config.gitlab_private_token or "").strip()
        if not target_id or not token:
            raise ValueError("GitLab project and private token are required.")
        project = _request_json(
            f"{base_url}/api/v4/projects/{quote(target_id, safe='')}",
            headers={"PRIVATE-TOKEN": token},
        )
        return {**summary, "status": "connected", "destination_name": project.get("path_with_namespace") or project.get("name") or target_id}
    if normalized == "notion":
        token = str(overrides.get("access_token") or config.notion_api_token or "").strip()
        if not target_id or not token:
            raise ValueError("Notion database ID and integration token are required.")
        database = _request_json(
            f"https://api.notion.com/v1/databases/{quote(target_id, safe='')}",
            headers={"Authorization": f"Bearer {token}", "Notion-Version": "2026-03-11"},
        )
        title_items = list(((database.get("title") or [])) if isinstance(database, dict) else [])
        destination_name = "".join(str(item.get("plain_text") or "") for item in title_items).strip() or target_id
        return {**summary, "status": "connected", "destination_name": destination_name}
    if normalized == "trello":
        api_key = str(overrides.get("api_key") or config.trello_api_key or "").strip()
        token = str(overrides.get("access_token") or config.trello_api_token or "").strip()
        if not target_id or not api_key or not token:
            raise ValueError("Trello list ID, API key, and token are required.")
        trello_list = _request_json(
            f"https://api.trello.com/1/lists/{quote(target_id, safe='')}?{urlencode({'key': api_key, 'token': token, 'fields': 'name'})}",
        )
        return {**summary, "status": "connected", "destination_name": trello_list.get("name") or target_id}
    raise ValueError("Microsoft To Do must be connected through Microsoft OAuth.")
