from __future__ import annotations

from typing import Any

from boardsight_ai.models import PipelineResult


def _decision_lookup(result: PipelineResult) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("decision_id")): item
        for item in result.workflow_model.prioritized_decisions
        if item.get("decision_id")
    }


def _task_lookup(result: PipelineResult) -> dict[str, list[dict[str, Any]]]:
    lookup: dict[str, list[dict[str, Any]]] = {}
    for task in result.workflow_model.execution_plan:
        lookup.setdefault(str(task.get("decision_id") or ""), []).append(task)
    return lookup


def _risk_signals(result: PipelineResult) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for index, bottleneck in enumerate(result.workflow_model.bottlenecks, start=1):
        signals.append(
            {
                "risk_id": f"RS-{index}",
                "kind": "workflow-bottleneck",
                "description": bottleneck,
                "severity": "medium" if "no major" in bottleneck.lower() else "high",
                "source": "workflow_model",
            }
        )

    if result.attention_sentiment.overall_attention and result.attention_sentiment.overall_attention < 45:
        signals.append(
            {
                "risk_id": f"RS-{len(signals) + 1}",
                "kind": "engagement-risk",
                "description": f"Meeting attention dropped to {result.attention_sentiment.overall_attention:.1f}%.",
                "severity": "medium",
                "source": "attention_sentiment",
            }
        )
    return signals


def build_agentic_contract(
    result: PipelineResult,
    *,
    analysis_profile: str,
    source_mode: str,
    contract_version: str,
) -> dict[str, Any]:
    prioritized_lookup = _decision_lookup(result)
    tasks_by_decision = _task_lookup(result)

    decisions: list[dict[str, Any]] = []
    for moment in result.decision_moments:
        priority = prioritized_lookup.get(moment.event_id, {})
        linked_tasks = tasks_by_decision.get(moment.event_id, [])
        decisions.append(
            {
                "decision_id": moment.event_id,
                "timestamp": moment.timestamp,
                "speaker": moment.speaker,
                "label": moment.label,
                "text": moment.text,
                "confidence": moment.confidence,
                "priority_score": float(priority.get("priority_score", 0.0) or 0.0),
                "execution_rank": int(priority.get("execution_rank", 0) or 0),
                "artifact_support": list(priority.get("artifact_support", [])),
                "task_ids": [str(task.get("task_id")) for task in linked_tasks if task.get("task_id")],
                "evidence": moment.evidence,
            }
        )

    actions = [
        {
            "task_id": str(task.get("task_id") or ""),
            "decision_id": str(task.get("decision_id") or ""),
            "title": str(task.get("title") or ""),
            "owner": str(task.get("owner") or "Unassigned"),
            "priority_score": float(task.get("priority_score", 0.0) or 0.0),
            "execution_order": int(task.get("execution_order", 0) or 0),
            "task_type": str(task.get("task_type") or ""),
            "notes": str(task.get("notes") or ""),
            "delivery_target": "gitlab-mcp-candidate",
        }
        for task in result.workflow_model.execution_plan
    ]

    artifacts = [
        {
            "artifact_id": artifact.artifact_id,
            "start_time": artifact.start_time,
            "end_time": artifact.end_time,
            "artifact_type": artifact.artifact_type,
            "display_mode": artifact.display_mode,
            "confidence": artifact.confidence,
            "content_hint": artifact.content_text or artifact.content_insight or artifact.content_summary,
        }
        for artifact in result.visual_artifacts
    ]

    return {
        "contract_version": contract_version,
        "source_mode": source_mode,
        "analysis_profile": analysis_profile,
        "meeting_digest": {
            "input_video": result.input_video,
            "meeting_conclusion": result.meeting_scores.meeting_conclusion,
            "execution_readiness": result.meeting_scores.execution_readiness,
            "impact_score": result.meeting_scores.impact_score,
            "productivity_score": result.meeting_scores.productivity_score,
        },
        "entities": {
            "decisions": decisions,
            "actions": actions,
            "risk_signals": _risk_signals(result),
            "visual_artifacts": artifacts,
        },
        "execution_graph": {
            "decision_count": len(decisions),
            "action_count": len(actions),
            "top_decision_id": result.workflow_model.workflow_summary.get("top_priority_decision", "None"),
            "workflow_stage_count": len(result.workflow_model.stages),
        },
    }
