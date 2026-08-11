# BoardSight ADK Cloud Run Deployment

> **Implementation status:** Experimental only. The ADK client currently expects `/api/v1/agent/*` routes that are not implemented by the BoardSight FastAPI service in this repository, so the documented agent flow is not production-ready end to end.

This is the fallback deployment path for the hackathon when Google Cloud Agent Builder UI is unstable.

## What it does

- Deploys a lightweight Google ADK agent to Cloud Run.
- Uses Vertex AI through Google Cloud credentials.
- Calls the existing BoardSight FastAPI backend for:
  - meeting discovery
  - live or recorded meeting context
  - GitLab execution previews
  - approval-gated GitLab sync

## Folder layout

```text
python-agent/
  boardsight_agent/
    __init__.py
    agent.py
  main.py
  requirements.txt
  Dockerfile
  .env.example
```

## Required environment variables

- `GOOGLE_GENAI_USE_VERTEXAI=true`
- `GOOGLE_CLOUD_PROJECT=boardsight-agent`
- `GOOGLE_CLOUD_LOCATION=us-central1`
- `BOARDSIGHT_AGENT_BACKEND_URL=https://boardsight-ai-lo7o6ublra-uc.a.run.app`
- `BOARDSIGHT_AGENT_BACKEND_API_KEY=<BoardSight backend key>`
- `BOARDSIGHT_GITLAB_BASE_URL=https://gitlab.com`
- `BOARDSIGHT_GITLAB_PROJECT_ID=kagent007/boardsight-agent`
- `BOARDSIGHT_GITLAB_PRIVATE_TOKEN=<GitLab token>`

If you do not want to store the GitLab token in Cloud Run yet, the ADK approval tool can also accept `gitlab_private_token` explicitly at runtime.

## Local dev

From `python-agent/`:

```powershell
python -m pip install -r requirements.txt
$env:GOOGLE_GENAI_USE_VERTEXAI="true"
$env:GOOGLE_CLOUD_PROJECT="boardsight-agent"
$env:GOOGLE_CLOUD_LOCATION="us-central1"
$env:BOARDSIGHT_AGENT_BACKEND_URL="https://boardsight-ai-lo7o6ublra-uc.a.run.app"
$env:BOARDSIGHT_AGENT_BACKEND_API_KEY="<backend-key>"
$env:BOARDSIGHT_GITLAB_BASE_URL="https://gitlab.com"
$env:BOARDSIGHT_GITLAB_PROJECT_ID="kagent007/boardsight-agent"
$env:BOARDSIGHT_GITLAB_PRIVATE_TOKEN="<gitlab-token>"
adk web --port 8080
```

## Cloud Run deploy

From the repo root:

```powershell
.\scripts\deploy-adk-agent-cloud-run.ps1 `
  -ProjectId boardsight-agent `
  -Region us-central1 `
  -ServiceName boardsight-agent-runtime `
  -BackendUrl https://boardsight-ai-lo7o6ublra-uc.a.run.app `
  -BackendApiKey <backend-key> `
  -GitLabBaseUrl https://gitlab.com `
  -GitLabProjectId kagent007/boardsight-agent `
  -GitLabPrivateToken <gitlab-token> `
  -AllowUnauthenticated
```

## Demo flow

1. Open the ADK Cloud Run URL in a browser.
2. Ask the agent to list recent meeting sources.
3. Ask it to inspect the latest live or recorded meeting.
4. Ask it to preview the GitLab execution plan.
5. Approve execution only when ready.
