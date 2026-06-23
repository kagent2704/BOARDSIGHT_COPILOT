# BoardSight

BoardSight is a multimodal meeting intelligence system for uploaded meeting recordings. It analyzes speech, speaker activity, visual artifacts, decision points, workflow transitions, and participant emotion/attention signals to produce structured outputs for review and export.

The agentic upgrade path is documented in [AGENTIC_ARCHITECTURE.md](/C:/Users/kashm/OneDrive/Desktop/BOARDSIGHT_CV_AGENTIC/AGENTIC_ARCHITECTURE.md). The short version: BoardSight becomes the structured meeting-intelligence backend, while Google Cloud Agent Builder orchestrates actions and GitLab MCP executes approved work.

The concrete cloud rollout plan now lives in [docs/GOOGLE_CLOUD_AGENT_IMPLEMENTATION_PLAN.md](/C:/Users/kashm/OneDrive/Desktop/BOARDSIGHT_CV_AGENTIC/docs/GOOGLE_CLOUD_AGENT_IMPLEMENTATION_PLAN.md), and the first Agent Builder-facing tool contract is documented in [docs/AGENT_BUILDER_TOOLKIT.md](/C:/Users/kashm/OneDrive/Desktop/BOARDSIGHT_CV_AGENTIC/docs/AGENT_BUILDER_TOOLKIT.md).

For independent public hosting, use [DEPLOY_RENDER_NEON.md](/C:/Users/kashm/OneDrive/Desktop/BOARDSIGHT_CV_AGENTIC/docs/DEPLOY_RENDER_NEON.md). A Render Blueprint file is included at [render.yaml](/C:/Users/kashm/OneDrive/Desktop/BOARDSIGHT_CV_AGENTIC/render.yaml).

The current codebase follows a deep-learning-only detection policy. If a required model is unavailable, the pipeline reports that feature as unavailable instead of falling back to heuristics.

See [PROJECT_ALIGNMENT.md](/C:/Users/kashm/OneDrive/Desktop/BOARDSIGHT/docs/PROJECT_ALIGNMENT.md) for the design direction that supersedes older papers and SRS language.

## What The Project Contains

- `java-app/`: Java web shell and UI
- `python-ai/`: Python inference pipeline, FastAPI service, storage, and report generation
- `scripts/`: Windows-oriented build and run scripts
- `output/`: generated analyses, exported reports, cached app data
- `docs/`: alignment notes and paper support material
- `legacy/`: older prototype material kept for reference

## Core Capabilities

- Upload a recorded meeting video through the web UI or run the pipeline directly from the CLI
- Generate transcripts with timestamps
- Estimate speaker dominance and participation balance
- Detect decision moments with transformer classification
- Classify visual artifacts such as slides, dashboards, charts, and speaker-video layouts
- Build decision traces and execution-oriented workflow outputs
- Run DeepFace emotion analysis and image-model-based attention classification
- Export JSON, Markdown, PDF, XLSX, transcript CSV, and summary image outputs

## Current Technical Direction

BoardSight is intentionally model-backed across its functional pipeline:

- ASR: `faster-whisper` by default, with transformer Whisper fallback
- Text classification: `typeform/distilbert-base-uncased-mnli`
- Image classification: `openai/clip-vit-base-patch32`
- Emotion: `DeepFace`
- Object detection: YOLO via `ultralytics`
- Optional diarization: `pyannote/speaker-diarization-3.1`

If you want the architecture rationale and the doc/SRS contradictions spelled out, start with [PROJECT_ALIGNMENT.md](/C:/Users/kashm/OneDrive/Desktop/BOARDSIGHT/docs/PROJECT_ALIGNMENT.md).

## Requirements

- Windows with Python 3.11 and Java installed
- PowerShell for the provided scripts
- Enough disk space for local model caches
- Hugging Face token in `python-ai/.env` if you want gated model access such as pyannote diarization

Core Python dependencies live in [requirements-core.txt](/C:/Users/kashm/OneDrive/Desktop/BOARDSIGHT_CV_AGENTIC/python-ai/requirements-core.txt). Heavier ML dependencies live in [requirements-ml.txt](/C:/Users/kashm/OneDrive/Desktop/BOARDSIGHT_CV_AGENTIC/python-ai/requirements-ml.txt).

