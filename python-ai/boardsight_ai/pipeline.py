from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from boardsight_ai.agentic_contract import build_agentic_contract
from boardsight_ai.config import AppConfig, default_config
from boardsight_ai.features import (
    attention_sentiment,
    decision_moments,
    decision_trace,
    scoring,
    speaker_dominance,
    speaker_labeling,
    visual_artifacts,
    workflow_engine,
)
from boardsight_ai.evaluation import write_evaluation
from boardsight_ai.models import PipelineResult, TranscriptSegment, VisualArtifact
from boardsight_ai.providers.llm import summarize
from boardsight_ai.providers.media import probe_video
from boardsight_ai.providers.speech import transcribe
from boardsight_ai.reporting import write_structured_reports


def _overlapping_transcript_segments(
    transcript_segments: list[TranscriptSegment],
    artifact: VisualArtifact,
    window_padding: float = 12.0,
) -> list[TranscriptSegment]:
    start = max(0.0, float(artifact.start_time) - window_padding)
    end = float(artifact.end_time) + window_padding
    return [
        segment
        for segment in transcript_segments
        if float(segment.end) >= start and float(segment.start) <= end
    ]


def _build_presentation_insights(
    transcript_segments: list[TranscriptSegment],
    visual_result: list[VisualArtifact],
    config: AppConfig,
) -> dict[str, Any]:
    if not config.enable_presentation_summary:
        return {
            "summary": "Presentation summarization is disabled for this analysis profile.",
            "summary_source": "profile-disabled",
            "visual_window_count": len(visual_result),
            "artifact_types": {},
            "evidence": [],
        }
    presentation_artifacts = [
        artifact
        for artifact in visual_result
        if any(
            keyword in f"{artifact.artifact_type} {artifact.display_mode}".lower()
            for keyword in ("slide", "presentation", "screen", "chart", "graph", "dashboard", "document")
        )
    ]
    if not presentation_artifacts:
        return {
            "summary": "No presentation-oriented visual windows were detected, so slide-content insight is unavailable.",
            "summary_source": "model-unavailable",
            "visual_window_count": 0,
            "artifact_types": {},
            "evidence": [],
        }

    artifact_counts: dict[str, int] = {}
    evidence: list[dict[str, Any]] = []
    synthesis_blocks: list[str] = []

    for artifact in presentation_artifacts:
        artifact_counts[artifact.artifact_type] = artifact_counts.get(artifact.artifact_type, 0) + 1
        nearby_segments = _overlapping_transcript_segments(transcript_segments, artifact)
        transcript_text = " ".join(segment.text.strip() for segment in nearby_segments if segment.text.strip())
        insight_text = artifact.content_insight or artifact.content_text or artifact.content_summary
        synthesis_blocks.append(
            " ".join(
                part
                for part in [
                    f"Presentation window from {artifact.start_time:.1f}s to {artifact.end_time:.1f}s.",
                    f"Slide category: {artifact.artifact_type.replace('-', ' ')}.",
                    f"Slide evidence: {insight_text}" if insight_text else "",
                    f"Spoken context: {transcript_text}" if transcript_text else "",
                ]
                if part
            )
        )
        evidence.append(
            {
                "artifact_id": artifact.artifact_id,
                "time_range": {
                    "start_seconds": artifact.start_time,
                    "end_seconds": artifact.end_time,
                },
                "artifact_type": artifact.artifact_type,
                "display_mode": artifact.display_mode,
                "content_text": artifact.content_text,
                "content_insight": artifact.content_insight,
                "nearby_transcript": transcript_text[:500],
            }
        )

    summary_input = " ".join(synthesis_blocks)[:4000]
    summary, summary_source = summarize(summary_input, config)
    return {
        "summary": summary,
        "summary_source": summary_source,
        "visual_window_count": len(presentation_artifacts),
        "artifact_types": artifact_counts,
        "evidence": evidence,
    }


