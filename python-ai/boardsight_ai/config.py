from __future__ import annotations

import os
from dataclasses import dataclass
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
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    output_root: Path
    analysis_profile: str = "production"
    active_speaker_weight_audio: float = 0.7
    active_speaker_weight_visual: float = 0.3
    yolo_model_name: str = "yolov8n.pt"
    text_classifier_model: str = "typeform/distilbert-base-uncased-mnli"
    image_classifier_model: str = "openai/clip-vit-base-patch32"
    deepface_detector_backend: str = "opencv"
    video_sample_seconds: float = 20.0
    visual_sample_seconds: float = 45.0
    max_visual_samples: int = 2
    max_attention_samples: int = 1
    max_face_samples: int = 1
    max_workflow_segments: int = 12
    faster_whisper_model: str = "tiny.en"
    enable_diarization: bool = False
    llm_provider: str = "gemini"
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    lightweight_visual_window_seconds: float = 18.0
    lightweight_visual_gap_seconds: float = 30.0
    lightweight_max_evidence_segments: int = 8


def default_config(project_root: Path | None = None, output_root: Path | None = None) -> AppConfig:
    resolved_root = (project_root or Path(__file__).resolve().parents[2]).resolve()
    _load_local_env(resolved_root)
    resolved_output = (output_root or resolved_root / "output").resolve()
    resolved_output.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        project_root=resolved_root,
        output_root=resolved_output,
        analysis_profile=os.getenv("BOARDSIGHT_ANALYSIS_PROFILE", "production"),
        active_speaker_weight_audio=float(os.getenv("BOARDSIGHT_ACTIVE_SPEAKER_WEIGHT_AUDIO", "0.7")),
        active_speaker_weight_visual=float(os.getenv("BOARDSIGHT_ACTIVE_SPEAKER_WEIGHT_VISUAL", "0.3")),
        yolo_model_name=os.getenv("BOARDSIGHT_YOLO_MODEL", "yolov8n.pt"),
        text_classifier_model=os.getenv("BOARDSIGHT_TEXT_CLASSIFIER_MODEL", "typeform/distilbert-base-uncased-mnli"),
        image_classifier_model=os.getenv("BOARDSIGHT_IMAGE_CLASSIFIER_MODEL", "openai/clip-vit-base-patch32"),
        deepface_detector_backend=os.getenv("BOARDSIGHT_DEEPFACE_DETECTOR", "opencv"),
        video_sample_seconds=float(os.getenv("BOARDSIGHT_VIDEO_SAMPLE_SECONDS", "20.0")),
        visual_sample_seconds=float(os.getenv("BOARDSIGHT_VISUAL_SAMPLE_SECONDS", "45.0")),
        max_visual_samples=int(os.getenv("BOARDSIGHT_MAX_VISUAL_SAMPLES", "2")),
        max_attention_samples=int(os.getenv("BOARDSIGHT_MAX_ATTENTION_SAMPLES", "1")),
        max_face_samples=int(os.getenv("BOARDSIGHT_MAX_FACE_SAMPLES", "1")),
        max_workflow_segments=int(os.getenv("BOARDSIGHT_MAX_WORKFLOW_SEGMENTS", "12")),
        faster_whisper_model=os.getenv("BOARDSIGHT_FASTER_WHISPER_MODEL", "tiny.en"),
        enable_diarization=_bool_env("BOARDSIGHT_ENABLE_DIARIZATION", "false"),
        llm_provider=os.getenv("BOARDSIGHT_LLM_PROVIDER", "gemini"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        gemini_model=os.getenv("BOARDSIGHT_GEMINI_MODEL", "gemini-2.5-flash"),
        lightweight_visual_window_seconds=float(os.getenv("BOARDSIGHT_LIGHTWEIGHT_VISUAL_WINDOW_SECONDS", "18.0")),
        lightweight_visual_gap_seconds=float(os.getenv("BOARDSIGHT_LIGHTWEIGHT_VISUAL_GAP_SECONDS", "30.0")),
        lightweight_max_evidence_segments=int(os.getenv("BOARDSIGHT_LIGHTWEIGHT_MAX_EVIDENCE_SEGMENTS", "8")),
    )
