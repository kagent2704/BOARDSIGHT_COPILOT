from __future__ import annotations

from pathlib import Path

from boardsight_ai.config import AppConfig
from boardsight_ai.lightweight_pipeline import _extract_visual_artifacts
from boardsight_ai.models import TranscriptSegment


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        project_root=tmp_path,
        output_root=tmp_path / "out",
        analysis_profile="production",
        llm_provider="gemini",
        gemini_api_key="test-key",
        lightweight_visual_gap_seconds=12.0,
        lightweight_visual_window_seconds=10.0,
        lightweight_max_evidence_segments=4,
    )


class _FakeCapture:
    def __init__(self) -> None:
        self.position = 0

    def set(self, _prop: int, value: int) -> None:
        self.position = value

    def read(self):
        return True, f"frame-{self.position}"

    def release(self) -> None:
        return None


class _FakeCv2:
    CAP_PROP_POS_FRAMES = 1


def test_extract_visual_artifacts_uses_sampled_video_evidence(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    transcript_segments = [
        TranscriptSegment(5.0, 9.0, "Kash", "We approved the roadmap."),
        TranscriptSegment(28.0, 34.0, "Akanksha", "Please share the dashboard export after this."),
    ]

    monkeypatch.setattr(
        "boardsight_ai.lightweight_pipeline.probe_video",
        lambda _video_path: {"duration_sec": 60.0, "fps": 10.0},
    )
    monkeypatch.setattr(
        "boardsight_ai.lightweight_pipeline.safe_open_video",
        lambda _video_path: (_FakeCapture(), _FakeCv2()),
    )

    calls: list[str] = []

    def _fake_analyze_sparse_frame(frame, _config):
        calls.append(str(frame))
        if frame == "frame-0":
            return {
                "artifact_type": "participant-camera",
                "display_mode": "speaker-view",
                "visible_people_count": 2,
                "screen_present": False,
                "chart_present": False,
                "document_present": False,
                "textual_content": "",
                "summary": "Two people visible on camera.",
                "confidence": 0.71,
                "detections": [{"label": "face", "confidence": 0.58}],
            }
        return {
            "artifact_type": "dashboard",
            "display_mode": "screen-share",
            "visible_people_count": 0,
            "screen_present": True,
            "chart_present": True,
            "document_present": False,
            "textual_content": "Q3 dashboard",
            "summary": "A shared dashboard is visible.",
            "confidence": 0.84,
            "detections": [{"label": "monitor", "confidence": 0.88}],
        }

    monkeypatch.setattr(
        "boardsight_ai.lightweight_pipeline.analyze_sparse_frame",
        _fake_analyze_sparse_frame,
    )

    artifacts = _extract_visual_artifacts(Path("demo.mp4"), transcript_segments, config)

    assert calls
    assert len(artifacts) >= 2
    assert any(item.artifact_type == "participant-camera" for item in artifacts)
    assert any(item.artifact_type == "dashboard" for item in artifacts)
    assert any("visible participant" in item.content_insight for item in artifacts)
    assert any("screen content visible" in item.content_insight for item in artifacts)