## Install Python Dependencies

```powershell
cd "C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV_AGENTIC"
python -m pip install -r .\python-ai\requirements-core.txt
python -m pip install -r .\python-ai\requirements-ml.txt
```

## Run The Project

### Option 1: Web App With AI Service

Open two terminals.

Terminal 1, AI service in PowerShell:

```powershell
cd "C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV_AGENTIC\python-ai"
$env:PYTHONPATH="C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV_AGENTIC\python-ai"
$env:BOARDSIGHT_AGENT_API_KEY="boardsight-local-dev-key"
python -m boardsight_ai.service --host 127.0.0.1 --port 8000
```

Terminal 1, AI service in Command Prompt:

```cmd
cd "C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV_AGENTIC\python-ai"
set PYTHONPATH=C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV_AGENTIC\python-ai
set BOARDSIGHT_AGENT_API_KEY=boardsight-local-dev-key
python -m boardsight_ai.service --host 127.0.0.1 --port 8000
```

You can also use the script:

```powershell
.\scripts\run-ai-service.ps1
```

Terminal 2, web UI:

```powershell
cd "C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV_AGENTIC"
$env:BOARDSIGHT_AI_URL="http://127.0.0.1:8000"
.\scripts\build-java.ps1
.\scripts\run-web.ps1 -port 8080
```

Open:

- `http://localhost:8080` for the UI
- `http://127.0.0.1:8000/health` for the AI health check
- `http://localhost:8080/api/health` for the Java shell health check

### Option 2: Docker Compose

```powershell
cd "C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV_AGENTIC"
docker compose up --build
```

This starts:

- `boardsight-ai` on port `8000`
- `boardsight-web` on port `8080`

### Option 3: CLI Only

```powershell
cd "C:\Users\kashm\OneDrive\Desktop\BOARDSIGHT_CV_AGENTIC"
python .\python-ai\boardsight_ai\cli.py --video ".\output\short_sample.mp4" --output-dir ".\output\manual-run"
```

## Demo Login

The FastAPI service seeds a default admin account on startup:

- Username: `admin`
- Password: `boardsight123`

## Typical Workflow

1. Start the AI service.
2. Start the Java web app.
3. Open `http://localhost:8080`.
4. Sign in with the demo admin account.
5. Go to `Upload & Analyze`.
6. Upload a meeting video.
7. Review outputs in:
   - `Home`
   - `Meetings`
   - `AI Copilot`
   - `Decision Trace`
   - `Workflow Modelling`
8. Export reports from the meeting detail view.

## Output Files

Each run writes into a folder under `output/`. Typical outputs include:

- `boardsight_result.json`
- `structured_report.md`
- `structured_report.pdf`
- `structured_report.xlsx`
- `transcript.csv`
- `summary_card.png`
- `performance_report.json`

Meeting metadata is stored in:

- `output/appdata/boardsight_meetings.db`
- `output/appdata/boardsight_auth.db`

## Performance Tuning

The project now defaults to faster CPU-friendly settings:

- `faster-whisper` model defaults to `tiny.en`
- diarization is disabled by default for speed
- visual, attention, face, and workflow passes are sample-capped
- decision, visual, and attention stages can run in parallel
- recorded analysis profiles now gate OCR/caption enrichment so fast runs do not pay for deep extraction by default
- all configured model-backed stages still run; the main speedup path is lighter sampling plus optional clip-range preprocessing before analysis

Useful environment variables:

```powershell
$env:BOARDSIGHT_FASTER_WHISPER_MODEL="tiny.en"
$env:BOARDSIGHT_ENABLE_DIARIZATION="false"
$env:BOARDSIGHT_VIDEO_SAMPLE_SECONDS="20"
$env:BOARDSIGHT_VISUAL_SAMPLE_SECONDS="45"
$env:BOARDSIGHT_MAX_VISUAL_SAMPLES="2"
$env:BOARDSIGHT_MAX_ATTENTION_SAMPLES="1"
$env:BOARDSIGHT_MAX_FACE_SAMPLES="1"
$env:BOARDSIGHT_MAX_WORKFLOW_SEGMENTS="12"
```

Fast demo profile:

