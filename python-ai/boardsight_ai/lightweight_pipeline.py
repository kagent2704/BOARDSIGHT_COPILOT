from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter
from typing import Any

from boardsight_ai.config import AppConfig
from boardsight_ai.features import decision_trace, speaker_dominance, speaker_labeling
from boardsight_ai.models import (
    AttentionSentimentResult,
    DecisionMoment,
    MeetingScores,
    PipelineResult,
    TranscriptSegment,
    VisualArtifact,
    WorkflowModel,
)
from boardsight_ai.providers.llm import generate_structured_json, summarize
from boardsight_ai.providers.media import probe_video
from boardsight_ai.providers.speech import transcribe
from boardsight_ai.providers.vision import analyze_sparse_frame, safe_open_video


STOPWORDS = {
    "the", "and", "for", "that", "with", "from", "this", "have", "will", "into", "about", "there",
    "their", "they", "your", "what", "when", "which", "would", "could", "should", "after", "before",
    "meeting", "board", "today", "need", "just", "than", "then", "been", "were", "them", "also",
    "because", "where", "while", "through", "across", "under", "over", "into", "onto", "between",
}

DECISION_KEYWORDS = (
    "approved", "agreed", "decided", "decision", "resolved", "confirmed", "adopted", "accepted",
)
ACTION_KEYWORDS = (
    "will", "should", "needs to", "need to", "action item", "follow up", "follow-up", "prepare",
    "send", "share", "complete", "deliver", "review", "update", "create",
)
BLOCKER_KEYWORDS = (
    "blocker", "blocked", "risk", "issue", "concern", "delay", "dependency", "pending", "unclear",
    "problem", "stuck",
)
VISUAL_KEYWORDS = {
    "slide": "presentation-slide",
    "slides": "presentation-slide",
    "screen": "screen-share",
    "dashboard": "dashboard",
    "chart": "chart",
    "graph": "chart",
    "report": "document",
    "document": "document",
    "spreadsheet": "document",
}


