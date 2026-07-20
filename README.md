# BoardSight

BoardSight is a meeting-intelligence product for recorded and live meetings. Recorded uploads now run the lightweight BoardSight production pipeline: fast speech transcription, sparse sampled-frame visual analysis, person detection, structured workflow and decision extraction, exportable reports, and optional Gemini-backed reasoning.

This repository now ships one stable production path instead of multiple competing local analysis stacks.

It also includes a live-meeting workspace: start a session, stream speech or paste transcript updates, and use the in-meeting copilot as a companion popup for catch-up questions.

## Organizations, Licensing, and Usage

BoardSight now treats an organization workspace as the commercial boundary. Existing accounts are migrated lazily into a personal workspace without losing their meetings. New team workspaces start on the Starter trial and support four workspace-only roles:

- `owner`: billing, licenses, invitations, and workspace settings
- `admin`: member and integration management
- `member`: licensed meeting and Live Copilot processing
- `viewer`: free access to shared results without initiating paid processing

Workspace roles are deliberately separate from the application-level administrator role. Recorded meetings, live sessions, usage reservations, and GitLab sync records are organization-scoped. Processing reserves pooled minutes before work begins, then commits actual usage or releases the reservation after a failure.

Built-in entitlements match the initial INR packaging:

| Plan | Licensed members | Pooled minutes/month | Intended price |
| --- | ---: | ---: | ---: |
| Personal | 1 | 300 | ₹199/month |
| Starter | 3 | 1,200 | ₹499/month |
| Growth | 10 | 4,000 | ₹999/month |

Initial customers can be activated manually through `PUT /api/v1/admin/workspaces/{organization_id}/subscription` by a global BoardSight administrator. Payment-provider webhooks and transactional invitation email are intentionally not enabled yet; workspace owners currently receive a shareable seven-day invitation link in the UI.

The browser sends `X-BoardSight-Workspace-ID` for workspace-scoped requests. If omitted, the service selects the user's personal or first available workspace.

## Production Pipeline

BoardSight now runs a single production pipeline for recorded meetings:

1. Extract audio and generate a timestamped transcript
2. Derive speaker participation and dominance from transcript timing
3. Detect decisions, action items, blockers, and outcomes from transcript structure
4. Inspect sparse sampled frames for presentation, screen-share, document, and participant-camera evidence
5. Build workflow stages, execution tasks, and decision traces
6. Generate exports and persist the normalized result contract

Optional Gemini use:

- If `BOARDSIGHT_LLM_PROVIDER=gemini` and `GEMINI_API_KEY` is set, BoardSight uses Gemini for structured JSON extraction and concise meeting summaries.
- If Gemini is unavailable, BoardSight falls back to deterministic transcript-grounded heuristics.

## What Changed

- The recorded-analysis runtime is `boardsight-production-lightweight-v1`
- Older deep-profile requests are still accepted for compatibility, but they resolve to the same production pipeline
- Meeting storage records:
  - `runtime_profile`
  - `data_contract_version`
  - `requested_analysis_profile`
  - `effective_analysis_profile`

## Repository Layout

- `java-app/`: Java shell and browser UI
- `python-ai/`: AI service, pipeline, storage, reporting, CLI
- `scripts/`: local build and run scripts
- `output/`: analyzed meetings, report artifacts, app databases
- `docs/`: supporting notes and older alignment docs
- `legacy/`: older prototype assets

## Requirements

- Python 3.11
- Java
- FFmpeg on PATH
- PowerShell for the bundled scripts on Windows

Recommended Python install sets:

- [python-ai/requirements-core.txt](C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV\python-ai\requirements-core.txt)
- [python-ai/requirements-runtime.txt](C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV\python-ai\requirements-runtime.txt)
- [python-ai/requirements-dev.txt](C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV\python-ai\requirements-dev.txt)

The old production install path that relied on `requirements-ml.txt` has been removed.

## Install

```powershell
cd "C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV"
python -m pip install -r .\python-ai\requirements-core.txt
python -m pip install -r .\python-ai\requirements-runtime.txt
```

For tests:

```powershell
python -m pip install -r .\python-ai\requirements-dev.txt
```

## Environment

Start from [python-ai/sample-config.env](C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV\python-ai\sample-config.env).

Important settings:

```powershell
$env:BOARDSIGHT_ANALYSIS_PROFILE="production"
$env:BOARDSIGHT_LLM_PROVIDER="gemini"
$env:GEMINI_API_KEY="your-key"
$env:BOARDSIGHT_ENABLE_DIARIZATION="false"
$env:BOARDSIGHT_FASTER_WHISPER_MODEL="tiny.en"
```

## Run Locally

### Terminal 1: AI Service

```powershell
cd "C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV"
$env:PYTHONPATH="python-ai"
python -m boardsight_ai.service --host 127.0.0.1 --port 8000
```

Or:

```powershell
.\scripts\run-ai-service.ps1
```

### Terminal 2: Web App

```powershell
cd "C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV"
$env:BOARDSIGHT_AI_URL="http://127.0.0.1:8000"
.\scripts\build-java.ps1
java -jar .\java-app\build\boardsight.jar --port 8080
```

Open:

- `http://localhost:8080`
- `http://127.0.0.1:8000/health`

## Live Meeting Copilot

From the `Live Meeting` workspace in the UI you can:

- start a live session
- use browser speech recognition when supported
- paste manual transcript updates if speech capture is unavailable
- ask questions like:
  - `What happened so far?`
  - `What decisions have been made?`
  - `I joined 10 minutes late. What happened before I joined?`

Live copilot answers are grounded in the transcript accumulated so far and fall back to local heuristic reasoning if Gemini is unavailable.

## CLI Run

```powershell
cd "C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV"
python .\python-ai\boardsight_ai\cli.py --video ".\output\short_sample.mp4" --output-dir ".\output\manual-run"
```

Optional clipped analysis:

```powershell
python .\python-ai\boardsight_ai\cli.py `
  --video ".\output\short_sample.mp4" `
  --output-dir ".\output\manual-run" `
  --start-seconds 0 `
  --end-seconds 180 `
  --analysis-profile production
```

## Docker

The Python image now installs the production runtime dependencies instead of the old full ML stack.

```powershell
cd "C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV"
docker compose up --build
```

## Default Login

- Username: `admin`
- Password: `boardsight123`

## Output Contract

Each run writes a result folder under `output/`, typically containing:

- `boardsight_result.json`
- `structured_report.md`
- `structured_report.pdf`
- `structured_report.xlsx`
- `structured_report.docx`
- `transcript.csv`
- `summary_card.png`
- `performance_report.json`

App databases:

- `output/appdata/boardsight_meetings.db`
- `output/appdata/boardsight_auth.db`

The persisted result metadata now includes:

- `data_contract_version`
- `storage_schema_version`
- `requested_analysis_profile`
- `effective_analysis_profile`
- `performance_report.runtime_profile`

## Testing

```powershell
cd "C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV"
pytest .\python-ai\tests -q
python -m compileall .\python-ai\boardsight_ai .\python-ai\tests
cd .\java-app
cmd /c "javac -d build\classes @java_sources.txt"
```

One-command local smoke check:

```powershell
cd "C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV"
.\scripts\smoke-test-local.ps1
```

## Product Notes

- This repo is oriented around one stable production pipeline instead of a research-style pile of optional vision models.
- Gemini improves structured answers and summaries, but the product still returns usable outputs without it.
- The old heavy analysis modules have been removed from the production code path and dependency bundle.
