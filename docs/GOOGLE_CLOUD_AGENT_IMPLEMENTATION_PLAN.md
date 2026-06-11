# Google Cloud Agent Implementation Plan

## Goal

Turn BoardSight from a local meeting-analysis application into a hackathon-ready AI agent system built around:

1. `Google Cloud Agent Builder` for reasoning, planning, approvals, and orchestration
2. `BoardSight AI Service` for multimodal meeting understanding and durable meeting memory
3. `GitLab MCP` for turning approved commitments into executable work

## What BoardSight Already Has

- recorded meeting analysis
- live meeting analysis with rolling transcript and visual updates
- normalized `agentic_contract` output
- GitLab execution planning and sync logic
- a web workflow for humans to inspect live context and GitLab previews

## What Makes It A Real Agent

The hackathon requirement is not just "AI analysis." The product needs:

- reasoning over meeting context
- explicit tool use
- approvals before side effects
- execution against a real external workflow system

That means BoardSight should stop being the whole agent and instead become the agent's tool-backed perception layer.

## Target Runtime

### Cloud Agent Layer

`Google Cloud Agent Builder`

- accepts the user goal
- decides whether to inspect live context, recorded context, or execution state
- fetches normalized meeting memory from BoardSight
- proposes GitLab actions
- asks for approval when writes are about to happen
- calls GitLab MCP after approval

### Tool Layer

`BoardSight AI Service`

- `GET /api/v1/agent/capabilities`
- `GET /api/v1/agent/sources`
- `GET /api/v1/agent/context/{source_kind}/{source_id}`
- `POST /api/v1/agent/execution/preview`
- `POST /api/v1/agent/execution/approve`
- `GET /api/v1/agent/execution/{approval_id}`

### Execution Layer

`GitLab MCP`

- issue creation
- milestone updates
- dependency links
- follow-up status pulls in future meetings

## Agent Flow

### Recorded Meeting Flow

1. User uploads a meeting to BoardSight.
2. BoardSight generates transcript, decisions, actions, risk signals, and `agentic_contract`.
3. Agent Builder calls `get_source_context`.
4. Agent Builder reasons over decisions, blockers, and follow-up work.
5. Agent Builder calls `execution_preview`.
6. User approves.
7. Agent Builder calls GitLab MCP or BoardSight `execution_approve`.
8. Sync metadata is stored for traceability.

### Live Meeting Flow

1. BoardSight ingests live chunks.
2. Rolling state is persisted in the live session store.
3. Agent Builder polls or is triggered against `get_source_context`.
4. The agent identifies emerging decisions, blockers, and tasks.
5. At the end of the meeting, the agent proposes a GitLab execution plan.
6. User approves and execution begins.

## Data Model

### Canonical Handoff Object

`agentic_contract`

- `meeting_digest`
- `entities.decisions`
- `entities.actions`
- `entities.risk_signals`
- `entities.visual_artifacts`
- `execution_graph`

### Agent Execution Persistence

`output/appdata/boardsight_agent.db`

- approval id
- source kind and source id
- meeting title
- previewed plan
- approval status
- GitLab sync result

This keeps reasoning state and execution state auditable.

## Implementation Phases

### Phase 1

Already started in this repo:

- normalize meeting memory for agent consumption
- approval-gated execution preview endpoint
- approval execution persistence
- backend status endpoint for agent execution runs

### Phase 2

Next:

- deploy the FastAPI service to Google Cloud Run
- register BoardSight endpoints as Agent Builder tools
- configure GitLab MCP in the partner-track flow
- add approval language to the Agent Builder prompt/instructions

### Phase 3

Demo hardening:

- push execution traces back into future meeting context
- improve low-quality action extraction for procedural meetings
- tighten assignee resolution with a participant-to-GitLab map

## Required Credentials And Access

I will need these to complete the real cloud hookup:

- Google Cloud project id
- access to the Agent Builder app or the target Vertex/Agent Builder workspace
- deployment target choice: `Cloud Run` is the simplest
- GitLab base URL
- GitLab project id or `group/project` path
- GitLab private token

## Recommended Demo Story

1. Start a live meeting.
2. Let BoardSight collect decisions and blockers.
3. Show the normalized agent context.
4. Generate an execution preview.
5. Approve the plan.
6. Show GitLab issues and links created from the meeting.
