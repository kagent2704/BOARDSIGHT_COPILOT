from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from boardsight_ai.agentic_contract import build_agentic_contract
from boardsight_ai.config import AppConfig
from boardsight_ai.features import attention_sentiment, decision_moments, decision_trace, scoring, visual_artifacts, workflow_engine
from boardsight_ai.models import AttentionSentimentResult, SpeakerDominanceResult, TranscriptResult, TranscriptSegment, WorkflowModel
from boardsight_ai.pipeline import _build_presentation_insights
from boardsight_ai.providers.llm import generate_text
from boardsight_ai.providers.speech import transcribe


PROBLEM_LABELS = [
    "blocker or problem",
    "risk or concern",
    "dependency or waiting point",
    "decision or approval",
    "routine discussion",
]


def _classifier(model_name: str):
    from boardsight_ai.providers.runtime import optional_import

    transformers = optional_import("transformers")
    if transformers is None:
        return None
    try:
        return transformers.pipeline("zero-shot-classification", model=model_name)
    except Exception:
        return None


def _classify_texts(texts: list[str], labels: list[str], config: AppConfig) -> list[tuple[str, float] | None]:
    classifier = _classifier(config.text_classifier_model)
    if classifier is None:
        return [None for _ in texts]
    try:
        outputs = classifier(texts, labels, multi_label=False, batch_size=8)
    except Exception:
        return [None for _ in texts]
    if isinstance(outputs, dict):
        outputs = [outputs]
    results: list[tuple[str, float] | None] = []
    for output in outputs:
        output_labels = output.get("labels", []) if isinstance(output, dict) else []
        scores = output.get("scores", []) if isinstance(output, dict) else []
        results.append((str(output_labels[0]), float(scores[0])) if output_labels and scores else None)
    return results


def _segments_to_transcript_result(segments: list[TranscriptSegment]) -> TranscriptResult:
    speaker_directory = [{"speaker": speaker, "label": speaker} for speaker in sorted({segment.speaker for segment in segments})]
    full_text = "\n".join(
        f"[{segment.start:.1f}-{segment.end:.1f}] {segment.speaker}: {segment.text}"
        for segment in segments
    )
    return TranscriptResult(full_text=full_text, segments=segments, speaker_directory=speaker_directory)


def _empty_attention_result() -> AttentionSentimentResult:
    return AttentionSentimentResult(
        overall_attention=0.0,
        overall_sentiment="unavailable",
        engagement_timeline=[],
        sentiment_timeline=[],
        cognitive_rating={"focus": 0.0, "clarity": 0.0, "overload_risk": 0.0},
        participant_states=[],
        model_sources=[],
        coverage_ratio=0.0,
    )


def _attention_to_dict(result: AttentionSentimentResult) -> dict[str, Any]:
    return {
        "overall_attention": result.overall_attention,
        "overall_sentiment": result.overall_sentiment,
        "engagement_timeline": result.engagement_timeline,
        "sentiment_timeline": result.sentiment_timeline,
        "cognitive_rating": result.cognitive_rating,
        "participant_states": result.participant_states,
        "model_sources": result.model_sources,
        "coverage_ratio": result.coverage_ratio,
    }


def _attention_from_dict(payload: dict[str, Any] | None) -> AttentionSentimentResult:
    payload = payload or {}
    return AttentionSentimentResult(
        overall_attention=float(payload.get("overall_attention", 0.0) or 0.0),
        overall_sentiment=str(payload.get("overall_sentiment", "unavailable") or "unavailable"),
        engagement_timeline=list(payload.get("engagement_timeline", []) or []),
        sentiment_timeline=list(payload.get("sentiment_timeline", []) or []),
        cognitive_rating=dict(payload.get("cognitive_rating", {"focus": 0.0, "clarity": 0.0, "overload_risk": 0.0}) or {"focus": 0.0, "clarity": 0.0, "overload_risk": 0.0}),
        participant_states=list(payload.get("participant_states", []) or []),
        model_sources=list(payload.get("model_sources", []) or []),
        coverage_ratio=float(payload.get("coverage_ratio", 0.0) or 0.0),
    )


