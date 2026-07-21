from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


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
    enable_visual_ocr: bool = False
    enable_visual_caption: bool = False
    enable_attention_analysis: bool = True
    enable_presentation_summary: bool = True
    max_parallel_workers: int = 3
    default_analysis_profile: str = "recorded-fast"
    analysis_contract_version: str = "2026-06-10"
    gitlab_base_url: str | None = None
    gitlab_project_id: str | None = None
    gitlab_private_token: str | None = None
    notion_database_id: str | None = None
    notion_api_token: str | None = None
    trello_list_id: str | None = None
    trello_api_key: str | None = None
    trello_api_token: str | None = None
    microsoft_todo_list_id: str | None = None
    microsoft_graph_access_token: str | None = None
    agent_api_key: str | None = None
    database_url: str | None = None
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
        enable_diarization=_env_bool("BOARDSIGHT_ENABLE_DIARIZATION", "false"),
        enable_visual_ocr=_env_bool("BOARDSIGHT_ENABLE_VISUAL_OCR", "false"),
        enable_visual_caption=_env_bool("BOARDSIGHT_ENABLE_VISUAL_CAPTION", "false"),
        enable_attention_analysis=_env_bool("BOARDSIGHT_ENABLE_ATTENTION_ANALYSIS", "true"),
        enable_presentation_summary=_env_bool("BOARDSIGHT_ENABLE_PRESENTATION_SUMMARY", "true"),
        max_parallel_workers=int(os.getenv("BOARDSIGHT_MAX_PARALLEL_WORKERS", "3")),
        default_analysis_profile=os.getenv("BOARDSIGHT_ANALYSIS_PROFILE", "recorded-fast"),
        gitlab_base_url=os.getenv("BOARDSIGHT_GITLAB_BASE_URL"),
        gitlab_project_id=os.getenv("BOARDSIGHT_GITLAB_PROJECT_ID"),
        gitlab_private_token=os.getenv("BOARDSIGHT_GITLAB_PRIVATE_TOKEN"),
        notion_database_id=os.getenv("BOARDSIGHT_NOTION_DATABASE_ID"),
        notion_api_token=os.getenv("BOARDSIGHT_NOTION_API_TOKEN"),
        trello_list_id=os.getenv("BOARDSIGHT_TRELLO_LIST_ID"),
        trello_api_key=os.getenv("BOARDSIGHT_TRELLO_API_KEY"),
        trello_api_token=os.getenv("BOARDSIGHT_TRELLO_API_TOKEN"),
        microsoft_todo_list_id=os.getenv("BOARDSIGHT_MICROSOFT_TODO_LIST_ID"),
        microsoft_graph_access_token=os.getenv("BOARDSIGHT_MICROSOFT_GRAPH_ACCESS_TOKEN"),
        agent_api_key=os.getenv("BOARDSIGHT_AGENT_API_KEY"),
        database_url=os.getenv("BOARDSIGHT_DATABASE_URL"),
        llm_provider=os.getenv("BOARDSIGHT_LLM_PROVIDER", "gemini"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        gemini_api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
        gemini_model=os.getenv("BOARDSIGHT_GEMINI_MODEL", "gemini-2.5-flash"),
        lightweight_visual_window_seconds=float(os.getenv("BOARDSIGHT_LIGHTWEIGHT_VISUAL_WINDOW_SECONDS", "18.0")),
        lightweight_visual_gap_seconds=float(os.getenv("BOARDSIGHT_LIGHTWEIGHT_VISUAL_GAP_SECONDS", "30.0")),
        lightweight_max_evidence_segments=int(os.getenv("BOARDSIGHT_LIGHTWEIGHT_MAX_EVIDENCE_SEGMENTS", "8")),
    )


def resolve_runtime_config(
    config: AppConfig,
    analysis_profile: str | None = None,
    source_mode: str | None = None,
) -> AppConfig:
    profile = (analysis_profile or config.default_analysis_profile or config.analysis_profile or "recorded-fast").strip().lower()
    source = (source_mode or "recorded").strip().lower()

    profile_overrides: dict[str, dict[str, object]] = {
        "production": {
            "video_sample_seconds": 20.0,
            "visual_sample_seconds": 45.0,
            "max_visual_samples": 2,
            "max_attention_samples": 1,
            "max_face_samples": 1,
            "max_workflow_segments": 12,
        },
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

    normalized_profile = profile if profile in profile_overrides else "recorded-fast"
    overrides = dict(profile_overrides[normalized_profile])
    if source == "live":
        for key, value in profile_overrides["live"].items():
            overrides.setdefault(key, value)

    return replace(
        config,
        analysis_profile=normalized_profile,
        default_analysis_profile=normalized_profile,
        **overrides,
    )
