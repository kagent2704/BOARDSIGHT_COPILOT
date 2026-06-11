from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path


def _load_local_env(project_root: Path) -> None:
    env_path = project_root / "python-ai" / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    output_root: Path
    active_speaker_weight_audio: float = 0.7
    active_speaker_weight_visual: float = 0.3
    yolo_model_name: str = "yolov8n.pt"
    text_classifier_model: str = os.getenv("BOARDSIGHT_TEXT_CLASSIFIER_MODEL", "typeform/distilbert-base-uncased-mnli")
    image_classifier_model: str = os.getenv("BOARDSIGHT_IMAGE_CLASSIFIER_MODEL", "openai/clip-vit-base-patch32")
    deepface_detector_backend: str = os.getenv("BOARDSIGHT_DEEPFACE_DETECTOR", "opencv")
    video_sample_seconds: float = float(os.getenv("BOARDSIGHT_VIDEO_SAMPLE_SECONDS", "20.0"))
    visual_sample_seconds: float = float(os.getenv("BOARDSIGHT_VISUAL_SAMPLE_SECONDS", "45.0"))
    max_visual_samples: int = int(os.getenv("BOARDSIGHT_MAX_VISUAL_SAMPLES", "2"))
    max_attention_samples: int = int(os.getenv("BOARDSIGHT_MAX_ATTENTION_SAMPLES", "1"))
    max_face_samples: int = int(os.getenv("BOARDSIGHT_MAX_FACE_SAMPLES", "1"))
    max_workflow_segments: int = int(os.getenv("BOARDSIGHT_MAX_WORKFLOW_SEGMENTS", "12"))
    faster_whisper_model: str = os.getenv("BOARDSIGHT_FASTER_WHISPER_MODEL", "tiny.en")
    enable_diarization: bool = os.getenv("BOARDSIGHT_ENABLE_DIARIZATION", "false").lower() in {"1", "true", "yes", "on"}
    enable_visual_ocr: bool = os.getenv("BOARDSIGHT_ENABLE_VISUAL_OCR", "false").lower() in {"1", "true", "yes", "on"}
    enable_visual_caption: bool = os.getenv("BOARDSIGHT_ENABLE_VISUAL_CAPTION", "false").lower() in {"1", "true", "yes", "on"}
    enable_attention_analysis: bool = os.getenv("BOARDSIGHT_ENABLE_ATTENTION_ANALYSIS", "true").lower() in {"1", "true", "yes", "on"}
    enable_presentation_summary: bool = os.getenv("BOARDSIGHT_ENABLE_PRESENTATION_SUMMARY", "true").lower() in {"1", "true", "yes", "on"}
    max_parallel_workers: int = int(os.getenv("BOARDSIGHT_MAX_PARALLEL_WORKERS", "3"))
    default_analysis_profile: str = os.getenv("BOARDSIGHT_ANALYSIS_PROFILE", "recorded-fast")
    analysis_contract_version: str = "2026-06-10"
    gitlab_base_url: str | None = os.getenv("BOARDSIGHT_GITLAB_BASE_URL")
    gitlab_project_id: str | None = os.getenv("BOARDSIGHT_GITLAB_PROJECT_ID")
    gitlab_private_token: str | None = os.getenv("BOARDSIGHT_GITLAB_PRIVATE_TOKEN")
    agent_api_key: str | None = os.getenv("BOARDSIGHT_AGENT_API_KEY")
    llm_provider: str = os.getenv("BOARDSIGHT_LLM_PROVIDER", "transformers")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")


def default_config(project_root: Path | None = None, output_root: Path | None = None) -> AppConfig:
    resolved_root = (project_root or Path(__file__).resolve().parents[2]).resolve()
    _load_local_env(resolved_root)
    resolved_output = (output_root or resolved_root / "output").resolve()
    resolved_output.mkdir(parents=True, exist_ok=True)
    return AppConfig(project_root=resolved_root, output_root=resolved_output)


def resolve_runtime_config(
    config: AppConfig,
    analysis_profile: str | None = None,
    source_mode: str | None = None,
) -> AppConfig:
    profile = (analysis_profile or config.default_analysis_profile or "recorded-fast").strip().lower()
    source = (source_mode or "recorded").strip().lower()

    profile_overrides: dict[str, dict[str, object]] = {
        "recorded-fast": {
            "video_sample_seconds": 30.0,
            "visual_sample_seconds": 60.0,
            "max_visual_samples": 1,
            "max_attention_samples": 1,
            "max_face_samples": 1,
            "max_workflow_segments": 8,
            "enable_visual_ocr": False,
            "enable_visual_caption": False,
            "enable_attention_analysis": True,
            "enable_presentation_summary": True,
        },
        "recorded-balanced": {
            "video_sample_seconds": 20.0,
            "visual_sample_seconds": 45.0,
            "max_visual_samples": 2,
            "max_attention_samples": 1,
            "max_face_samples": 1,
            "max_workflow_segments": 12,
            "enable_visual_ocr": False,
            "enable_visual_caption": True,
            "enable_attention_analysis": True,
            "enable_presentation_summary": True,
        },
        "recorded-deep": {
            "video_sample_seconds": 15.0,
            "visual_sample_seconds": 25.0,
            "max_visual_samples": 4,
            "max_attention_samples": 3,
            "max_face_samples": 2,
            "max_workflow_segments": 24,
            "enable_visual_ocr": True,
            "enable_visual_caption": True,
            "enable_attention_analysis": True,
            "enable_presentation_summary": True,
        },
        "live": {
            "video_sample_seconds": 10.0,
            "visual_sample_seconds": 20.0,
            "max_visual_samples": 1,
            "max_attention_samples": 1,
            "max_face_samples": 1,
            "max_workflow_segments": 6,
            "enable_visual_ocr": False,
            "enable_visual_caption": False,
            "enable_attention_analysis": True,
            "enable_presentation_summary": True,
        },
    }
    overrides = dict(profile_overrides.get(profile, profile_overrides["recorded-fast"]))

    if source == "live":
        live_defaults = profile_overrides["live"]
        for key, value in live_defaults.items():
            overrides.setdefault(key, value)

    return replace(config, default_analysis_profile=profile, **overrides)