def _merge_attention(existing: AttentionSentimentResult, new: AttentionSentimentResult) -> AttentionSentimentResult:
    engagement = [*existing.engagement_timeline, *new.engagement_timeline]
    sentiment = [*existing.sentiment_timeline, *new.sentiment_timeline]
    participant_states = [*existing.participant_states]
    seen = {item.get("speaker"): item for item in participant_states}
    for item in new.participant_states:
        speaker = item.get("speaker")
        if speaker in seen:
            prior = seen[speaker]
            total_samples = int(prior.get("samples", 0)) + int(item.get("samples", 0))
            if total_samples > 0:
                merged_attention = (
                    float(prior.get("average_attention", 0.0)) * int(prior.get("samples", 0))
                    + float(item.get("average_attention", 0.0)) * int(item.get("samples", 0))
                ) / total_samples
            else:
                merged_attention = float(item.get("average_attention", 0.0))
            prior["samples"] = total_samples
            prior["average_attention"] = round(merged_attention, 2)
            prior["dominant_emotion"] = item.get("dominant_emotion") or prior.get("dominant_emotion")
            prior["peak_confidence"] = max(float(prior.get("peak_confidence", 0.0)), float(item.get("peak_confidence", 0.0)))
        else:
            participant_states.append(dict(item))
            seen[speaker] = participant_states[-1]

    overall_attention = round(sum(item.get("attention_score", 0.0) for item in engagement) / max(1, len(engagement)), 2) if engagement else 0.0
    sentiment_counts: dict[str, int] = {}
    for item in sentiment:
        label = str(item.get("sentiment", "unavailable"))
        sentiment_counts[label] = sentiment_counts.get(label, 0) + 1
    overall_sentiment = max(sentiment_counts, key=sentiment_counts.get) if sentiment_counts else "unavailable"
    clarity = round(sum(float(item.get("confidence", 0.0)) for item in sentiment) / max(1, len(sentiment)) * 100.0, 2) if sentiment else 0.0
    coverage_ratio = max(existing.coverage_ratio, new.coverage_ratio)
    sources = list(dict.fromkeys([*existing.model_sources, *new.model_sources]))
    return AttentionSentimentResult(
        overall_attention=overall_attention,
        overall_sentiment=overall_sentiment,
        engagement_timeline=engagement,
        sentiment_timeline=sentiment,
        cognitive_rating={"focus": overall_attention, "clarity": clarity, "overload_risk": round(max(0.0, 100.0 - overall_attention), 2)},
        participant_states=participant_states,
        model_sources=sources,
        coverage_ratio=coverage_ratio,
    )


def _offset_visual_artifacts(artifacts, start_offset_seconds: float) -> list[dict[str, Any]]:
    adjusted = []
    for artifact in artifacts:
        payload = asdict(artifact)
        payload["start_time"] = round(start_offset_seconds + float(payload.get("start_time", 0.0) or 0.0), 2)
        payload["end_time"] = round(start_offset_seconds + float(payload.get("end_time", 0.0) or 0.0), 2)
        adjusted.append(payload)
    return adjusted


def analyze_live_chunk_media(
    chunk_path: Path,
    config: AppConfig,
    *,
    start_offset_seconds: float,
    transcript_segments: list[TranscriptSegment],
) -> dict[str, Any]:
    visual_result, visual_warnings = visual_artifacts.run(chunk_path, config)
    adjusted_visuals = _offset_visual_artifacts(visual_result, start_offset_seconds)
    attention_result = attention_sentiment.run(transcript_segments, config, chunk_path)
    adjusted_attention = _attention_to_dict(attention_result)
    for item in adjusted_attention["engagement_timeline"]:
        item["timestamp"] = round(start_offset_seconds + float(item.get("timestamp", 0.0) or 0.0), 2)
    for item in adjusted_attention["sentiment_timeline"]:
        item["timestamp"] = round(start_offset_seconds + float(item.get("timestamp", 0.0) or 0.0), 2)
    presentation_insights = _build_presentation_insights(transcript_segments, visual_result, config)
    return {
        "visual_artifacts": adjusted_visuals,
        "attention_sentiment": adjusted_attention,
        "presentation_insights": presentation_insights,
        "warnings": visual_warnings,
    }


def _empty_speaker_result(segments: list[TranscriptSegment]) -> SpeakerDominanceResult:
    durations: dict[str, float] = {}
    for segment in segments:
        durations[segment.speaker] = durations.get(segment.speaker, 0.0) + max(0.0, segment.end - segment.start)
    total = sum(durations.values()) or 1.0
    speakers = [
        {
            "speaker": speaker,
            "total_seconds": round(seconds, 2),
            "dominance_ratio": round((seconds / total) * 100.0, 2),
        }
        for speaker, seconds in sorted(durations.items(), key=lambda item: item[1], reverse=True)
    ]
    return SpeakerDominanceResult(speakers=speakers, active_speaker_timeline=[], visual_identities=[])


