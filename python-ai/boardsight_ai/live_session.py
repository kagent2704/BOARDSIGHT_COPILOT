from __future__ import annotations

import re
from typing import Any

from boardsight_ai.config import AppConfig
from boardsight_ai.features import speaker_dominance
from boardsight_ai.lightweight_pipeline import (
    _build_attention_sentiment,
    _build_meeting_scores,
    _build_workflow_model,
    _extract_structured_moments,
    _merge_gemini_structure,
)
from boardsight_ai.models import TranscriptResult, TranscriptSegment
from boardsight_ai.providers.llm import answer_question


def _seconds_to_timestamp(value: float) -> str:
    total_seconds = max(0, int(value))
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def _build_segments(event_rows: list[dict[str, Any]]) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    for index, row in enumerate(event_rows, start=1):
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        speaker = str(row.get("speaker") or "").strip() or f"Participant {index}"
        start_seconds = float(row.get("start_seconds") or 0.0)
        end_seconds = float(row.get("end_seconds") or max(start_seconds + 4.0, start_seconds))
        segments.append(
            TranscriptSegment(
                start=start_seconds,
                end=max(end_seconds, start_seconds + 0.1),
                speaker=speaker,
                text=text,
                confidence=1.0,
            )
        )
    return segments


def build_live_session_payload(
    session_row: dict[str, Any],
    event_rows: list[dict[str, Any]],
    config: AppConfig,
    visual_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    segments = _build_segments(event_rows)
    transcript_result = TranscriptResult(
        full_text=" ".join(segment.text for segment in segments).strip(),
        segments=segments,
        speaker_directory=[{"speaker": speaker} for speaker in sorted({segment.speaker for segment in segments})],
    )
    speaker_result = speaker_dominance.run(transcript_result.segments, config, video_path=None)
    decision_events, action_events, blocker_events = _extract_structured_moments(transcript_result.segments)
    visual_rows = visual_rows or []
    visual_artifacts = []
    workflow_model = _build_workflow_model(transcript_result.segments, decision_events, action_events, blocker_events)
    attention_result = _build_attention_sentiment(transcript_result.segments, speaker_result, blocker_events)
    meeting_scores = _build_meeting_scores(
        transcript_result,
        speaker_result,
        decision_events,
        action_events,
        blocker_events,
        attention_result,
    )
    live_structure, live_source = _merge_gemini_structure(
        transcript_result,
        decision_events,
        action_events,
        blocker_events,
        workflow_model,
        config,
    )
    visual_summaries = [
        str(row.get("summary") or row.get("textual_content") or row.get("artifact_type") or "").strip()
        for row in visual_rows
        if str(row.get("summary") or row.get("textual_content") or row.get("artifact_type") or "").strip()
    ]
    if visual_summaries:
        combined_summary = str(live_structure.get("summary") or "").strip()
        visual_line = "Visual cues: " + "; ".join(visual_summaries[:4])
        live_structure["summary"] = "\n".join(part for part in [combined_summary, visual_line] if part)
        discussion_points = list(live_structure.get("discussion_points") or [])
        live_structure["discussion_points"] = (discussion_points + visual_summaries[:3])[:8]
    return {
        "session": {
            "id": int(session_row["id"]),
            "title": str(session_row.get("title") or f"Live Session {session_row['id']}"),
            "status": str(session_row.get("status") or "active"),
            "started_at": str(session_row.get("started_at") or ""),
            "updated_at": str(session_row.get("updated_at") or ""),
            "finalized_at": str(session_row.get("finalized_at") or ""),
            "username": str(session_row.get("username") or ""),
            "event_count": len(event_rows),
            "speaker_count": len(speaker_result.speakers),
            "runtime_profile": "boardsight-live-copilot-v1",
        },
        "transcript": {
            "full_text": transcript_result.full_text,
            "segments": [
                {
                    "start": segment.start,
                    "end": segment.end,
                    "timestamp": _seconds_to_timestamp(segment.start),
                    "speaker": segment.speaker,
                    "text": segment.text,
                }
                for segment in transcript_result.segments
            ],
        },
        "speaker_dominance": {
            "speakers": speaker_result.speakers,
            "active_speaker_timeline": speaker_result.active_speaker_timeline,
        },
        "decision_moments": [
            {
                "event_id": item.event_id,
                "timestamp": item.timestamp,
                "speaker": item.speaker,
                "text": item.text,
                "label": item.label,
                "confidence": item.confidence,
            }
            for item in (decision_events + action_events + blocker_events)
        ],
        "workflow_model": {
            "stages": workflow_model.stages,
            "bottlenecks": workflow_model.bottlenecks,
            "prioritized_decisions": workflow_model.prioritized_decisions,
            "execution_plan": workflow_model.execution_plan,
        },
        "attention_sentiment": {
            "overall_attention": attention_result.overall_attention,
            "overall_sentiment": attention_result.overall_sentiment,
            "engagement_timeline": attention_result.engagement_timeline,
        },
        "meeting_scores": {
            "impact_score": meeting_scores.impact_score,
            "productivity_score": meeting_scores.productivity_score,
            "execution_readiness": meeting_scores.execution_readiness,
            "meeting_conclusion": meeting_scores.meeting_conclusion,
        },
        "copilot_context": {
            "summary": live_structure.get("summary", ""),
            "discussion_points": live_structure.get("discussion_points", []),
            "decisions": live_structure.get("decisions", []),
            "action_items": live_structure.get("action_items", []),
            "blockers": live_structure.get("blockers", []),
            "outcomes": live_structure.get("outcomes", []),
            "source": live_source,
        },
        "live_visual_cues": [
            {
                "artifact_id": str(row.get("id") or f"LV-{index + 1}"),
                "start_time": float(row.get("timestamp_seconds") or 0.0),
                "end_time": float(row.get("timestamp_seconds") or 0.0),
                "artifact_type": str(row.get("artifact_type") or ""),
                "display_mode": str(row.get("display_mode") or ""),
                "content_summary": str(row.get("summary") or row.get("textual_content") or ""),
                "visible_people_count": int(row.get("visible_people_count") or 0),
                "screen_present": bool(row.get("screen_present")),
                "chart_present": bool(row.get("chart_present")),
                "document_present": bool(row.get("document_present")),
            }
            for index, row in enumerate(visual_rows)
        ],
    }


def _late_join_cutoff_seconds(question: str) -> float | None:
    match = re.search(r"(\d+)\s*minute(?:s)?\s+late", question.lower())
    if match:
        return float(match.group(1)) * 60.0
    return None


def _heuristic_live_answer(payload: dict[str, Any], question: str) -> str:
    lower_question = question.lower()
    context = payload["copilot_context"]
    transcript_segments = payload["transcript"]["segments"]
    if not transcript_segments:
        return "I do not have any live transcript yet. Start the session and let BoardSight capture notes or speech first."

    cutoff_seconds = _late_join_cutoff_seconds(question)
    if "before i joined" in lower_question and cutoff_seconds is not None:
        earlier_segments = [segment for segment in transcript_segments if float(segment["start"]) <= cutoff_seconds]
        if not earlier_segments:
            return "I do not have enough transcript before that join point yet."
        ordered = earlier_segments[:8]
        bullet_lines = [
            f"- {item['timestamp']} {item['speaker']}: {item['text']}"
            for item in ordered
        ]
        return "Before you joined, this is what had already been discussed:\n" + "\n".join(bullet_lines)

    if "decision" in lower_question:
        decisions = context.get("decisions", [])
        if decisions:
            return "Decisions so far:\n" + "\n".join(f"- {item}" for item in decisions[:6])
        return "No explicit decisions have been detected in the live transcript so far."

    if "action" in lower_question or "to do" in lower_question or "todo" in lower_question:
        action_items = context.get("action_items", [])
        if action_items:
            return "Action items so far:\n" + "\n".join(f"- {item}" for item in action_items[:6])
        return "No explicit action items have been detected in the live transcript so far."

    if "blocker" in lower_question or "risk" in lower_question:
        blockers = context.get("blockers", [])
        if blockers:
            return "Risks or blockers so far:\n" + "\n".join(f"- {item}" for item in blockers[:6])
        return "No clear blockers or risks have been detected in the live transcript so far."

    if "screen" in lower_question or "visual" in lower_question or "slide" in lower_question or "camera" in lower_question:
        visual_cues = payload.get("live_visual_cues", [])
        if visual_cues:
            return "Recent visual cues:\n" + "\n".join(
                f"- {_seconds_to_timestamp(float(item.get('start_time') or 0.0))}: {item.get('artifact_type', 'unknown')} ({item.get('display_mode', 'unknown')}) - {item.get('content_summary', '')}"
                for item in visual_cues[-5:]
            )
        return "No live visual cues have been captured yet."

    if "what happened" in lower_question or "summary" in lower_question or "so far" in lower_question:
        summary = str(context.get("summary") or "").strip()
        if summary:
            extras: list[str] = []
            if context.get("decisions"):
                extras.append("Decisions: " + "; ".join(context["decisions"][:3]))
            if context.get("action_items"):
                extras.append("Action items: " + "; ".join(context["action_items"][:3]))
            if context.get("blockers"):
                extras.append("Blockers: " + "; ".join(context["blockers"][:3]))
            return "\n".join([summary] + extras)

    latest_segments = transcript_segments[-5:]
    return "I can answer from the live transcript so far. Recent discussion:\n" + "\n".join(
        f"- {item['timestamp']} {item['speaker']}: {item['text']}" for item in latest_segments
    )


def answer_live_copilot(payload: dict[str, Any], question: str, config: AppConfig) -> tuple[str, str]:
    transcript_segments = payload["transcript"]["segments"]
    transcript_excerpt = "\n".join(
        f"{item['timestamp']} | {item['speaker']}: {item['text']}"
        for item in transcript_segments[-80:]
    )
    structured = payload["copilot_context"]
    prompt = (
        "You are BoardSight Live Copilot.\n"
        "Answer only from the live meeting transcript and structured signals provided below.\n"
        "If the user joined late, summarize what had happened before their join point if it can be inferred.\n"
        "Be concise, concrete, and grounded. Prefer bullets when listing decisions, action items, or blockers.\n"
        "If the transcript does not support the answer, say that clearly.\n\n"
        f"Live summary: {structured.get('summary', '')}\n"
        f"Discussion points: {structured.get('discussion_points', [])}\n"
        f"Decisions: {structured.get('decisions', [])}\n"
        f"Action items: {structured.get('action_items', [])}\n"
        f"Blockers: {structured.get('blockers', [])}\n"
        f"Outcomes: {structured.get('outcomes', [])}\n\n"
        f"Live visual cues: {payload.get('live_visual_cues', [])}\n\n"
        f"Transcript so far:\n{transcript_excerpt}\n\n"
        f"User question: {question}"
    )
    answer, source = answer_question(prompt, config)
    if source.startswith("gemini:") and answer.strip():
        return answer.strip(), source
    return _heuristic_live_answer(payload, question), "live-heuristic"