def run_pipeline(
    video_path: Path,
    output_dir: Path,
    config: AppConfig | None = None,
    analysis_range: dict[str, float | None] | None = None,
    analysis_profile: str | None = None,
    source_mode: str = "recorded",
) -> PipelineResult:
    resolved_config = config or default_config(output_root=output_dir)
    warnings: list[str] = []
    timings: dict[str, float] = {}

    def timed(stage_name: str, action):
        started = time.perf_counter()
        value = action()
        timings[stage_name] = round(time.perf_counter() - started, 2)
        return value

    transcript_segments, transcript_warnings = timed("transcription", lambda: transcribe(video_path, resolved_config))
    warnings.extend(transcript_warnings)
    transcript_result = timed("speaker_labeling", lambda: speaker_labeling.run(transcript_segments, resolved_config))

    speaker_result = timed("speaker_dominance", lambda: speaker_dominance.run(transcript_result.segments, resolved_config, video_path))

    with ThreadPoolExecutor(max_workers=max(1, resolved_config.max_parallel_workers)) as executor:
        decision_future = executor.submit(
            timed,
            "decision_detection",
            lambda: decision_moments.run(transcript_result.segments, resolved_config),
        )
        visual_future = executor.submit(
            timed,
            "visual_artifacts",
            lambda: visual_artifacts.run(video_path, resolved_config),
        )
        attention_future = executor.submit(
            timed,
            "attention_sentiment",
            lambda: attention_sentiment.run(transcript_result.segments, resolved_config, video_path),
        )

        decision_events, decision_warnings = decision_future.result()
        visual_result, visual_warnings = visual_future.result()
        attention_result = attention_future.result()

    warnings.extend(decision_warnings)
    warnings.extend(visual_warnings)

    workflow_result = timed("workflow_model", lambda: workflow_engine.run(transcript_result.segments, decision_events, visual_result, resolved_config))
    trace_result = timed("decision_traces", lambda: decision_trace.run(transcript_result.segments, decision_events, visual_result, workflow_result, resolved_config))
    meeting_scores = timed("meeting_scores", lambda: scoring.run(speaker_result, decision_events, attention_result, workflow_result, resolved_config))
    presentation_insights = timed(
        "presentation_insights",
        lambda: _build_presentation_insights(transcript_result.segments, visual_result, resolved_config),
    )

    metadata = {
        "video_probe": probe_video(video_path),
        "analysis_profile": analysis_profile or resolved_config.default_analysis_profile,
        "source_mode": source_mode,
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
                "visual_sample_seconds": resolved_config.visual_sample_seconds,
                "max_visual_samples": resolved_config.max_visual_samples,
                "attention_sample_seconds": resolved_config.video_sample_seconds,
                "max_attention_samples": resolved_config.max_attention_samples,
                "max_face_samples": resolved_config.max_face_samples,
                "max_workflow_segments": resolved_config.max_workflow_segments,
                "faster_whisper_model": resolved_config.faster_whisper_model,
                "enable_diarization": resolved_config.enable_diarization,
                "enable_visual_ocr": resolved_config.enable_visual_ocr,
                "enable_visual_caption": resolved_config.enable_visual_caption,
                "enable_attention_analysis": resolved_config.enable_attention_analysis,
                "max_parallel_workers": resolved_config.max_parallel_workers,
            },
            "target_accuracy_range": "85-90%",
            "runtime_profile": "fast-sampled-full-model-stack",
            "current_status": {
                "transcript_generation": "ASR model-backed only; no placeholder transcript fallback",
                "speaker_dominance": "ASR/diarization-duration backed with CNN face-recognition identities when available",
                "visual_artifact_logging": f"zero-shot image classifier ({resolved_config.image_classifier_model}) plus YOLO detections when available, with TrOCR/BLIP presentation-content extraction on presentation windows",
                "decision_moment_detection": f"zero-shot text classifier ({resolved_config.text_classifier_model})",
                "decision_trace_generation": "transformer summarization only; unavailable text is reported when the model is not loaded",
                "attention_sentiment": ", ".join(attention_result.model_sources) if attention_result.model_sources else "model-unavailable",
                "workflow_engine": f"zero-shot text classifier ({resolved_config.text_classifier_model})",
            },
            "no_heuristics_policy": "Functional detections must come from pretrained model inference. Missing models produce unavailable results instead of heuristic placeholders.",
        },
        "presentation_insights": presentation_insights,
    }

    result = PipelineResult(
        input_video=str(video_path),
        transcript=transcript_result,
        speaker_dominance=speaker_result,
        decision_moments=decision_events,
        visual_artifacts=visual_result,
        workflow_model=workflow_result,
        decision_traces=trace_result,
        attention_sentiment=attention_result,
        meeting_scores=meeting_scores,
        warnings=warnings,
        metadata=metadata,
    )
    result.metadata["agentic_contract"] = build_agentic_contract(
        result,
        analysis_profile=(analysis_profile or resolved_config.default_analysis_profile or "recorded-fast"),
        source_mode=source_mode,
        contract_version=resolved_config.analysis_contract_version,
    )

    return result


def write_result(result: PipelineResult, result_file: Path) -> Path:
    result_file.parent.mkdir(parents=True, exist_ok=True)
    report_files = write_structured_reports(result, result_file.parent)
    performance_report_path = write_evaluation(result, result_file.parent)
    payload: dict[str, Any] = result.to_dict()
    payload.setdefault("metadata", {})
    payload["metadata"]["report_files"] = report_files
    payload["metadata"]["performance_report_file"] = str(performance_report_path)
    result_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return result_file