def _problem_segments(segments: list[TranscriptSegment], config: AppConfig) -> list[dict[str, Any]]:
    recent_segments = segments[-24:]
    classifications = _classify_texts([segment.text for segment in recent_segments], PROBLEM_LABELS, config)
    issues: list[dict[str, Any]] = []
    for segment, classification in zip(recent_segments, classifications):
        if classification is None:
            continue
        label, score = classification
        if label == "routine discussion":
            continue
        issues.append(
            {
                "timestamp": round(segment.start, 2),
                "speaker": segment.speaker,
                "category": label,
                "confidence": round(score, 3),
                "text": segment.text,
            }
        )
    return issues[:10]


def _discussion_points(segments: list[TranscriptSegment]) -> list[str]:
    points: list[str] = []
    for segment in segments[-16:]:
        text = " ".join(segment.text.split())
        if len(text) < 24:
            continue
        points.append(text[:180])
        if len(points) >= 6:
            break
    return points


def _build_suggestions(
    *,
    decisions: list[dict[str, Any]],
    execution_plan: list[dict[str, Any]],
    problems: list[dict[str, Any]],
) -> list[str]:
    suggestions: list[str] = []
    if problems:
        suggestions.append("Review the flagged blockers and assign a named owner for each unresolved risk before the meeting closes.")
    if execution_plan:
        suggestions.append("Push the top execution tasks into GitLab issues or milestones while the decision context is still fresh.")
    if decisions and not execution_plan:
        suggestions.append("Convert approved decisions into explicit action items with owners and deadlines.")
    if not decisions:
        suggestions.append("End the meeting with a formal decision check so unresolved topics do not leave without ownership.")
    return suggestions[:4]


def _generate_meeting_summary(segments: list[TranscriptSegment], decisions: list[dict[str, Any]], problems: list[dict[str, Any]], config: AppConfig) -> tuple[str, str]:
    discussion = " ".join(segment.text for segment in segments[-24:])
    prompt = (
        "Summarize this live meeting in one short paragraph. "
        "Explain what the meeting was about, the main points discussed, and the current outcome or likely next steps. "
        "Be concrete and do not use bullet points.\n\n"
        f"Discussion: {discussion[:2800]}\n"
        f"Decisions: {json.dumps(decisions[:5])}\n"
        f"Problems: {json.dumps(problems[:5])}"
    )
    generated, source = generate_text(prompt, config, max_new_tokens=110, min_new_tokens=30)
    if generated and all(marker not in generated for marker in ('{"', "DM-", "decision_id", "timestamp")):
        return generated, source

    if not segments:
        return "No meeting transcript has been captured yet.", "template"
    topics = _discussion_points(segments)
    summary = f"The meeting focused on {topics[0].lower() if topics else 'ongoing agenda items'}."
    if len(topics) > 1:
        summary += f" Additional discussion covered {topics[1].lower()}."
    if decisions:
        summary += f" {len(decisions)} decision points and {len(problems)} notable risks or blockers were identified."
    if decisions:
        summary += " The current outcome is an execution-ready set of follow-up actions."
    return summary, "template"


def _generate_actionable_insights(decisions: list[dict[str, Any]], execution_plan: list[dict[str, Any]], problems: list[dict[str, Any]]) -> list[str]:
    insights: list[str] = []
    if decisions:
        insights.append(f"{len(decisions)} decision signals have been detected and ranked for execution readiness.")
    if execution_plan:
        insights.append(f"{len(execution_plan)} action items are ready for downstream project tracking.")
    if problems:
        insights.append(f"{len(problems)} problem or risk statements need active follow-up.")
    return insights[:4]


def _segments_from_dicts(items: list[dict[str, Any]]) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            start=float(item.get("start", 0.0) or 0.0),
            end=float(item.get("end", 0.0) or 0.0),
            speaker=str(item.get("speaker", "Live Speaker") or "Live Speaker"),
            text=str(item.get("text", "") or "").strip(),
            confidence=float(item.get("confidence", 0.0) or 0.0),
        )
        for item in items
        if str(item.get("text", "") or "").strip()
    ]