def _seconds_to_timestamp(value: float) -> str:
    minutes = int(value // 60)
    seconds = int(value % 60)
    return f"{minutes:02d}:{seconds:02d}"


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").split())


def _topic_candidates(text: str, limit: int = 6) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", text.lower())
    counts = Counter(token for token in tokens if token not in STOPWORDS)
    return [token for token, _ in counts.most_common(limit)]


def _segment_matches(segment: TranscriptSegment, keywords: tuple[str, ...]) -> bool:
    text = segment.text.lower()
    return any(keyword in text for keyword in keywords)


def _dedupe_moments(items: list[DecisionMoment]) -> list[DecisionMoment]:
    seen: set[tuple[str, str]] = set()
    output: list[DecisionMoment] = []
    for item in items:
        key = (item.speaker, _normalize_text(item.text).lower())
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _extract_structured_moments(transcript_segments: list[TranscriptSegment]) -> tuple[list[DecisionMoment], list[DecisionMoment], list[DecisionMoment]]:
    decisions: list[DecisionMoment] = []
    actions: list[DecisionMoment] = []
    blockers: list[DecisionMoment] = []

    for segment in transcript_segments:
        text = _normalize_text(segment.text)
        if not text:
            continue
        timestamp = _seconds_to_timestamp(segment.start)
        if _segment_matches(segment, DECISION_KEYWORDS):
            decisions.append(
                DecisionMoment(
                    event_id=f"DM-{len(decisions) + 1}",
                    timestamp=timestamp,
                    speaker=segment.speaker,
                    text=text,
                    confidence=0.72,
                    label="decision",
                    evidence=["transcript-keywords:decision"],
                )
            )
        if _segment_matches(segment, ACTION_KEYWORDS):
            actions.append(
                DecisionMoment(
                    event_id=f"AI-{len(actions) + 1}",
                    timestamp=timestamp,
                    speaker=segment.speaker,
                    text=text,
                    confidence=0.68,
                    label="action",
                    evidence=["transcript-keywords:action"],
                )
            )
        if _segment_matches(segment, BLOCKER_KEYWORDS):
            blockers.append(
                DecisionMoment(
                    event_id=f"BL-{len(blockers) + 1}",
                    timestamp=timestamp,
                    speaker=segment.speaker,
                    text=text,
                    confidence=0.66,
                    label="blocker",
                    evidence=["transcript-keywords:blocker"],
                )
            )

    return _dedupe_moments(decisions), _dedupe_moments(actions), _dedupe_moments(blockers)


def _build_frame_sample_schedule(
    duration_seconds: float,
    transcript_segments: list[TranscriptSegment],
    config: AppConfig,
) -> list[float]:
    timestamps: set[float] = set()
    cursor = 0.0
    while cursor <= duration_seconds:
        timestamps.add(round(cursor, 2))
        cursor += max(8.0, float(config.lightweight_visual_gap_seconds))

    for segment in transcript_segments:
        if _segment_matches(segment, tuple(VISUAL_KEYWORDS.keys())):
            timestamps.add(round(max(0.0, segment.start), 2))

    return sorted(timestamps)[: max(4, config.lightweight_max_evidence_segments)]


def _extract_visual_artifacts(video_path: Path, transcript_segments: list[TranscriptSegment], config: AppConfig) -> list[VisualArtifact]:
    artifacts: list[VisualArtifact] = []
    probe = probe_video(video_path)
    duration_seconds = float(probe.get("duration_sec") or 0.0)
    cap, cv2 = safe_open_video(video_path)
    if cap is None or cv2 is None or duration_seconds <= 0.0:
        return artifacts

    fps = float(probe.get("fps") or 0.0) or 25.0
    sample_timestamps = _build_frame_sample_schedule(duration_seconds, transcript_segments, config)
    for timestamp in sample_timestamps:
        frame_index = max(0, int(timestamp * fps))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue

        analysis = analyze_sparse_frame(frame, config)
        artifact_type = str(analysis.get("artifact_type") or "none")
        visible_people_count = int(analysis.get("visible_people_count") or 0)
        if artifact_type == "none" and visible_people_count <= 0:
            continue

        nearby_segments = [
            segment
            for segment in transcript_segments
            if abs(float(segment.start) - float(timestamp)) <= float(config.lightweight_visual_window_seconds)
        ]
        nearby_text = " ".join(_normalize_text(segment.text) for segment in nearby_segments if segment.text)
        artifact_id = f"VA-{len(artifacts) + 1}"
        summary = _normalize_text(str(analysis.get("summary") or "")) or nearby_text[:180]
        content_text = _normalize_text(str(analysis.get("textual_content") or "")) or nearby_text[:300]
        content_insight_parts = []
        if visible_people_count > 0:
            content_insight_parts.append(f"{visible_people_count} visible participant(s)")
        if analysis.get("screen_present"):
            content_insight_parts.append("screen content visible")
        if analysis.get("chart_present"):
            content_insight_parts.append("chart or dashboard cues detected")
        if analysis.get("document_present"):
            content_insight_parts.append("document-like surface detected")
        if nearby_text:
            content_insight_parts.append(f"nearby transcript: {nearby_text[:160]}")

        artifacts.append(
            VisualArtifact(
                artifact_id=artifact_id,
                start_time=round(max(0.0, timestamp - 2.0), 2),
                end_time=round(min(duration_seconds, timestamp + config.lightweight_visual_window_seconds), 2),
                artifact_type=artifact_type,
                confidence=round(float(analysis.get("confidence") or 0.0), 3),
                detections=list(analysis.get("detections") or []),
                display_mode=str(analysis.get("display_mode") or ""),
                content_summary=summary,
                content_text=content_text,
                content_insight="; ".join(content_insight_parts),
            )
        )

    cap.release()
    return artifacts


def _build_workflow_model(
    transcript_segments: list[TranscriptSegment],
    decision_events: list[DecisionMoment],
    action_events: list[DecisionMoment],
    blocker_events: list[DecisionMoment],
) -> WorkflowModel:
    if not transcript_segments:
        return WorkflowModel(
            stages=[],
            transitions=[],
            bottlenecks=[],
            prioritized_decisions=[],
            execution_plan=[],
            workflow_summary={"status": "empty-transcript"},
        )

    total_segments = max(1, len(transcript_segments))
    stage_names = ["opening", "discussion", "decision", "execution-close"]
    stage_slots = {
        "opening": transcript_segments[: max(1, total_segments // 5)],
        "discussion": transcript_segments[max(1, total_segments // 5): max(2, (total_segments * 3) // 5)],
        "decision": transcript_segments[max(2, (total_segments * 3) // 5): max(3, (total_segments * 4) // 5)],
        "execution-close": transcript_segments[max(3, (total_segments * 4) // 5):],
    }

    stages: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    previous = None
    for index, stage_name in enumerate(stage_names, start=1):
        bucket = stage_slots.get(stage_name, [])
        if not bucket:
            continue
        anchor = bucket[0]
        stage = {
            "timestamp": round(anchor.start, 2),
            "stage": stage_name,
            "speaker": anchor.speaker,
            "summary": _normalize_text(anchor.text)[:120],
            "confidence": 0.7,
            "source": "transcript-phase-segmentation",
        }
        stages.append(stage)
        if previous is not None:
            transitions.append({"from": previous, "to": stage_name, "speaker": anchor.speaker})
        previous = stage_name

    prioritized_decisions: list[dict[str, Any]] = []
    execution_plan: list[dict[str, Any]] = []
    blocker_lookup = " ".join(item.text.lower() for item in blocker_events)

    for rank, item in enumerate(decision_events + action_events, start=1):
        owner = item.speaker or "Unassigned"
        owner_bonus = 8.0 if owner and owner.lower() != "unknown speaker" else 0.0
        blocker_penalty = 12.0 if any(word in blocker_lookup for word in item.text.lower().split()) else 0.0
        base_score = 58.0 if item.label == "decision" else 52.0
        priority_score = round(min(95.0, max(20.0, base_score + owner_bonus - blocker_penalty + rank)), 2)
        prioritized_decisions.append(
            {
                "decision_id": item.event_id,
                "label": item.label,
                "speaker": owner,
                "priority_score": priority_score,
                "execution_rank": rank,
                "reasoning": item.evidence + ["lightweight-priority-scorer"],
                "text": item.text,
                "artifact_support": [],
            }
        )
        execution_plan.append(
            {
                "task_id": f"{item.event_id}-T1",
                "decision_id": item.event_id,
                "title": item.text[:110],
                "owner": owner,
                "priority_score": priority_score,
                "execution_order": rank,
                "task_type": "action-followthrough" if item.label == "action" else "decision-followthrough",
                "notes": "Generated from the lightweight multimodal BoardSight pipeline.",
            }
        )

    bottlenecks = [_normalize_text(item.text)[:140] for item in blocker_events[:5]]
    workflow_summary = {
        "total_stages": len(stages),
        "total_decisions": len(decision_events),
        "total_execution_tasks": len(execution_plan),
        "top_priority_decision": prioritized_decisions[0]["decision_id"] if prioritized_decisions else "None",
        "source": "lightweight-multimodal-workflow",
    }
    return WorkflowModel(stages, transitions, bottlenecks, prioritized_decisions, execution_plan, workflow_summary)


def _build_attention_sentiment(
    transcript_segments: list[TranscriptSegment],
    speaker_result,
    blocker_events: list[DecisionMoment],
) -> AttentionSentimentResult:
    engagement_timeline: list[dict[str, Any]] = []
    speaker_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"samples": 0, "attention_total": 0.0})
    total_segments = max(1, len(transcript_segments))
    distinct_speakers = max(1, len(speaker_result.speakers))
    cadence_bonus = min(18.0, total_segments * 1.4)
    participation_bonus = min(16.0, distinct_speakers * 4.0)
    blocker_penalty = min(22.0, len(blocker_events) * 6.0)
    overall_attention = round(max(22.0, min(92.0, 42.0 + cadence_bonus + participation_bonus - blocker_penalty)), 2)

    for segment in transcript_segments:
        text = segment.text.lower()
        score = overall_attention
        if any(keyword in text for keyword in BLOCKER_KEYWORDS):
            score = max(20.0, score - 12.0)
        elif any(keyword in text for keyword in DECISION_KEYWORDS + ACTION_KEYWORDS):
            score = min(95.0, score + 6.0)
        score = round(score, 2)
        engagement_timeline.append(
            {
                "timestamp": round(segment.start, 2),
                "speaker": segment.speaker,
                "attention_score": score,
                "attention_label": "meeting-engagement-lite",
                "emotion": "focused",
                "source": "multimodal-engagement-lite",
            }
        )
        speaker_stats[segment.speaker]["samples"] += 1
        speaker_stats[segment.speaker]["attention_total"] += score

    overall_sentiment = "neutral"
    if blocker_penalty >= 18.0:
        overall_sentiment = "negative"
    elif len(transcript_segments) >= 5 and (distinct_speakers >= 2 or cadence_bonus >= 10):
        overall_sentiment = "positive"

    participant_states = [
        {
            "speaker": speaker,
            "samples": stats["samples"],
            "average_attention": round(stats["attention_total"] / max(1, stats["samples"]), 2),
            "dominant_emotion": "focused",
            "peak_confidence": 0.58,
        }
        for speaker, stats in sorted(speaker_stats.items(), key=lambda item: item[1]["attention_total"], reverse=True)
    ]

    return AttentionSentimentResult(
        overall_attention=overall_attention,
        overall_sentiment=overall_sentiment,
        engagement_timeline=engagement_timeline,
        sentiment_timeline=[],
        cognitive_rating={
            "focus": overall_attention,
            "clarity": round(max(28.0, min(94.0, 60.0 + len(transcript_segments) * 0.8 - len(blocker_events) * 5.0)), 2),
            "overload_risk": round(max(5.0, 100.0 - overall_attention), 2),
        },
        participant_states=participant_states,
        model_sources=["multimodal-engagement-lite"],
        coverage_ratio=1.0 if transcript_segments else 0.0,
    )


def _build_meeting_scores(
    transcript_result,
    speaker_result,
    decision_events: list[DecisionMoment],
    action_events: list[DecisionMoment],
    blocker_events: list[DecisionMoment],
    attention_result: AttentionSentimentResult,
) -> MeetingScores:
    ownership_ratio = (
        sum(1 for item in action_events if item.speaker and item.speaker.lower() != "unknown speaker")
        / max(1, len(action_events))
    )
    impact_score = round(min(95.0, 34.0 + len(decision_events) * 14.0 + len(action_events) * 7.0), 2)
    productivity_score = round(max(18.0, min(94.0, 38.0 + ownership_ratio * 28.0 + len(action_events) * 6.0 - len(blocker_events) * 8.0)), 2)
    execution_readiness = round(max(15.0, min(93.0, 42.0 + ownership_ratio * 30.0 + len(action_events) * 5.0 - len(blocker_events) * 7.0)), 2)
    speaker_rating = {
        item["speaker"]: round(float(item.get("dominance_ratio", 0.0)), 2)
        for item in speaker_result.speakers
    }
    cognitive_rating = {
        "meeting_focus": attention_result.cognitive_rating["focus"],
        "meeting_clarity": attention_result.cognitive_rating["clarity"],
        "overload_risk": attention_result.cognitive_rating["overload_risk"],
        "source": ",".join(attention_result.model_sources) or "lightweight-multimodal-lite",
    }
    conclusion = (
        f"Lightweight meeting assessment: {len(decision_events)} decisions, "
        f"{len(action_events)} action items, {len(blocker_events)} blockers, "
        f"ownership coverage {round(ownership_ratio * 100.0, 1)}%."
    )
    return MeetingScores(
        impact_score=impact_score,
        productivity_score=productivity_score,
        execution_readiness=execution_readiness,
        speaker_rating=speaker_rating,
        cognitive_rating=cognitive_rating,
        meeting_conclusion=conclusion,
    )


def _build_gemini_prompt(transcript_result, decision_events: list[DecisionMoment], action_events: list[DecisionMoment], blocker_events: list[DecisionMoment]) -> str:
    transcript_excerpt = "\n".join(
        f"{_seconds_to_timestamp(segment.start)} | {segment.speaker}: {_normalize_text(segment.text)}"
        for segment in transcript_result.segments[:120]
    )
    return (
        "You are helping BoardSight structure a meeting analysis.\n"
        "Return valid JSON with these top-level keys only: summary, discussion_points, decisions, action_items, blockers, outcomes.\n"
        "Each of decisions, action_items, blockers should be an array of short strings.\n"
        "discussion_points and outcomes should also be arrays of short strings.\n"
        "Use the transcript and the preliminary signals below, but keep the answer faithful to the source text.\n\n"
        f"Preliminary decisions: {[item.text for item in decision_events[:8]]}\n"
        f"Preliminary action items: {[item.text for item in action_events[:8]]}\n"
        f"Preliminary blockers: {[item.text for item in blocker_events[:8]]}\n\n"
        f"Transcript:\n{transcript_excerpt}"
    )


def _merge_unique_strings(primary: list[Any], fallback: list[Any], *, limit: int) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for bucket in (primary, fallback):
        for item in bucket:
            text = _normalize_text(str(item or ""))
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(text)
            if len(merged) >= limit:
                return merged
    return merged


def _merge_gemini_structure(
    transcript_result,
    decision_events: list[DecisionMoment],
    action_events: list[DecisionMoment],
    blocker_events: list[DecisionMoment],
    workflow_model: WorkflowModel,
    config: AppConfig,
) -> tuple[dict[str, Any], str]:
    parsed, source = generate_structured_json(
        _build_gemini_prompt(transcript_result, decision_events, action_events, blocker_events),
        config,
    )
    if not isinstance(parsed, dict):
        summary, summary_source = summarize(transcript_result.full_text[:4000], config)
        return {
            "summary": summary,
            "discussion_points": _topic_candidates(transcript_result.full_text),
            "decisions": [item.text for item in decision_events[:6]],
            "action_items": [item.text for item in action_events[:6]],
            "blockers": [item.text for item in blocker_events[:6]],
            "outcomes": [task["title"] for task in workflow_model.execution_plan[:4]],
        }, summary_source

    heuristic_summary, heuristic_summary_source = summarize(transcript_result.full_text[:4000], config)
    fallback_discussion_points = _topic_candidates(transcript_result.full_text)
    fallback_decisions = [item.text for item in decision_events[:6]]
    fallback_actions = [item.text for item in action_events[:6]]
    fallback_blockers = [item.text for item in blocker_events[:6]]
    fallback_outcomes = [task["title"] for task in workflow_model.execution_plan[:4]]

    summary_text = _normalize_text(str(parsed.get("summary") or ""))
    if not summary_text:
        summary_text = heuristic_summary
        source = heuristic_summary_source

    merged = {
        "summary": summary_text,
        "discussion_points": _merge_unique_strings(
            parsed.get("discussion_points", []),
            fallback_discussion_points,
            limit=8,
        ),
        "decisions": _merge_unique_strings(parsed.get("decisions", []), fallback_decisions, limit=8),
        "action_items": _merge_unique_strings(parsed.get("action_items", []), fallback_actions, limit=8),
        "blockers": _merge_unique_strings(parsed.get("blockers", []), fallback_blockers, limit=8),
        "outcomes": _merge_unique_strings(parsed.get("outcomes", []), fallback_outcomes, limit=8),
    }
    return merged, source


def run_lightweight_pipeline(
    video_path: Path,
    output_dir: Path,
    config: AppConfig,
    analysis_range: dict[str, float | None] | None = None,
    requested_profile: str | None = None,
) -> PipelineResult:
    warnings: list[str] = []
    timings: dict[str, float] = {}

    def timed(stage_name: str, func):
        started = perf_counter()
        value = func()
        timings[stage_name] = round(perf_counter() - started, 4)
        return value

    transcript_segments, transcript_warnings = timed("transcription", lambda: transcribe(video_path, config))
    warnings.extend(transcript_warnings)
    transcript_result = timed("speaker_labeling", lambda: speaker_labeling.run(transcript_segments, config))
    speaker_result = timed("speaker_dominance", lambda: speaker_dominance.run(transcript_result.segments, config, video_path=None))
    decision_events, action_events, blocker_events = timed(
        "structured_extraction",
        lambda: _extract_structured_moments(transcript_result.segments),
    )
    visual_result = timed("visual_evidence", lambda: _extract_visual_artifacts(transcript_result.segments, config))
    workflow_result = timed(
        "workflow_model",
        lambda: _build_workflow_model(transcript_result.segments, decision_events, action_events, blocker_events),
    )
    attention_result = timed(
        "engagement_scoring",
        lambda: _build_attention_sentiment(transcript_result.segments, speaker_result, blocker_events),
    )
    meeting_scores = timed(
        "meeting_scores",
        lambda: _build_meeting_scores(
            transcript_result,
            speaker_result,
            decision_events,
            action_events,
            blocker_events,
            attention_result,
        ),
    )
    llm_structure, llm_source = timed(
        "llm_structuring",
        lambda: _merge_gemini_structure(
            transcript_result,
            decision_events,
            action_events,
            blocker_events,
            workflow_result,
            config,
        ),
    )
    trace_result = timed(
        "decision_traces",
        lambda: decision_trace.run(
            transcript_result.segments,
            decision_events,
            visual_result,
            workflow_result,
            config,
        ),
    )

    effective_profile = "boardsight-production-lightweight-v1"
    requested_profile_text = (requested_profile or config.analysis_profile or "production").strip().lower()
    compatibility_warning = ""
    if requested_profile_text in {"recorded-deep", "deep", "full-model-stack"}:
        compatibility_warning = (
            "Legacy deep-analysis requests are now routed to the production lightweight pipeline."
        )
        warnings.append(compatibility_warning)

    metadata = {
        "data_contract_version": "boardsight-result-v2",
        "storage_schema_version": "meetings-v2",
        "requested_analysis_profile": requested_profile_text,
        "effective_analysis_profile": effective_profile,
        "video_probe": probe_video(video_path),
        "analysis_range": analysis_range or {
            "start_seconds": None,
            "end_seconds": None,
            "duration_seconds": None,
            "mode": "full-video",
        },
        "feature_flags": {
            "speaker_dominance": True,
            "decision_moment_detection": True,
            "visual_artifact_logging": True,
            "workflow_engine_modelling": True,
            "decision_trace_generation": True,
            "attention_sentiment": True,
            "speaker_labeling": True,
        },
        "performance_report": {
            "stage_timings_seconds": timings,
            "sampling_limits": {
                "lightweight_visual_window_seconds": config.lightweight_visual_window_seconds,
                "lightweight_visual_gap_seconds": config.lightweight_visual_gap_seconds,
                "lightweight_max_evidence_segments": config.lightweight_max_evidence_segments,
                "faster_whisper_model": config.faster_whisper_model,
                "enable_diarization": config.enable_diarization,
            },
            "target_accuracy_range": "lightweight multimodal mode",
            "runtime_profile": effective_profile,
            "current_status": {
                "transcript_generation": "ASR model-backed speech analysis",
                "speaker_dominance": "audio-duration backed with sampled visual identity enrichment and no mandatory face-recognition dependency",
                "visual_artifact_logging": "sparse sampled-frame analysis with Gemini vision or OpenCV/YOLO fallback",
                "decision_moment_detection": "speech-driven extraction with optional Gemini refinement",
                "decision_trace_generation": llm_source,
                "attention_sentiment": ",".join(attention_result.model_sources),
                "workflow_engine": "meeting-phase segmentation and action-plan generation",
            },
            "no_heuristics_policy": "Production runtime uses lightweight speech plus sparse visual evidence and optional Gemini reasoning instead of the legacy dense local stack.",
        },
        "presentation_insights": {
            "summary": str(llm_structure.get("summary") or "No presentation-specific summary was generated."),
            "summary_source": llm_source,
            "visual_window_count": len(visual_result),
            "artifact_types": dict(Counter(item.artifact_type for item in visual_result)),
            "evidence": [
                {
                    "artifact_id": item.artifact_id,
                    "time_range": {"start_seconds": item.start_time, "end_seconds": item.end_time},
                    "artifact_type": item.artifact_type,
                    "display_mode": item.display_mode,
                    "content_text": item.content_text,
                    "content_insight": item.content_insight,
                    "nearby_transcript": item.content_summary,
                }
                for item in visual_result[:8]
            ],
        },
        "lightweight_structured_outputs": {
            "summary": llm_structure.get("summary", ""),
            "discussion_points": llm_structure.get("discussion_points", []),
            "decisions": llm_structure.get("decisions", []),
            "action_items": llm_structure.get("action_items", []),
            "blockers": llm_structure.get("blockers", []),
            "outcomes": llm_structure.get("outcomes", []),
        },
        "pipeline_notes": [compatibility_warning] if compatibility_warning else [],
    }

    combined_decisions = decision_events + action_events
    return PipelineResult(
        input_video=str(video_path),
        transcript=transcript_result,
        speaker_dominance=speaker_result,
        decision_moments=combined_decisions,
        visual_artifacts=visual_result,
        workflow_model=workflow_result,
        decision_traces=trace_result,
        attention_sentiment=attention_result,
        meeting_scores=meeting_scores,
        warnings=warnings,
        metadata=metadata,
    )