```powershell
$env:BOARDSIGHT_VISUAL_SAMPLE_SECONDS="60"
$env:BOARDSIGHT_MAX_VISUAL_SAMPLES="1"
$env:BOARDSIGHT_MAX_ATTENTION_SAMPLES="1"
$env:BOARDSIGHT_MAX_FACE_SAMPLES="1"
$env:BOARDSIGHT_MAX_WORKFLOW_SEGMENTS="8"
```

Available analysis profiles in the UI and API:

- `recorded-fast`: best for demo speed and iterative review
- `recorded-balanced`: moderate enrichment with conservative sampling
- `recorded-deep`: richer visual evidence extraction for final review
- `live`: intended for lower-latency live meeting use

Slower, richer profile:

```powershell
$env:BOARDSIGHT_ENABLE_DIARIZATION="true"
$env:BOARDSIGHT_MAX_VISUAL_SAMPLES="4"
$env:BOARDSIGHT_MAX_ATTENTION_SAMPLES="4"
$env:BOARDSIGHT_MAX_FACE_SAMPLES="2"
$env:BOARDSIGHT_MAX_WORKFLOW_SEGMENTS="32"
```

## Reported Stage Timings

Pipeline output JSON now includes stage timing metadata under:

`metadata.performance_report.stage_timings_seconds`

Agent-ready handoff data now also lives under:

`metadata.agentic_contract`

Budget tracking and any budget-protection skips are also recorded under:

`metadata.analysis_range`

That is the first place to look when a run used a selected video segment instead of the full recording.

## Fast Segment Analysis

The upload screen now supports optional `Start Time` and `End Time` inputs.

- Leave both blank to analyze the full video.
- Enter `mm:ss`, `hh:mm:ss`, or raw seconds to analyze only that portion.
- BoardSight performs fast FFmpeg-based clip preprocessing first, then runs the full deep-learning pipeline on the selected segment.

## Live Meeting Mode

BoardSight now includes a live meeting session flow for fast agent-style monitoring.

- Start a live session from the `Live Meeting` view in the web app
- Choose `Share Tab or Screen + Audio` for whole-meeting capture, or `Microphone Only` as a fallback
- BoardSight ingests rolling media chunks, transcribes them, and updates:
  - rolling meeting summary
  - problems and risks
  - decisions
  - action items
  - suggestions
  - meeting outcomes after finalization

Important notes:

- The currently running AI service and Java web app must be restarted after pulling these changes
- For the best live capture, share the meeting tab with audio enabled
- Live mode is transcript-first right now; video understanding for live sessions is not yet streamed frame-by-frame

## Agent Builder Endpoints

BoardSight now exposes an agent-facing API layer intended for Google Cloud Agent Builder:

- `GET /api/v1/agent/capabilities`
- `GET /api/v1/agent/sources`
- `GET /api/v1/agent/context/{source_kind}/{source_id}`
- `POST /api/v1/agent/execution/preview`
- `POST /api/v1/agent/execution/approve`
- `GET /api/v1/agent/execution/{approval_id}`

These endpoints are approval-aware and designed to keep GitLab writes out of the reasoning step until a human has approved the generated plan.

## Known Notes

- If port `8000` is already occupied, the AI service will fail to bind. Stop the existing process or use another port.
- If port `8080` is already occupied, launch the Java app with a different `--port`.
- DOCX export may fail on some Windows machines because `lxml` can be blocked by local application-control policy. PDF, XLSX, Markdown, transcript CSV, image summary, and JSON still complete.
- Older documents in the repo may still describe hybrid or heuristic behavior. The current implementation is model-backed and documented in [PROJECT_ALIGNMENT.md](/C:/Users/kashm/OneDrive/Desktop/BOARDSIGHT/docs/PROJECT_ALIGNMENT.md).

## Helpful Commands

Build the Java app:

```powershell
.\scripts\build-java.ps1
```

Run Java CLI mode:

```powershell
.\scripts\run-java.ps1 -video "C:\path\to\meeting.mp4"
```

Run AI service script:

```powershell
.\scripts\run-ai-service.ps1
```

Health checks:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health
Invoke-WebRequest -UseBasicParsing http://localhost:8080/api/health
```

## Repository Structure

```text
BOARDSIGHT/
|- docs/
|- java-app/
|- legacy/
|- output/
|- python-ai/
|- scripts/
|- docker-compose.yml
|- README.md
```
