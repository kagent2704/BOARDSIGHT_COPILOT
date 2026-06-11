# Agent Builder Toolkit

## Recommended Tool Registration

Register the BoardSight FastAPI service in Google Cloud Agent Builder as a tool-backed HTTP service.

Primary endpoints:

- `GET /health`
- `GET /api/v1/agent/capabilities`
- `GET /api/v1/agent/sources`
- `GET /api/v1/agent/context/{source_kind}/{source_id}`
- `POST /api/v1/agent/execution/preview`
- `POST /api/v1/agent/execution/approve`
- `GET /api/v1/agent/execution/{approval_id}`

## Suggested Agent Instructions

Use BoardSight to understand meetings and GitLab MCP to execute approved work.

Rules:

1. Always inspect BoardSight meeting context before proposing work.
2. Prefer the normalized `agentic_contract` over free-text summaries.
3. Never execute GitLab writes without explicit user approval.
4. If the meeting is still live, prefer a preview plan until the user finalizes the session.
5. Preserve traceability between each GitLab work item and the meeting source id.

## Suggested Tool Sequence

### Discover

Call:

- `GET /api/v1/agent/sources`

### Understand

Call:

- `GET /api/v1/agent/context/live/{session_id}`
- or `GET /api/v1/agent/context/meeting/{meeting_id}`

### Plan

Call:

- `POST /api/v1/agent/execution/preview`

Payload:

```json
{
  "source_kind": "live",
  "source_id": "abc123"
}
```

### Approve And Execute

Call:

- `POST /api/v1/agent/execution/approve`

Payload:

```json
{
  "approval_id": "preview-id",
  "gitlab_base_url": "https://gitlab.com",
  "gitlab_project_id": "group/project",
  "gitlab_private_token": "token"
}
```

### Inspect

Call:

- `GET /api/v1/agent/execution/{approval_id}`

## Deployment Hint

The simplest cloud path is:

1. Deploy BoardSight FastAPI to `Cloud Run`
2. Put the service behind authenticated HTTPS
3. Register the service in Agent Builder
4. Connect GitLab MCP in the hackathon partner flow
