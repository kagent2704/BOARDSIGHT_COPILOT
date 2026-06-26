# BoardSight Cloud Run Deployment

This is the cleanest hosted path when you want the full BoardSight Copilot stack without trimming core features.

## What gets deployed

1. `boardsight-ai`
   The Python FastAPI service that runs meeting analysis, live session intelligence, GitLab planning, and Copilot chat.
2. `boardsight-web`
   The Java web shell and UI that proxies into the AI service.

## Before you start

Make sure these are already true in Google Cloud:

- billing enabled
- `Cloud Run` API enabled
- `Cloud Build` API enabled
- `Artifact Registry` API enabled
- project selected in `gcloud`

Recommended local check:

```powershell
gcloud config list
```

## Required values

- `PROJECT_ID`
- `REGION`
- `BOARDSIGHT_DATABASE_URL`
- `BOARDSIGHT_AGENT_API_KEY`

Optional but recommended for full execution workflows:

- `BOARDSIGHT_GITLAB_BASE_URL`
- `BOARDSIGHT_GITLAB_PROJECT_ID`
- `BOARDSIGHT_GITLAB_PRIVATE_TOKEN`

Optional for higher-quality Copilot answers:

- `GEMINI_API_KEY`
- `BOARDSIGHT_GEMINI_MODEL` such as `gemini-3.1-flash-lite`

## Recommended production-ish sizing

For the AI service:

- memory: `4Gi` to `8Gi`
- cpu: `2` to `4`
- timeout: `900`

For the web service:

- memory: `1Gi`
- cpu: `1`

If you want the cheapest possible starting point, keep the defaults and scale the AI service up only if you see runtime memory pressure.

## Deploy the AI service

From the repo root:

```powershell
cd "C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV_AGENTIC"

.\scripts\deploy-ai-cloud-run.ps1 `
  -ProjectId "boardsight-agent" `
  -Region "us-central1" `
  -ServiceName "boardsight-ai" `
  -DatabaseUrl "postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require" `
  -AgentApiKey "replace-with-a-long-random-key" `
  -GitLabBaseUrl "https://gitlab.com" `
  -GitLabProjectId "kagent007/boardsight-agent" `
  -GitLabPrivateToken "replace-with-your-gitlab-token" `
  -LlmProvider "gemini" `
  -GeminiApiKey "replace-with-your-gemini-api-key" `
  -GeminiModel "gemini-3.1-flash-lite" `
  -Memory "4Gi" `
  -Cpu 2 `
  -TimeoutSeconds 900 `
  -MaxInstances 2 `
  -AllowUnauthenticated
```

When this finishes, copy the service URL.

Useful health check:

```powershell
Invoke-WebRequest -UseBasicParsing "https://YOUR-AI-URL/health"
```

## Deploy the web service

Use the AI URL from the first deployment:

```powershell
cd "C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV_AGENTIC"

.\scripts\deploy-web-cloud-run.ps1 `
  -ProjectId "boardsight-agent" `
  -Region "us-central1" `
  -ServiceName "boardsight-web" `
  -AiServiceUrl "https://YOUR-AI-URL" `
  -Memory "1Gi" `
  -Cpu 1 `
  -TimeoutSeconds 300 `
  -MaxInstances 2 `
  -AllowUnauthenticated
```

When this finishes, open the returned `boardsight-web` URL in the browser.

## Default login

- username: `admin`
- password: `boardsight123`

## What to verify after deploy

1. Open the web URL.
2. Log in with the demo admin account.
3. Open `AI Copilot`.
4. Open `Live Meeting`.
5. Upload a short video in `Upload & Analyze`.
6. Confirm the meeting appears in `Meetings`.
7. Ask the Copilot a question against a specific meeting.
8. If GitLab is configured, generate a GitLab plan.

## Notes

- The AI root URL is an API service, not the main product UI. Use the web service URL for the product.
- Cloud Run cold starts are expected, especially on the AI service.
- If build times or memory usage get painful later, the next upgrade is to prebuild the AI image locally or in CI, push it to Artifact Registry, and deploy by image instead of source.
- If you do not set `GEMINI_API_KEY`, BoardSight will keep using its grounded extractive fallback or the local transformer path, depending on `BOARDSIGHT_LLM_PROVIDER`.
