from __future__ import annotations

from pathlib import Path

from boardsight_ai.config import AppConfig
from boardsight_ai.models import (
    AttentionSentimentResult,
    MeetingScores,
    PipelineResult,
    SpeakerDominanceResult,
    TranscriptResult,
    WorkflowModel,
)
from boardsight_ai.pipeline import run_pipeline
from boardsight_ai.storage import get_meeting_result, save_meeting_result


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        project_root=tmp_path,
        output_root=tmp_path / "out",
        analysis_profile="production",
        llm_provider="gemini",
        gemini_api_key="test-key",
    )


def test_run_pipeline_routes_to_lightweight_runtime(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    expected_result = PipelineResult(
        input_video="demo.mp4",
        transcript=TranscriptResult(
            full_text="Roadmap approved and report to be shared.",
            segments=[],
            speaker_directory=[],
        ),
        speaker_dominance=SpeakerDominanceResult(
            speakers=[],
            active_speaker_timeline=[],
            visual_identities=[],
        ),
        decision_moments=[],
        visual_artifacts=[],
        workflow_model=WorkflowModel(stages=[], transitions=[], bottlenecks=[]),
        decision_traces=[],
        attention_sentiment=AttentionSentimentResult(
            overall_attention=64.0,
            overall_sentiment="positive",
            engagement_timeline=[],
            sentiment_timeline=[],
            cognitive_rating={"focus": 64.0, "clarity": 61.0, "overload_risk": 24.0},
            participant_states=[],
            model_sources=["transcript-engagement-heuristic"],
            coverage_ratio=1.0,
        ),
        meeting_scores=MeetingScores(
            impact_score=55.0,
            productivity_score=72.0,
            execution_readiness=77.0,
            speaker_rating={},
            cognitive_rating={},
            meeting_conclusion="Lightweight meeting assessment complete.",
        ),
        warnings=[],
        metadata={
            "data_contract_version": "boardsight-result-v2",
            "storage_schema_version": "meetings-v2",
            "requested_analysis_profile": "production",
            "effective_analysis_profile": "boardsight-production-lightweight-v1",
            "performance_report": {
                "runtime_profile": "boardsight-production-lightweight-v1",
            },
            "presentation_insights": {
                "summary_source": "gemini:test",
                "visual_window_count": 0,
            },
            "lightweight_structured_outputs": {
                "summary": "Roadmap approved; report will be shared.",
                "discussion_points": ["roadmap", "report"],
                "decisions": ["Roadmap approved."],
                "action_items": ["Share the report."],
                "blockers": [],
                "outcomes": ["Share the report."],
            },
        },
    )

    captured: dict[str, object] = {}

    def _fake_run_lightweight_pipeline(video_path, output_dir, resolved_config, analysis_range=None, requested_profile=None):
        captured["video_path"] = video_path
        captured["output_dir"] = output_dir
        captured["analysis_range"] = analysis_range
        captured["requested_profile"] = requested_profile
        captured["config"] = resolved_config
        return expected_result

    monkeypatch.setattr(
        "boardsight_ai.pipeline.run_lightweight_pipeline",
        _fake_run_lightweight_pipeline,
    )

    result = run_pipeline(
        Path("demo.mp4"),
        tmp_path / "out",
        config=config,
        analysis_range={"start_seconds": 0.0, "end_seconds": 45.0},
        analysis_profile="production",
    )

    assert result is expected_result
    assert captured["video_path"] == Path("demo.mp4")
    assert captured["output_dir"] == tmp_path / "out"
    assert captured["analysis_range"] == {"start_seconds": 0.0, "end_seconds": 45.0}
    assert captured["requested_profile"] == "production"
    assert captured["config"] == config


def test_storage_persists_lightweight_runtime_profile(tmp_path: Path) -> None:
    result = PipelineResult(
        input_video="demo.mp4",
        transcript=TranscriptResult(full_text="Approved the roadmap.", segments=[], speaker_directory=[]),
        speaker_dominance=SpeakerDominanceResult(speakers=[], active_speaker_timeline=[], visual_identities=[]),
        decision_moments=[],
        visual_artifacts=[],
        workflow_model=WorkflowModel(stages=[], transitions=[], bottlenecks=[]),
        decision_traces=[],
        attention_sentiment=AttentionSentimentResult(
            overall_attention=0.0,
            overall_sentiment="neutral",
            engagement_timeline=[],
            sentiment_timeline=[],
            cognitive_rating={"focus": 0.0, "clarity": 0.0, "overload_risk": 0.0},
            participant_states=[],
            model_sources=[],
            coverage_ratio=0.0,
        ),
        meeting_scores=MeetingScores(
            impact_score=0.0,
            productivity_score=0.0,
            execution_readiness=0.0,
            speaker_rating={},
            cognitive_rating={},
            meeting_conclusion="Lightweight meeting assessment unavailable.",
        ),
        warnings=[],
        metadata={
            "data_contract_version": "boardsight-result-v2",
            "performance_report": {"runtime_profile": "boardsight-production-lightweight-v1"},
        },
    )

    database_path = tmp_path / "meetings.db"
    meeting_id = save_meeting_result(
        database_path,
        result,
        output_dir=tmp_path / "out",
        result_file=tmp_path / "out" / "boardsight_result.json",
    )
    stored = get_meeting_result(database_path, meeting_id)

    assert stored is not None
    assert stored["runtime_profile"] == "boardsight-production-lightweight-v1"
    assert stored["data_contract_version"] == "boardsight-result-v2"