def analyze_live_segments(
    segments: list[TranscriptSegment],
    config: AppConfig,
    *,
    session_id: str,
    title: str,
    source_type: str,
    status: str,
    visual_artifact_payloads: list[dict[str, Any]] | None = None,
    cumulative_attention: dict[str, Any] | None = None,
    presentation_windows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    transcript_result = _segments_to_transcript_result(segments)
    decision_events, decision_warnings = decision_moments.run(segments, config)
    visual_artifacts_payloads = list(visual_artifact_payloads or [])
    visual_objects = []
    for payload in visual_artifacts_payloads:
        visual_objects.append(SimpleNamespace(**payload))
    workflow_result = workflow_engine.run(segments, decision_events, visual_objects, config)
    trace_result = decision_trace.run(segments, decision_events, visual_objects, workflow_result, config)
    attention_result = _attention_from_dict(cumulative_attention)
    speaker_result = _empty_speaker_result(segments)
    meeting_scores = scoring.run(speaker_result, decision_events, attention_result, workflow_result, config)
    problems = _problem_segments(segments, config)
    discussion_points = _discussion_points(segments)
    decision_dicts = [asdict(item) for item in decision_events]
    summary, summary_source = _generate_meeting_summary(segments, decision_dicts, problems, config)
    suggestions = _build_suggestions(
        decisions=workflow_result.prioritized_decisions,
        execution_plan=workflow_result.execution_plan,
        problems=problems,
    )
    outcomes = [task.get("title", "") for task in workflow_result.execution_plan[:6] if task.get("title")]
    actionable_insights = _generate_actionable_insights(
        workflow_result.prioritized_decisions,
        workflow_result.execution_plan,
        problems,
    )

    contract = build_agentic_contract(
        SimpleNamespace(
            input_video=f"live-session:{session_id}",
            transcript=transcript_result,
            speaker_dominance=speaker_result,
            decision_moments=decision_events,
            visual_artifacts=[],
            workflow_model=workflow_result,
            decision_traces=trace_result,
            attention_sentiment=attention_result,
            meeting_scores=meeting_scores,
            warnings=decision_warnings,
            metadata={},
        ),
        analysis_profile=config.default_analysis_profile,
        source_mode="live",
        contract_version=config.analysis_contract_version,
    )

    return {
        "session_id": session_id,
        "title": title,
        "status": status,
        "source_type": source_type,
        "analysis_profile": config.default_analysis_profile,
        "transcript": [asdict(segment) for segment in segments],
        "visual_artifacts": visual_artifacts_payloads,
        "attention_sentiment": _attention_to_dict(attention_result),
        "presentation_windows": list(presentation_windows or []),
        "rolling_summary": summary,
        "rolling_summary_source": summary_source,
        "discussion_points": discussion_points,
        "problems": problems,
        "decisions": decision_dicts,
        "action_items": workflow_result.execution_plan,
        "prioritized_decisions": workflow_result.prioritized_decisions,
        "decision_traces": [asdict(item) for item in trace_result],
        "actionable_insights": actionable_insights,
        "suggestions": suggestions,
        "meeting_outcomes": outcomes,
        "meeting_scores": asdict(meeting_scores),
        "warnings": decision_warnings,
        "agentic_contract": contract,
        "updated_at_segments": len(segments),
    }


def append_transcript_dicts(
    existing: list[dict[str, Any]],
    new_segments: list[TranscriptSegment],
) -> list[dict[str, Any]]:
    appended = list(existing)
    for segment in new_segments:
        payload = asdict(segment)
        if appended:
            last = appended[-1]
            if (
                abs(float(last.get("start", 0.0)) - payload["start"]) < 0.05
                and abs(float(last.get("end", 0.0)) - payload["end"]) < 0.05
                and str(last.get("text", "")).strip() == payload["text"].strip()
            ):
                continue
        appended.append(payload)
    return appended


def transcribe_live_chunk(
    chunk_path: Path,
    config: AppConfig,
    *,
    start_offset_seconds: float,
    speaker_name: str = "Live Speaker",
) -> list[TranscriptSegment]:
    segments, _warnings = transcribe(chunk_path, config)
    adjusted: list[TranscriptSegment] = []
    for segment in segments:
        adjusted.append(
            TranscriptSegment(
                start=round(start_offset_seconds + segment.start, 2),
                end=round(start_offset_seconds + segment.end, 2),
                speaker=speaker_name,
                text=segment.text,
                confidence=segment.confidence,
            )
        )
    return adjusted


def write_live_result(result: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "live_session_result.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return path


def transcript_dicts_to_segments(items: list[dict[str, Any]]) -> list[TranscriptSegment]:
    return _segments_from_dicts(items)
