# BoardSight Agentic Architecture

## Direction

BoardSight is being reshaped from a report-first meeting analyzer into an agent-ready execution system.

The target runtime split is:

1. `BoardSight AI pipeline`
   Turns live or recorded meeting media into structured decisions, actions, risks, and evidence.
2. `Google Cloud Agent Builder`
   Orchestrates planning, user approval, follow-up reasoning, and long-running execution.
3. `GitLab MCP`
   Converts approved BoardSight actions into issues, milestones, epics, and traceable work items.

## Data Contract

Every completed run should now produce:

- raw transcript and multimodal analysis outputs
- stable report artifacts for UI/export
- an `agentic_contract` envelope under `metadata.agentic_contract`

That contract is designed to be the handoff format for cloud orchestration. It contains:

- `meeting_digest`
- `entities.decisions`
- `entities.actions`
- `entities.risk_signals`
- `entities.visual_artifacts`
- `execution_graph`

This keeps the UI/report layer separate from the action layer, so future GitLab and Agent Builder integrations do not need to parse presentation-oriented report text.

## Recorded vs Live

The system now distinguishes:

- `source_mode=recorded`
- `source_mode=live`

And supports analysis profiles:

- `recorded-fast`
- `recorded-balanced`
- `recorded-deep`
- `live`

These profiles explicitly control expensive stages such as OCR, captioning, workflow sampling depth, and attention sampling rather than burying performance behavior in scattered environment variables.

## Latency Strategy

To reduce recorded-meeting analysis time without collapsing the schema:

1. Speech and speaker labeling stay as the dependency root.
2. Decision detection, visual analysis, and attention/sentiment now run in parallel.
3. Heavy visual enrichment is profile-gated.
4. Attention analysis no longer spawns a fresh Python subprocess for each run.

This keeps the result shape stable while cutting unnecessary serial work.

## Cloud Mapping

Recommended next step for Google Cloud Agent Builder:

1. Keep BoardSight as a callable backend tool/service.
2. Feed `agentic_contract` into Agent Builder as the normalized meeting memory object.
3. Require user approval before GitLab MCP writes tasks.
4. Persist approved actions and downstream GitLab IDs back into a durable run store.

## Persistence Notes

The local SQLite layer now stores run profile and agentic summary fields alongside the raw result JSON.

For cloud deployment, the same logical model can map cleanly to:

- operational run store: `Cloud SQL` or `Firestore`
- searchable meeting memory and analytics: `BigQuery`
- media and report artifacts: `Cloud Storage`
